from unittest.mock import Mock, patch

from liquipedia_scraper import (
    LIQUIPEDIA_IMPERSONATION_CHAIN,
    get_ongoing_tournaments,
)


def test_get_ongoing_tournaments_does_not_override_user_agent_header():
    response = Mock()
    response.status_code = 200
    response.content = b"<html><body>Ongoing\nIEM Rio 2026\nConcluded</body></html>"

    with patch(
        "liquipedia_scraper.get_with_impersonation_fallback", return_value=response
    ) as mock_fetch:
        tournaments = get_ongoing_tournaments()

    assert tournaments == ["IEM Rio 2026"]
    assert mock_fetch.call_count == 1
    assert (
        mock_fetch.call_args.args[0] == "https://liquipedia.net/counterstrike/Main_Page"
    )
    assert mock_fetch.call_args.kwargs["timeout"] == 10
    assert (
        mock_fetch.call_args.kwargs["fallback_impersonations"]
        == LIQUIPEDIA_IMPERSONATION_CHAIN
    )
    assert "headers" not in mock_fetch.call_args.kwargs


def test_get_ongoing_tournaments_filters_noise_from_successful_page():
    response = Mock()
    response.status_code = 200
    response.content = b"""<html><body>
        Ongoing
        IEM Rio 2026
        Edit
        BLAST Open London 2026
        Twitter
        Concluded
    </body></html>"""

    with patch(
        "liquipedia_scraper.get_with_impersonation_fallback", return_value=response
    ):
        tournaments = get_ongoing_tournaments()

    assert tournaments == ["IEM Rio 2026", "BLAST Open London 2026"]


def test_get_ongoing_tournaments_returns_empty_when_markers_missing():
    response = Mock()
    response.status_code = 200
    response.content = b"<html><body>No tournament markers here</body></html>"

    with patch(
        "liquipedia_scraper.get_with_impersonation_fallback", return_value=response
    ):
        tournaments = get_ongoing_tournaments()

    assert tournaments == []
