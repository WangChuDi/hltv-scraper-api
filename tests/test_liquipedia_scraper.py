from unittest.mock import Mock, patch

from liquipedia_scraper import (
    LIQUIPEDIA_IMPERSONATION_CHAIN,
    get_completed_tournaments,
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


def test_get_ongoing_tournaments_returns_empty_on_non_200_response():
    response = Mock()
    response.status_code = 403
    response.content = b"<html><body>Blocked by upstream</body></html>"

    with patch(
        "liquipedia_scraper.get_with_impersonation_fallback", return_value=response
    ):
        tournaments = get_ongoing_tournaments()

    assert tournaments == []


def test_get_completed_tournaments_prefers_live_main_page_s_tier_results():
    response = Mock()
    response.status_code = 200
    response.content = b"""<html><body>
        <div>Concluded IEM Rio 2026 should not be parsed from loose page text</div>
        <div data-filter-effect="fade" data-filter-hideable-group>
            <span class="tournaments-list-heading">Completed</span>
            <ul class="tournaments-list-type-list">
                <li>
                    <div>S-Tier</div>
                    <span class="tournaments-list-name">
                        <span class="tournament-name"><a href="/counterstrike/Intel_Extreme_Masters/2026/Rio">IEM Rio 2026</a></span>
                    </span>
                </li>
                <li>
                    <div>A-Tier</div>
                    <span class="tournaments-list-name">
                        <span class="tournament-name"><a href="/counterstrike/PGL/2026/Bucharest">PGL Bucharest 2026</a></span>
                    </span>
                </li>
                <li>
                    <div>S-Tier</div>
                    <span class="tournaments-list-name">
                        <span class="tournament-name"><a href="/counterstrike/ESL/Pro_League/Season_23">ESL Pro League S23 Finals</a></span>
                    </span>
                </li>
                <li>
                    <div>S-Tier</div>
                    <span class="tournaments-list-name">
                        <span class="tournament-name"><a href="/counterstrike/Intel_Extreme_Masters/2026/Rio">IEM Rio 2026</a></span>
                    </span>
                </li>
            </ul>
        </div>
    </body></html>"""

    with patch(
        "liquipedia_scraper.get_with_impersonation_fallback", return_value=response
    ) as mock_fetch:
        tournaments = get_completed_tournaments()

    assert tournaments == ["IEM Rio 2026", "ESL Pro League S23 Finals"]
    assert mock_fetch.call_count == 1
    assert (
        mock_fetch.call_args.args[0] == "https://liquipedia.net/counterstrike/Main_Page"
    )
    assert mock_fetch.call_args.kwargs["impersonate"] == "chrome"
    assert mock_fetch.call_args.kwargs["timeout"] == 10
    assert (
        mock_fetch.call_args.kwargs["fallback_impersonations"]
        == LIQUIPEDIA_IMPERSONATION_CHAIN
    )


def test_get_completed_tournaments_falls_back_when_live_scrape_is_empty():
    response = Mock()
    response.status_code = 200
    response.content = b"<html><body><div data-filter-effect=\"fade\" data-filter-hideable-group><span class=\"tournaments-list-heading\">Completed</span><ul class=\"tournaments-list-type-list\"></ul></div></body></html>"

    with patch(
        "liquipedia_scraper.get_with_impersonation_fallback", return_value=response
    ):
        tournaments = get_completed_tournaments()

    assert tournaments == [
        "ESL Pro League Season 23 Finals",
        "BLAST Premier World Final 2025",
        "IEM Katowice 2026",
        "PGL Major Copenhagen 2025",
        "BLAST Premier Fall Final 2025",
    ]


def test_get_completed_tournaments_falls_back_on_fetch_error():
    with patch(
        "liquipedia_scraper.get_with_impersonation_fallback",
        side_effect=RuntimeError("upstream blocked"),
    ):
        tournaments = get_completed_tournaments()

    assert tournaments == [
        "ESL Pro League Season 23 Finals",
        "BLAST Premier World Final 2025",
        "IEM Katowice 2026",
        "PGL Major Copenhagen 2025",
        "BLAST Premier Fall Final 2025",
    ]
