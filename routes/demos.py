import logging
import mimetypes
import os
import re
import time

from flask import Blueprint, Response, stream_with_context
from curl_cffi import requests

from http_client import HLTV_IMPERSONATION_CHAIN, get_with_impersonation_fallback

demos_bp = Blueprint("demos", __name__, url_prefix="/api/v1/download")
logger = logging.getLogger(__name__)

CF_CHALLENGE_STATUS_CODES = {403, 429, 503}
CF_CHALLENGE_BODY_MARKERS = [
    "just a moment",
    "checking your browser",
    "attention required",
    "cf-browser-verification",
    "challenge-platform",
    "cdn-cgi/challenge-platform",
    "window._cf_chl_opt",
    "please enable javascript and cookies",
]
CF_CHALLENGE_STRONG_MARKERS = {
    "cf-browser-verification",
    "challenge-platform",
    "cdn-cgi/challenge-platform",
    "window._cf_chl_opt",
}
DEFAULT_HLTV_DEMO_IMPERSONATE = (
    os.getenv("HLTV_DEMO_IMPERSONATE", "chrome136").strip() or "chrome136"
)
OHMYCAPTCHA_ENV_HINT = {
    "OHMYCAPTCHA_BASE_URL": "http://127.0.0.1:8004",
    "OHMYCAPTCHA_CLIENT_KEY": "<your-client-key>",
    "OHMYCAPTCHA_TASK_TYPE": "TurnstileTaskProxyless",
    "OHMYCAPTCHA_TURNSTILE_SITEKEY": "<optional-sitekey>",
}


def _format_upstream_error_context(upstream_resp):
    interesting_headers = [
        "Content-Type",
        "Content-Length",
        "Server",
        "CF-RAY",
        "CF-Cache-Status",
        "Location",
        "Retry-After",
        "Set-Cookie",
    ]
    headers = {}
    for header in interesting_headers:
        value = upstream_resp.headers.get(header)
        if value:
            if header == "Set-Cookie" and len(value) > 200:
                value = value[:200] + "..."
            headers[header] = value

    try:
        body_preview = " ".join((upstream_resp.text or "").split())
    except Exception as exc:
        body_preview = f"<unavailable: {exc}>"

    if len(body_preview) > 400:
        body_preview = body_preview[:400] + "..."

    return headers, body_preview


def _detect_cloudflare_challenge(status_code, headers, body_preview):
    signals = []

    if status_code in CF_CHALLENGE_STATUS_CODES:
        signals.append(f"status:{status_code}")

    cf_ray = headers.get("CF-RAY")
    if cf_ray:
        signals.append("header:CF-RAY")

    server = (headers.get("Server") or "").lower()
    if "cloudflare" in server:
        signals.append("header:Server=cloudflare")

    set_cookie = (headers.get("Set-Cookie") or "").lower()
    if "cf_clearance" in set_cookie:
        signals.append("header:Set-Cookie=cf_clearance")

    body_lower = (body_preview or "").lower()
    marker_hits = []
    for marker in CF_CHALLENGE_BODY_MARKERS:
        if marker in body_lower:
            marker_hits.append(marker)
            signals.append(f"body:{marker}")

    has_hard_header = bool(cf_ray) or "cf_clearance" in set_cookie
    has_cf_fingerprint = has_hard_header or "cloudflare" in server
    strong_marker_hit = any(
        marker in CF_CHALLENGE_STRONG_MARKERS for marker in marker_hits
    )
    is_challenge = (
        (
            status_code in CF_CHALLENGE_STATUS_CODES
            and (has_cf_fingerprint or bool(marker_hits))
        )
        or strong_marker_hit
        or (has_cf_fingerprint and bool(marker_hits))
    )
    return is_challenge, signals


def _normalize_ohmycaptcha_base_url(raw_url):
    base_url = (raw_url or "").strip().rstrip("/")
    if base_url.endswith("/api/v1/health"):
        return base_url[: -len("/api/v1/health")]
    if base_url.endswith("/api/v1"):
        return base_url[: -len("/api/v1")]
    if base_url.endswith("/health"):
        return base_url[: -len("/health")]
    return base_url


def _is_ohmycaptcha_configured():
    base_url = os.getenv("OHMYCAPTCHA_BASE_URL", "").strip()
    client_key = os.getenv("OHMYCAPTCHA_CLIENT_KEY", "").strip()
    return bool(base_url and client_key)


def _build_ohmycaptcha_hint(reason):
    return {
        "reason": reason,
        "how_to_enable": {
            "set_env": OHMYCAPTCHA_ENV_HINT,
            "note": "Configure env vars in hltv-scraper-api runtime. OHMYCAPTCHA_TURNSTILE_SITEKEY is optional fallback.",
        },
    }


def _extract_turnstile_sitekey(html_text):
    if not html_text:
        return None

    patterns = [
        r'data-sitekey=["\']([^"\']+)["\']',
        r'sitekey["\']?\s*[:=]\s*["\']([^"\']+)["\']',
        r'turnstile\.render\([^,]+,\s*\{[^\}]*sitekey\s*:\s*["\']([^"\']+)["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, html_text, flags=re.IGNORECASE)
        if match:
            candidate = (match.group(1) or "").strip()
            if candidate:
                return candidate

    return None


def _create_ohmycaptcha_task(base_url, client_key, website_url, sitekey):
    task_type = os.getenv("OHMYCAPTCHA_TASK_TYPE", "TurnstileTaskProxyless")
    payload = {
        "clientKey": client_key,
        "task": {
            "type": task_type,
            "websiteURL": website_url,
            "websiteKey": sitekey,
        },
    }
    create_resp = requests.post(f"{base_url}/createTask", json=payload, timeout=20)
    create_resp.raise_for_status()
    data = create_resp.json()
    if data.get("errorId") != 0:
        raise RuntimeError(
            f"ohmycaptcha createTask failed: {data.get('errorCode')} {data.get('errorDescription')}"
        )

    task_id = data.get("taskId")
    if not task_id:
        raise RuntimeError("ohmycaptcha createTask returned empty taskId")

    return task_id


def _poll_ohmycaptcha_task(base_url, client_key, task_id):
    poll_timeout_seconds = int(os.getenv("OHMYCAPTCHA_POLL_TIMEOUT_SECONDS", "90"))
    poll_interval_seconds = float(os.getenv("OHMYCAPTCHA_POLL_INTERVAL_SECONDS", "2"))
    deadline = time.time() + poll_timeout_seconds

    while time.time() < deadline:
        result_resp = requests.post(
            f"{base_url}/getTaskResult",
            json={"clientKey": client_key, "taskId": task_id},
            timeout=20,
        )
        result_resp.raise_for_status()
        result_data = result_resp.json()

        if result_data.get("errorId") != 0:
            raise RuntimeError(
                "ohmycaptcha getTaskResult failed: "
                f"{result_data.get('errorCode')} {result_data.get('errorDescription')}"
            )

        status = result_data.get("status")
        if status == "ready":
            solution = result_data.get("solution") or {}
            token = solution.get("token")
            if not token:
                raise RuntimeError(
                    "ohmycaptcha returned ready status without solution.token"
                )
            return token

        if status != "processing":
            raise RuntimeError(f"Unexpected ohmycaptcha task status: {status}")

        time.sleep(poll_interval_seconds)

    raise TimeoutError("Timed out waiting for ohmycaptcha turnstile token")


def _solve_turnstile_token(website_url, sitekey):
    base_url = _normalize_ohmycaptcha_base_url(os.getenv("OHMYCAPTCHA_BASE_URL", ""))
    if not base_url:
        raise RuntimeError(
            "OHMYCAPTCHA_BASE_URL is not configured (expected API root, e.g. http://host:8004 or http://host:8004/api/v1)"
        )

    client_key = os.getenv("OHMYCAPTCHA_CLIENT_KEY", "").strip()
    task_id = _create_ohmycaptcha_task(base_url, client_key, website_url, sitekey)
    return _poll_ohmycaptcha_task(base_url, client_key, task_id)


def _request_hltv_demo(target_url, turnstile_token=None):
    headers = None
    if turnstile_token:
        headers = {
            "cf-turnstile-response": turnstile_token,
            "x-turnstile-token": turnstile_token,
            "Referer": target_url,
        }

    return get_with_impersonation_fallback(
        target_url,
        impersonate=DEFAULT_HLTV_DEMO_IMPERSONATE,
        fallback_impersonations=HLTV_IMPERSONATION_CHAIN,
        stream=True,
        headers=headers,
    )


def _build_streaming_response_from_upstream(upstream_resp, demo_id):
    filename = f"demo_{demo_id}.rar"

    def generate():
        for chunk in upstream_resp.iter_content(chunk_size=8192):
            if chunk:
                yield chunk

    response = Response(
        stream_with_context(generate()), status=upstream_resp.status_code
    )
    forward_headers = ["Content-Type", "Content-Disposition", "Content-Length"]
    for header in forward_headers:
        if header in upstream_resp.headers:
            response.headers[header] = upstream_resp.headers[header]

    if "Content-Disposition" not in response.headers:
        response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    if "Content-Type" not in response.headers:
        guessed_content_type, _ = mimetypes.guess_type(filename)
        response.headers["Content-Type"] = (
            guessed_content_type or "application/octet-stream"
        )

    return response


def _is_html_response(upstream_resp):
    content_type = (upstream_resp.headers.get("Content-Type") or "").lower()
    return "text/html" in content_type or "application/xhtml+xml" in content_type


@demos_bp.route("/demo/<demo_id>", methods=["GET"])
def download_demo(demo_id: str):
    """
    Download a demo file from HLTV.
    ---
    tags:
      - Demos
    parameters:
      - name: demo_id
        in: path
        type: string
        required: true
        description: The ID of the demo to download.
    responses:
      200:
        description: The demo file stream
      404:
        description: Demo not found
      500:
        description: Internal server error
    """
    target_url = f"https://www.hltv.org/download/demo/{demo_id}"

    try:
        # Use curl_cffi to bypass Cloudflare
        # impersonate="safari15_3" worked for match details, using it here too
        # stream=True is critical for large file downloads
        upstream_resp = _request_hltv_demo(target_url)

        challenge_detected = False
        challenge_signals = []
        body_preview = ""
        should_enter_challenge_flow = False

        if upstream_resp.status_code != 200:
            should_enter_challenge_flow = True
            _, body_preview = _format_upstream_error_context(upstream_resp)
            challenge_detected, challenge_signals = _detect_cloudflare_challenge(
                upstream_resp.status_code,
                upstream_resp.headers,
                body_preview,
            )
        elif _is_html_response(upstream_resp):
            should_enter_challenge_flow = True
            _, body_preview = _format_upstream_error_context(upstream_resp)
            challenge_detected, challenge_signals = _detect_cloudflare_challenge(
                upstream_resp.status_code,
                upstream_resp.headers,
                body_preview,
            )

        if should_enter_challenge_flow:
            solver_attempted = False
            solver_error = None
            ohmycaptcha_hint = None
            if challenge_detected and _is_ohmycaptcha_configured():
                sitekey = _extract_turnstile_sitekey(upstream_resp.text or "")
                if not sitekey:
                    sitekey = os.getenv("OHMYCAPTCHA_TURNSTILE_SITEKEY", "").strip()
                if sitekey:
                    solver_attempted = True
                    try:
                        token = _solve_turnstile_token(target_url, sitekey)
                        retry_resp = _request_hltv_demo(
                            target_url,
                            turnstile_token=token,
                        )
                        upstream_resp = retry_resp
                    except Exception as exc:
                        solver_error = str(exc)
                        logger.warning(
                            "ohmycaptcha solve attempt failed: demo_id=%s target_url=%s sitekey=%s error=%s",
                            demo_id,
                            target_url,
                            sitekey,
                            solver_error,
                        )
                else:
                    solver_error = (
                        "Cloudflare challenge detected but no Turnstile sitekey was found "
                        "(neither in response body nor OHMYCAPTCHA_TURNSTILE_SITEKEY)"
                    )
            elif challenge_detected:
                ohmycaptcha_hint = _build_ohmycaptcha_hint(
                    "Cloudflare challenge detected, but OHMYCAPTCHA_BASE_URL / OHMYCAPTCHA_CLIENT_KEY are not fully configured"
                )

            final_is_html = _is_html_response(upstream_resp)
            final_headers, final_body_preview = _format_upstream_error_context(
                upstream_resp
            )
            final_challenge_detected, final_challenge_signals = (
                _detect_cloudflare_challenge(
                    upstream_resp.status_code,
                    upstream_resp.headers,
                    final_body_preview,
                )
            )
            final_failed = upstream_resp.status_code != 200 or final_is_html

            if final_failed:
                logger.warning(
                    "HLTV demo download failed: demo_id=%s status=%s target_url=%s challenge_detected=%s challenge_signals=%s solver_attempted=%s headers=%s body_preview=%s",
                    demo_id,
                    upstream_resp.status_code,
                    target_url,
                    final_challenge_detected,
                    final_challenge_signals,
                    solver_attempted,
                    final_headers,
                    final_body_preview,
                )
                payload = {
                    "error": f"Failed to fetch demo: HLTV returned {upstream_resp.status_code}",
                    "challenge_detected": final_challenge_detected,
                    "challenge_signals": final_challenge_signals,
                    "solver_attempted": solver_attempted,
                }
                if solver_error:
                    payload["solver_error"] = solver_error
                if ohmycaptcha_hint:
                    payload["ohmycaptcha_hint"] = ohmycaptcha_hint

                return payload, upstream_resp.status_code

        try:
            return _build_streaming_response_from_upstream(upstream_resp, demo_id)
        except Exception as stream_exc:
            logger.warning(
                "Streaming demo download failed, retrying once with a fresh upstream request: demo_id=%s target_url=%s error=%s",
                demo_id,
                target_url,
                stream_exc,
            )
            retry_stream_resp = _request_hltv_demo(target_url)
            if retry_stream_resp.status_code != 200 or _is_html_response(
                retry_stream_resp
            ):
                _, body_preview = _format_upstream_error_context(
                    retry_stream_resp
                )
                challenge_detected, challenge_signals = _detect_cloudflare_challenge(
                    retry_stream_resp.status_code,
                    retry_stream_resp.headers,
                    body_preview,
                )
                payload = {
                    "error": f"Failed to fetch demo after stream retry: HLTV returned {retry_stream_resp.status_code}",
                    "challenge_detected": challenge_detected,
                    "challenge_signals": challenge_signals,
                    "solver_attempted": False,
                }
                if challenge_detected and not _is_ohmycaptcha_configured():
                    payload["ohmycaptcha_hint"] = _build_ohmycaptcha_hint(
                        "Cloudflare challenge detected during stream retry, configure ohmycaptcha if this persists"
                    )
                return payload, retry_stream_resp.status_code
            return _build_streaming_response_from_upstream(retry_stream_resp, demo_id)

    except Exception as e:
        return {"error": str(e)}, 500
