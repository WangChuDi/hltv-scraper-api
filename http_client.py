import os
from typing import Any, Callable

from curl_cffi import requests


HLTV_IMPERSONATION_CHAIN = tuple(
    value.strip()
    for value in os.getenv(
        "HLTV_IMPERSONATION_CHAIN", "chrome136,chrome131,chrome124"
    ).split(",")
    if value.strip()
)

LIQUIPEDIA_IMPERSONATION_CHAIN = tuple(
    value.strip()
    for value in os.getenv(
        "LIQUIPEDIA_IMPERSONATION_CHAIN", "chrome,chrome136,chrome131"
    ).split(",")
    if value.strip()
)

FALLBACK_RETRY_STATUSES = {403, 429, 503}
CHALLENGE_BODY_MARKERS = [
    "just a moment",
    "checking your browser",
    "attention required",
    "cf-browser-verification",
    "window._cf_chl_opt",
    "please enable javascript and cookies",
]
CHALLENGE_COOKIE_MARKERS = ("cf_clearance", "__cf_bm", "cf_chl_")


def _dedupe_preserve_order(values):
    seen = set()
    result = []
    for value in values:
        normalized = (value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def build_impersonation_chain(primary=None, fallbacks=None):
    return _dedupe_preserve_order([primary, *(fallbacks or [])])


def detect_cloudflare_challenge(
    response,
    *,
    inspect_body=True,
    extra_body_markers=None,
    return_signals=False,
):
    if response is None:
        return (False, []) if return_signals else False

    status_code = getattr(response, "status_code", None)
    headers = getattr(response, "headers", {}) or {}

    server = str(headers.get("Server") or "").lower()
    cf_ray = headers.get("CF-RAY")
    set_cookie = str(headers.get("Set-Cookie") or "").lower()
    body_markers = [*CHALLENGE_BODY_MARKERS, *(extra_body_markers or [])]
    signals = []

    if status_code in FALLBACK_RETRY_STATUSES:
        signals.append(f"status:{status_code}")
    if cf_ray:
        signals.append("header:CF-RAY")
    if "cloudflare" in server:
        signals.append("header:Server=cloudflare")

    body_preview = ""
    if inspect_body:
        try:
            body_preview = " ".join((response.text or "").split()).lower()
        except Exception:
            body_preview = ""

    marker_hits = [marker for marker in body_markers if marker in body_preview]
    for marker in marker_hits:
        signals.append(f"body:{marker}")

    has_cf_cookie_signal = any(
        cookie_marker in set_cookie for cookie_marker in CHALLENGE_COOKIE_MARKERS
    )
    if has_cf_cookie_signal:
        if "cf_clearance" in set_cookie:
            signals.append("header:Set-Cookie=cf_clearance")
        elif "__cf_bm" in set_cookie:
            signals.append("header:Set-Cookie=__cf_bm")
        else:
            signals.append("header:Set-Cookie=cf_chl_")

    has_cf_headers = bool(cf_ray) or "cloudflare" in server or has_cf_cookie_signal

    if status_code in FALLBACK_RETRY_STATUSES:
        detected = True
    elif inspect_body:
        detected = bool(marker_hits) or (has_cf_headers and has_cf_cookie_signal)
    else:
        detected = has_cf_headers and has_cf_cookie_signal

    if return_signals:
        deduped_signals = list(dict.fromkeys(signals))
        return detected, deduped_signals

    return detected


def is_retryable_response(response, *, inspect_body=True):
    status_code = getattr(response, "status_code", None)
    if status_code in FALLBACK_RETRY_STATUSES:
        return True
    return detect_cloudflare_challenge(response, inspect_body=inspect_body)


def get_with_impersonation_fallback(
    url,
    *,
    impersonate=None,
    fallback_impersonations=None,
    timeout=None,
    validate_response: Callable[[Any], bool] | None = None,
    **request_kwargs,
):
    impersonation_chain = build_impersonation_chain(
        primary=impersonate,
        fallbacks=fallback_impersonations,
    )

    if not impersonation_chain:
        return requests.get(url, timeout=timeout, **request_kwargs)

    last_response = None
    last_exception = None

    for current_impersonate in impersonation_chain:
        try:
            response = requests.get(
                url,
                impersonate=current_impersonate,
                timeout=timeout,
                **request_kwargs,
            )
        except Exception as exc:
            last_exception = exc
            continue

        last_response = response
        if validate_response is not None:
            if validate_response(response):
                return response
            continue

        inspect_body = not bool(request_kwargs.get("stream"))
        if not is_retryable_response(response, inspect_body=inspect_body):
            return response

    if last_response is not None:
        return last_response

    if last_exception is not None:
        raise last_exception

    raise RuntimeError(f"Failed to fetch URL with impersonation fallback: {url}")
