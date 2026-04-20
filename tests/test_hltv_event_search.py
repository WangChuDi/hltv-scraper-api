from unittest.mock import Mock, patch

from hltv_event_search import (
    get_event_with_grouped_events,
    get_hltv_event_metadata,
    get_live_box_event,
)


def test_get_live_box_event_returns_none_on_non_200_response():
    response = Mock()
    response.status_code = 403
    response.content = b"<html><body>blocked</body></html>"

    with patch("hltv_event_search.get_with_impersonation_fallback", return_value=response):
        result = get_live_box_event()

    assert result is None


def test_get_hltv_event_metadata_returns_none_on_non_200_response():
    response = Mock()
    response.status_code = 403
    response.content = b"<html><body>blocked</body></html>"

    with patch("hltv_event_search.get_with_impersonation_fallback", return_value=response):
        result = get_hltv_event_metadata("/events/123/test-event")

    assert result is None


def test_get_event_with_grouped_events_returns_none_on_non_200_response():
    response = Mock()
    response.status_code = 503
    response.content = b"<html><body>unavailable</body></html>"

    with patch("hltv_event_search.get_with_impersonation_fallback", return_value=response):
        result = get_event_with_grouped_events("/events/123/test-event")

    assert result is None
