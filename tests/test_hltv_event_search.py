from unittest.mock import Mock, patch

import hltv_event_search

from hltv_event_search import (
    find_event_by_id,
    get_event_with_grouped_events,
    get_hltv_event_metadata,
    get_live_box_event,
    search_events,
)


def _clear_event_by_id_cache():
    hltv_event_search._EVENT_BY_ID_CACHE.clear()


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


def test_search_events_falls_back_to_html_when_json_payload_shape_is_unexpected():
    search_response = Mock()
    search_response.status_code = 200
    search_response.json.return_value = [123, {"events": "not-a-list"}]

    events_response = Mock()
    events_response.status_code = 200
    events_response.content = (
        b"<html><body>"
        b'<a href="/events/8048/pgl-bucharest-2026"><div class="text-ellipsis">PGL Bucharest 2026</div></a>'
        b"</body></html>"
    )

    archive_response = Mock()
    archive_response.status_code = 200
    archive_response.content = b"<html><body></body></html>"

    with patch("hltv_event_search.get_with_impersonation_fallback") as mock_get:
        mock_get.side_effect = [search_response, events_response, archive_response]

        results = search_events("PGL Bucharest 2026")

    assert len(results) == 1
    assert results[0]["event_id"] == "8048"
    assert results[0]["url"] == "/events/8048/pgl-bucharest-2026"
    assert mock_get.call_count == 3


def test_search_events_accepts_dict_json_payload_shape():
    search_response = Mock()
    search_response.status_code = 200
    search_response.json.return_value = {
        "events": [
            {
                "id": 8242,
                "name": "IEM Rio 2026",
                "location": "/events/8242/iem-rio-2026",
            }
        ]
    }

    with patch("hltv_event_search.get_with_impersonation_fallback", return_value=search_response) as mock_get:
        results = search_events("IEM Rio 2026")

    assert len(results) == 1
    assert results[0]["event_id"] == "8242"
    assert results[0]["url"] == "/events/8242/iem-rio-2026"
    assert mock_get.call_count == 1


def test_search_events_accepts_list_json_payload_shape_with_link():
    search_response = Mock()
    search_response.status_code = 200
    search_response.json.return_value = [
        {
            "id": 8048,
            "name": "PGL Bucharest 2026",
            "link": "https://www.hltv.org/events/8048/pgl-bucharest-2026",
        }
    ]

    with patch("hltv_event_search.get_with_impersonation_fallback", return_value=search_response) as mock_get:
        results = search_events("PGL Bucharest 2026")

    assert len(results) == 1
    assert results[0]["event_id"] == "8048"
    assert results[0]["url"] == "/events/8048/pgl-bucharest-2026"
    assert mock_get.call_count == 1


def test_find_event_by_id_uses_archive_offset_pagination():
    _clear_event_by_id_cache()

    search_response = Mock()
    search_response.status_code = 200
    search_response.json.return_value = []

    events_response = Mock()
    events_response.status_code = 200
    events_response.content = b"<html><body></body></html>"

    archive_offset_0_response = Mock()
    archive_offset_0_response.status_code = 200
    archive_offset_0_response.content = (
        b"<html><body>"
        b'<a href="/events/9000/not-it">Not It</a>'
        b"</body></html>"
    )

    archive_offset_50_response = Mock()
    archive_offset_50_response.status_code = 200
    archive_offset_50_response.content = (
        b"<html><body>"
        b'<a href="/events/8048/pgl-bucharest-2026">PGL Bucharest 2026</a>'
        b"</body></html>"
    )

    with patch("hltv_event_search.get_with_impersonation_fallback") as mock_get:
        mock_get.side_effect = [
            search_response,
            events_response,
            archive_offset_0_response,
            archive_offset_50_response,
        ]

        result = find_event_by_id(8048)

    assert result is not None
    assert result["event_id"] == "8048"
    called_urls = [call.args[0] for call in mock_get.call_args_list]
    assert any("offset=0" in url for url in called_urls)
    assert any("offset=50" in url for url in called_urls)


def test_find_event_by_id_uses_positive_cache_for_repeat_lookup():
    _clear_event_by_id_cache()

    search_response = Mock()
    search_response.status_code = 200
    search_response.json.return_value = []

    events_response = Mock()
    events_response.status_code = 200
    events_response.content = b"<html><body></body></html>"

    archive_offset_0_response = Mock()
    archive_offset_0_response.status_code = 200
    archive_offset_0_response.content = (
        b"<html><body>"
        b'<a href="/events/9000/not-it">Not It</a>'
        b"</body></html>"
    )

    archive_offset_50_response = Mock()
    archive_offset_50_response.status_code = 200
    archive_offset_50_response.content = (
        b"<html><body>"
        b'<a href="/events/8048/pgl-bucharest-2026">PGL Bucharest 2026</a>'
        b"</body></html>"
    )

    with patch("hltv_event_search.get_with_impersonation_fallback") as mock_get:
        mock_get.side_effect = [
            search_response,
            events_response,
            archive_offset_0_response,
            archive_offset_50_response,
        ]

        result_first = find_event_by_id(8048)
        result_second = find_event_by_id(8048)

    assert result_first is not None
    assert result_second == result_first
    assert mock_get.call_count == 4


def test_find_event_by_id_caches_search_payload_hits():
    _clear_event_by_id_cache()

    search_response = Mock()
    search_response.status_code = 200
    search_response.json.return_value = {
        "events": [
            {
                "id": 8048,
                "name": "PGL Bucharest 2026",
                "location": "/events/8048/pgl-bucharest-2026",
            }
        ]
    }

    with patch(
        "hltv_event_search.get_with_impersonation_fallback",
        return_value=search_response,
    ) as mock_get:
        result_first = find_event_by_id(8048)
        result_second = find_event_by_id(8048)

    assert result_first is not None
    assert result_second == result_first
    assert mock_get.call_count == 1


def test_find_event_by_id_ignores_match_listing_search_paths_and_falls_back():
    _clear_event_by_id_cache()

    search_response = Mock()
    search_response.status_code = 200
    search_response.json.return_value = {
        "events": [
            {
                "id": 8048,
                "name": "PGL Bucharest 2026",
                "eventMatchesLocation": "/events/8048/matches",
            }
        ]
    }

    events_response = Mock()
    events_response.status_code = 200
    events_response.content = (
        b"<html><body>"
        b'<a href="/events/8048/pgl-bucharest-2026">PGL Bucharest 2026</a>'
        b"</body></html>"
    )

    with patch(
        "hltv_event_search.get_with_impersonation_fallback",
        side_effect=[search_response, events_response],
    ) as mock_get:
        result = find_event_by_id(8048)

    assert result is not None
    assert result["event_id"] == "8048"
    assert result["url"] == "/events/8048/pgl-bucharest-2026"
    assert mock_get.call_count == 2


def test_find_event_by_id_pages_archive_until_empty():
    _clear_event_by_id_cache()

    search_response = Mock()
    search_response.status_code = 200
    search_response.json.return_value = []

    events_response = Mock()
    events_response.status_code = 200
    events_response.content = b"<html><body></body></html>"

    archive_offset_0_response = Mock()
    archive_offset_0_response.status_code = 200
    archive_offset_0_response.content = (
        b"<html><body>"
        b'<a href="/events/9000/not-it">Not It</a>'
        b"</body></html>"
    )

    archive_offset_50_response = Mock()
    archive_offset_50_response.status_code = 200
    archive_offset_50_response.content = (
        b"<html><body>"
        b'<a href="/events/8048/pgl-bucharest-2026">PGL Bucharest 2026</a>'
        b"</body></html>"
    )

    archive_offset_100_response = Mock()
    archive_offset_100_response.status_code = 200
    archive_offset_100_response.content = b"<html><body></body></html>"

    with patch("hltv_event_search.get_with_impersonation_fallback") as mock_get:
        mock_get.side_effect = [
            search_response,
            events_response,
            archive_offset_0_response,
            archive_offset_50_response,
            archive_offset_100_response,
        ]

        result = find_event_by_id(999999)

    assert result is None
    called_urls = [call.args[0] for call in mock_get.call_args_list]
    assert any("offset=0" in url for url in called_urls)
    assert any("offset=50" in url for url in called_urls)
    assert any("offset=100" in url for url in called_urls)


def test_find_event_by_id_scans_older_archive_years():
    _clear_event_by_id_cache()

    search_response = Mock()
    search_response.status_code = 200
    search_response.json.return_value = []

    events_response = Mock()
    events_response.status_code = 200
    events_response.content = b"<html><body></body></html>"

    with patch("hltv_event_search.get_with_impersonation_fallback") as mock_get:
        mock_get.side_effect = [search_response, events_response]

        with patch("hltv_event_search.datetime.datetime") as mock_datetime:
            mock_datetime.now.return_value = Mock(year=2026)

            with patch(
                "hltv_event_search._iter_archive_links_for_year",
                side_effect=lambda year: iter(
                    [
                        (
                            "/events/8048/pgl-bucharest-2026",
                            "PGL Bucharest 2026",
                        )
                    ]
                    if year == 2018
                    else []
                ),
            ):
                result = find_event_by_id(8048)

    assert result is not None
    assert result["event_id"] == "8048"


def test_find_event_by_id_does_not_cache_misses():
    _clear_event_by_id_cache()

    search_response = Mock()
    search_response.status_code = 200
    search_response.json.return_value = []

    events_response = Mock()
    events_response.status_code = 200
    events_response.content = b"<html><body></body></html>"

    with patch(
        "hltv_event_search.get_with_impersonation_fallback",
        side_effect=[search_response, events_response, search_response, events_response],
    ) as mock_get:
        with patch("hltv_event_search._fetch_archive_links_for_year", return_value=[]):
            result_first = find_event_by_id(123456)
            result_second = find_event_by_id(123456)

    assert result_first is None
    assert result_second is None
    assert mock_get.call_count == 4
