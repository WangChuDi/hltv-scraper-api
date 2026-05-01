import os
import re
import time

from curl_cffi import requests

from http_client import detect_cloudflare_challenge

OHMYCAPTCHA_ENV_HINT = {
    "OHMYCAPTCHA_BASE_URL": "http://127.0.0.1:8004",
    "OHMYCAPTCHA_CLIENT_KEY": "<your-client-key>",
    "OHMYCAPTCHA_TASK_TYPE": "TurnstileTaskProxyless",
    "OHMYCAPTCHA_TURNSTILE_SITEKEY": "<optional-sitekey>",
}


def detect_upstream_challenge(upstream_resp, *, extra_body_markers=()):
    return detect_cloudflare_challenge(
        upstream_resp,
        inspect_body=True,
        extra_body_markers=extra_body_markers,
        return_signals=True,
    )


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


def solve_upstream_turnstile(
    upstream_resp,
    *,
    target_url,
    request_with_token,
    extra_body_markers=(),
    missing_config_reason,
):
    challenge_detected, challenge_signals = detect_upstream_challenge(
        upstream_resp,
        extra_body_markers=extra_body_markers,
    )

    solver_attempted = False
    solver_error = None
    ohmycaptcha_hint = None
    final_resp = upstream_resp

    if challenge_detected and _is_ohmycaptcha_configured():
        sitekey = _extract_turnstile_sitekey(upstream_resp.text or "")
        if not sitekey:
            sitekey = os.getenv("OHMYCAPTCHA_TURNSTILE_SITEKEY", "").strip()
        if sitekey:
            solver_attempted = True
            try:
                token = _solve_turnstile_token(target_url, sitekey)
                final_resp = request_with_token(token)
            except Exception as exc:
                solver_error = str(exc)
        else:
            solver_error = (
                "Cloudflare challenge detected but no Turnstile sitekey was found "
                "(neither in response body nor OHMYCAPTCHA_TURNSTILE_SITEKEY)"
            )
    elif challenge_detected:
        ohmycaptcha_hint = _build_ohmycaptcha_hint(missing_config_reason)

    final_challenge_detected, final_challenge_signals = detect_upstream_challenge(
        final_resp,
        extra_body_markers=extra_body_markers,
    )

    return {
        "response": final_resp,
        "challenge_detected": final_challenge_detected,
        "challenge_signals": final_challenge_signals,
        "solver_attempted": solver_attempted,
        "solver_error": solver_error,
        "ohmycaptcha_hint": ohmycaptcha_hint,
    }
