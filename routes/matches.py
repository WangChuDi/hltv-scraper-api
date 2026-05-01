from typing import Literal
from flask import Blueprint, Response, jsonify
from flasgger import swag_from

from hltv_scraper import HLTVScraper
from http_client import (
    HLTV_IMPERSONATION_CHAIN,
    get_with_impersonation_fallback,
)
from routes.challenge_helpers import (
    _build_ohmycaptcha_hint,
    detect_upstream_challenge,
    solve_upstream_turnstile,
)

matches_bp = Blueprint("matches", __name__, url_prefix="/api/v1/matches")

MATCH_CHALLENGE_BODY_MARKERS = (
    "challenge-platform",
    "cdn-cgi/challenge-platform",
    "cf-mitigated",
    "cf-challenge",
)


def _request_hltv_match_page(target_url, turnstile_token=None):
    headers = None
    if turnstile_token:
        headers = {
            "cf-turnstile-response": turnstile_token,
            "x-turnstile-token": turnstile_token,
            "Referer": target_url,
        }

    return get_with_impersonation_fallback(
        target_url,
        impersonate="chrome136",
        fallback_impersonations=HLTV_IMPERSONATION_CHAIN,
        timeout=10,
        headers=headers,
    )


def _processing_match_detail_response(target_url, retry_after):
    response = jsonify(
        {
            "status": "processing",
            "message": "Match details are being fetched",
            "retry_after": retry_after,
            "target_url": target_url,
        }
    )
    response.status_code = 202
    response.headers["Retry-After"] = str(retry_after)
    return response


def _failed_match_detail_upstream_response(target_url):
    upstream_resp = _request_hltv_match_page(target_url)
    solve_result = solve_upstream_turnstile(
        upstream_resp,
        target_url=target_url,
        request_with_token=lambda token: _request_hltv_match_page(
            target_url,
            turnstile_token=token,
        ),
        extra_body_markers=MATCH_CHALLENGE_BODY_MARKERS,
        missing_config_reason=(
            "Cloudflare challenge detected, but OHMYCAPTCHA_BASE_URL / "
            "OHMYCAPTCHA_CLIENT_KEY are not fully configured"
        ),
    )

    upstream_resp = solve_result["response"]
    challenge_detected = solve_result["challenge_detected"]
    challenge_signals = solve_result["challenge_signals"]
    solver_error = solve_result["solver_error"]
    ohmycaptcha_hint = solve_result["ohmycaptcha_hint"]

    upstream_status_code = getattr(upstream_resp, "status_code", None)
    if isinstance(upstream_status_code, bool):
        normalized_status_code = 502
    elif isinstance(upstream_status_code, int):
        normalized_status_code = upstream_status_code
    elif isinstance(upstream_status_code, str):
        try:
            normalized_status_code = int(upstream_status_code)
        except ValueError:
            normalized_status_code = 502
    else:
        normalized_status_code = 502

    error_status = normalized_status_code if normalized_status_code != 200 else 502
    error_message = (
        f"Failed to fetch match details: HLTV returned {normalized_status_code}"
    )
    if challenge_detected:
        error_message += " challenge page"
    payload = {
        "status": "failed",
        "error": error_message,
        "challenge_detected": challenge_detected,
        "challenge_signals": challenge_signals,
        "target_url": target_url,
    }
    if solver_error:
        payload["solver_error"] = solver_error
    if ohmycaptcha_hint:
        payload["ohmycaptcha_hint"] = ohmycaptcha_hint
    return jsonify(payload), error_status


def _failed_match_detail_state_response(target_url, state):
    retry_after_raw = state.get("retry_after")
    if isinstance(retry_after_raw, bool):
        retry_after = 2
    elif isinstance(retry_after_raw, int):
        retry_after = retry_after_raw if retry_after_raw > 0 else 2
    elif isinstance(retry_after_raw, str):
        try:
            retry_after = int(retry_after_raw)
        except ValueError:
            retry_after = 2
        else:
            retry_after = retry_after if retry_after > 0 else 2
    else:
        retry_after = 2
    payload = {
        "status": "failed",
        "error": state.get("error") or "Failed to fetch match details",
        "message": state.get("message") or "Background spider failed",
        "retry_after": retry_after,
        "target_url": target_url,
    }
    response = jsonify(payload)
    response.status_code = 500
    response.headers["Retry-After"] = str(retry_after)
    return response

@matches_bp.route("/upcoming", methods=["GET"])
@swag_from('../swagger_specs/matches_upcoming.yml')
def upcoming_matches() -> Response | tuple[Response, Literal[500]]:
    """Get upcoming matches from HLTV."""
    try:
        data = HLTVScraper.get_upcoming_matches()
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@matches_bp.route("/<string:id>/<string:match_name>", methods=["GET"])
@swag_from('../swagger_specs/matches_detail.yml')
def match(id: str, match_name: str) -> Response | tuple[Response, int]:
    """Get match details from HLTV."""
    try:
        target_url = f"https://www.hltv.org/matches/{id}/{match_name}"
        state = HLTVScraper.get_match_state(id, match_name)
        if state.get("status") == "processing":
            retry_after_raw = state.get("retry_after")
            if isinstance(retry_after_raw, bool):
                retry_after = 2
            elif isinstance(retry_after_raw, int):
                retry_after = retry_after_raw if retry_after_raw > 0 else 2
            elif isinstance(retry_after_raw, str):
                try:
                    retry_after = int(retry_after_raw)
                except ValueError:
                    retry_after = 2
                else:
                    retry_after = retry_after if retry_after > 0 else 2
            else:
                retry_after = 2
            return _processing_match_detail_response(target_url, retry_after)

        if state.get("status") == "failed":
            return _failed_match_detail_state_response(target_url, state)

        data = state.get("data")
        if isinstance(data, list) and not data:
            return _failed_match_detail_upstream_response(target_url)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
