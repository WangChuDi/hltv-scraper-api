from unittest.mock import Mock, patch

from http_client import (
    LIQUIPEDIA_IMPERSONATION_CHAIN,
    build_impersonation_chain,
    detect_cloudflare_challenge,
    get_with_impersonation_fallback,
)


def test_build_impersonation_chain_deduplicates_and_preserves_order():
    assert build_impersonation_chain(
        primary="chrome136", fallbacks=["chrome131", "chrome136", "chrome124"]
    ) == ["chrome136", "chrome131", "chrome124"]


def test_detect_cloudflare_challenge_from_headers_and_body():
    response = Mock()
    response.status_code = 403
    response.headers = {"Server": "cloudflare", "CF-RAY": "abc"}
    response.text = "<html><title>Just a moment...</title></html>"

    assert detect_cloudflare_challenge(response) is True


def test_detect_cloudflare_challenge_ignores_normal_hltv_page_markers():
    response = Mock()
    response.status_code = 200
    response.headers = {"Server": "cloudflare", "CF-RAY": "abc"}
    response.text = (
        '<html lang="en" data-client-country-iso="CN">'
        "https://www.hltv.org/cdn-cgi/challenge-platform "
        "https://www.hltv.org/api/ads/render"
        "</html>"
    )

    assert detect_cloudflare_challenge(response) is False


def test_detect_cloudflare_challenge_ignores_bot_management_cookie_on_normal_page():
    response = Mock()
    response.status_code = 200
    response.headers = {
        "Server": "cloudflare",
        "CF-RAY": "abc",
        "Set-Cookie": "__cf_bm=abc123; path=/; HttpOnly",
    }
    response.text = (
        '<html><div class="teamsBox"></div>'
        '<div id="all-content"></div>'
        '<a class="stream-box" data-demo-link="/download/demo/123"></a></html>'
    )

    detected, signals = detect_cloudflare_challenge(response, return_signals=True)

    assert detected is False
    assert "header:Set-Cookie=__cf_bm" not in signals


def test_streaming_requests_do_not_inspect_response_body():
    response = Mock(status_code=200, headers={"Server": "cloudflare"})
    type(response).text = property(
        lambda self: (_ for _ in ()).throw(AssertionError("body should not be read"))
    )

    with patch("http_client.requests.get", return_value=response):
        result = get_with_impersonation_fallback(
            "https://www.hltv.org/download/demo/123",
            impersonate="chrome136",
            fallback_impersonations=["chrome124"],
            stream=True,
        )

    assert result is response


def test_detect_cloudflare_challenge_ignores_bot_management_cookie_when_body_is_skipped():
    response = Mock()
    response.status_code = 200
    response.headers = {
        "Server": "cloudflare",
        "Set-Cookie": "__cf_bm=abc123; path=/; HttpOnly",
    }

    assert detect_cloudflare_challenge(response, inspect_body=False) is False


def test_detect_cloudflare_challenge_uses_clearance_cookie_when_body_is_skipped():
    response = Mock()
    response.status_code = 200
    response.headers = {
        "Server": "cloudflare",
        "Set-Cookie": "cf_clearance=abc123; path=/; HttpOnly",
    }

    detected, signals = detect_cloudflare_challenge(
        response,
        inspect_body=False,
        return_signals=True,
    )

    assert detected is True
    assert "header:Set-Cookie=cf_clearance" in signals


def test_detect_cloudflare_challenge_can_return_signals_with_extra_markers():
    response = Mock()
    response.status_code = 200
    response.headers = {"Server": "cloudflare"}
    response.text = "<html><body>challenge-platform</body></html>"

    detected, signals = detect_cloudflare_challenge(
        response,
        extra_body_markers=["challenge-platform"],
        return_signals=True,
    )

    assert detected is True
    assert "header:Server=cloudflare" in signals
    assert "body:challenge-platform" in signals


def test_returns_first_successful_response_without_fallback():
    response = Mock(status_code=200, headers={}, text="ok")

    with patch("http_client.requests.get", return_value=response) as mock_get:
        result = get_with_impersonation_fallback(
            "https://www.hltv.org", impersonate="chrome136", timeout=10
        )

    assert result is response
    assert mock_get.call_count == 1
    assert mock_get.call_args.kwargs["impersonate"] == "chrome136"


def test_falls_back_to_next_impersonation_on_cloudflare_block():
    blocked = Mock(
        status_code=403,
        headers={"Server": "cloudflare", "CF-RAY": "abc"},
        text="Just a moment...",
    )
    success = Mock(status_code=200, headers={}, text="ok")

    with patch("http_client.requests.get", side_effect=[blocked, success]) as mock_get:
        result = get_with_impersonation_fallback(
            "https://www.hltv.org",
            impersonate="chrome136",
            fallback_impersonations=["chrome131", "chrome124"],
            timeout=10,
        )

    assert result is success
    assert mock_get.call_count == 2
    assert mock_get.call_args_list[0].kwargs["impersonate"] == "chrome136"
    assert mock_get.call_args_list[1].kwargs["impersonate"] == "chrome131"


def test_falls_back_to_next_impersonation_on_exception():
    success = Mock(status_code=200, headers={}, text="ok")

    with patch(
        "http_client.requests.get", side_effect=[TimeoutError("blocked"), success]
    ) as mock_get:
        result = get_with_impersonation_fallback(
            "https://www.hltv.org",
            impersonate="chrome136",
            fallback_impersonations=["chrome131"],
            timeout=10,
        )

    assert result is success
    assert mock_get.call_count == 2
    assert mock_get.call_args_list[1].kwargs["impersonate"] == "chrome131"


def test_uses_validate_response_to_trigger_fallback():
    first = Mock(status_code=200, headers={}, text="bad")
    second = Mock(status_code=200, headers={}, text="good")

    with patch("http_client.requests.get", side_effect=[first, second]) as mock_get:
        result = get_with_impersonation_fallback(
            "https://www.hltv.org/search?term=test",
            impersonate="chrome124",
            fallback_impersonations=["chrome136"],
            timeout=10,
            validate_response=lambda resp: resp.text == "good",
        )

    assert result is second
    assert mock_get.call_count == 2


def test_preserves_request_kwargs_across_attempts():
    blocked = Mock(
        status_code=503, headers={"Server": "cloudflare"}, text="challenge-platform"
    )
    success = Mock(status_code=200, headers={}, text="ok")

    with patch("http_client.requests.get", side_effect=[blocked, success]) as mock_get:
        get_with_impersonation_fallback(
            "https://www.hltv.org/download/demo/123",
            impersonate="chrome136",
            fallback_impersonations=["chrome124"],
            stream=True,
            headers={"Referer": "https://www.hltv.org"},
        )

    assert mock_get.call_args_list[0].kwargs["stream"] is True
    assert mock_get.call_args_list[1].kwargs["stream"] is True
    assert mock_get.call_args_list[1].kwargs["headers"] == {
        "Referer": "https://www.hltv.org"
    }


def test_raises_last_exception_when_all_attempts_fail():
    with patch(
        "http_client.requests.get",
        side_effect=[TimeoutError("first"), TimeoutError("second")],
    ):
        try:
            get_with_impersonation_fallback(
                "https://www.hltv.org",
                impersonate="chrome136",
                fallback_impersonations=["chrome131"],
            )
        except TimeoutError as exc:
            assert str(exc) == "second"
        else:
            raise AssertionError("Expected TimeoutError")


def test_liquipedia_chain_is_configured():
    assert LIQUIPEDIA_IMPERSONATION_CHAIN
