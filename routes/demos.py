import logging
import mimetypes
import os

from flask import Blueprint, Response, stream_with_context

from http_client import (
    HLTV_IMPERSONATION_CHAIN,
    get_with_impersonation_fallback,
)
from routes.challenge_helpers import (
    _build_ohmycaptcha_hint,
    _normalize_ohmycaptcha_base_url,
    _solve_turnstile_token,
    detect_upstream_challenge,
    solve_upstream_turnstile,
)

demos_bp = Blueprint("demos", __name__, url_prefix="/api/v1/download")
logger = logging.getLogger(__name__)

DEMO_CHALLENGE_BODY_MARKERS = (
    "challenge-platform",
    "cdn-cgi/challenge-platform",
)
DEFAULT_HLTV_DEMO_IMPERSONATE = (
    os.getenv("HLTV_DEMO_IMPERSONATE", "chrome136").strip() or "chrome136"
)


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
            if header == "Set-Cookie":
                first_cookie = value.split(";", 1)[0]
                if "=" in first_cookie:
                    cookie_name = first_cookie.split("=", 1)[0].strip()
                    value = f"{cookie_name}=<redacted>"
                else:
                    value = "<redacted>"
            headers[header] = value

    try:
        body_preview = " ".join((upstream_resp.text or "").split())
    except Exception as exc:
        body_preview = f"<unavailable: {exc}>"

    if len(body_preview) > 400:
        body_preview = body_preview[:400] + "..."

    return headers, body_preview
def _is_ohmycaptcha_configured():
    base_url = os.getenv("OHMYCAPTCHA_BASE_URL", "").strip()
    client_key = os.getenv("OHMYCAPTCHA_CLIENT_KEY", "").strip()
    return bool(base_url and client_key)


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
        # stream=True is critical for large file downloads
        # impersonation is handled by the shared fallback helper
        upstream_resp = _request_hltv_demo(target_url)

        challenge_detected = False
        challenge_signals = []
        should_enter_challenge_flow = False

        if upstream_resp.status_code != 200:
            should_enter_challenge_flow = True
            challenge_detected, challenge_signals = detect_upstream_challenge(
                upstream_resp,
                extra_body_markers=DEMO_CHALLENGE_BODY_MARKERS,
            )
        elif _is_html_response(upstream_resp):
            should_enter_challenge_flow = True
            challenge_detected, challenge_signals = detect_upstream_challenge(
                upstream_resp,
                extra_body_markers=DEMO_CHALLENGE_BODY_MARKERS,
            )

        if should_enter_challenge_flow:
            solve_result = solve_upstream_turnstile(
                upstream_resp,
                target_url=target_url,
                request_with_token=lambda token: _request_hltv_demo(
                    target_url,
                    turnstile_token=token,
                ),
                extra_body_markers=DEMO_CHALLENGE_BODY_MARKERS,
                missing_config_reason=(
                    "Cloudflare challenge detected, but OHMYCAPTCHA_BASE_URL / "
                    "OHMYCAPTCHA_CLIENT_KEY are not fully configured"
                ),
            )

            upstream_resp = solve_result["response"]
            solver_attempted = solve_result["solver_attempted"]
            solver_error = solve_result["solver_error"]
            ohmycaptcha_hint = solve_result["ohmycaptcha_hint"]

            final_is_html = _is_html_response(upstream_resp)
            final_headers, final_body_preview = _format_upstream_error_context(
                upstream_resp
            )
            final_challenge_detected = solve_result["challenge_detected"]
            final_challenge_signals = solve_result["challenge_signals"]
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
                challenge_detected, challenge_signals = detect_upstream_challenge(
                    retry_stream_resp,
                    extra_body_markers=DEMO_CHALLENGE_BODY_MARKERS,
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
