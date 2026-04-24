from unittest.mock import Mock, patch

from hltv_event_scraper import get_event_details


def test_get_event_details_returns_none_on_non_200_response():
    response = Mock()
    response.status_code = 429
    response.content = b"<html><body>rate limited</body></html>"

    with patch(
        "hltv_event_scraper.get_with_impersonation_fallback", return_value=response
    ) as mock_get:
        result = get_event_details("/events/123/test-event")

    assert result is None
    assert mock_get.call_args.kwargs["impersonate"] == "chrome136"
