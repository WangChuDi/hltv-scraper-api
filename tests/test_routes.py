import json
from unittest.mock import Mock, patch

from scrapy.http import HtmlResponse

from hltv_scraper.hltv_scraper.spiders.parsers.match_teams_box import (
    MatchTeamsBoxParser,
)


class TestRoutesEndpoints:
    """Tests for all API route endpoints."""

    def test_demo_download_logs_upstream_403_context(self, client, app, caplog):
        upstream_response = Mock()
        upstream_response.status_code = 403
        upstream_response.headers = {
            "Content-Type": "text/html; charset=UTF-8",
            "CF-RAY": "abc123",
            "Set-Cookie": "cf_clearance=very-long-cookie-value" * 20,
        }
        upstream_response.text = (
            "<html><title>Just a moment...</title><body>Forbidden</body></html>"
        )

        with app.app_context():
            with patch.dict(
                "os.environ",
                {
                    "OHMYCAPTCHA_BASE_URL": "",
                    "OHMYCAPTCHA_CLIENT_KEY": "",
                    "OHMYCAPTCHA_TURNSTILE_SITEKEY": "",
                },
                clear=False,
            ):
                with patch("routes.demos.requests.get", return_value=upstream_response):
                    with caplog.at_level("WARNING"):
                        response = client.get("/api/v1/download/demo/105805")

        assert response.status_code == 403
        data = json.loads(response.data)
        assert data["error"] == "Failed to fetch demo: HLTV returned 403"
        assert data["challenge_detected"] is True
        assert data["solver_attempted"] is False
        assert "ohmycaptcha_hint" in data
        assert "set_env" in data["ohmycaptcha_hint"]["how_to_enable"]
        assert (
            data["ohmycaptcha_hint"]["how_to_enable"]["set_env"]["OHMYCAPTCHA_BASE_URL"]
            == "http://127.0.0.1:8004"
        )
        assert "challenge_signals" in data
        assert any(
            signal.startswith("status:403") for signal in data["challenge_signals"]
        )
        assert any(
            signal.startswith("header:CF-RAY") for signal in data["challenge_signals"]
        )
        assert any(
            signal.startswith("body:just a moment")
            for signal in data["challenge_signals"]
        )
        assert "HLTV demo download failed" in caplog.text
        assert "demo_id=105805" in caplog.text
        assert "status=403" in caplog.text
        assert "CF-RAY" in caplog.text
        assert "body_preview" in caplog.text
        assert "Just a moment..." in caplog.text

    def test_demo_download_detects_challenge_with_200_interstitial(self, client, app):
        upstream_response = Mock()
        upstream_response.status_code = 200
        upstream_response.headers = {
            "Content-Type": "text/html; charset=UTF-8",
            "Server": "cloudflare",
        }
        upstream_response.text = "<html><script>window._cf_chl_opt={};</script></html>"

        with app.app_context():
            with patch("routes.demos.requests.get", return_value=upstream_response):
                response = client.get("/api/v1/download/demo/105805")

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["error"] == "Failed to fetch demo: HLTV returned 200"
        assert data["challenge_detected"] is True
        assert data["solver_attempted"] is False
        assert any(
            signal.startswith("body:window._cf_chl_opt")
            for signal in data["challenge_signals"]
        )

    def test_demo_download_falls_back_to_env_sitekey(self, client, app):
        challenge_response = Mock()
        challenge_response.status_code = 403
        challenge_response.headers = {
            "Content-Type": "text/html; charset=UTF-8",
            "CF-RAY": "abc123",
        }
        challenge_response.text = (
            "<html><title>Just a moment...</title><body>challenge</body></html>"
        )

        download_response = Mock()
        download_response.status_code = 200
        download_response.headers = {
            "Content-Type": "application/x-rar-compressed",
            "Content-Length": "4",
            "Content-Disposition": 'attachment; filename="demo.rar"',
        }
        download_response.iter_content.return_value = [b"demo"]

        with app.app_context():
            with patch("routes.demos._solve_turnstile_token", return_value="token123"):
                with patch(
                    "routes.demos.requests.get",
                    side_effect=[challenge_response, download_response],
                ) as mock_get:
                    with patch.dict(
                        "os.environ",
                        {
                            "OHMYCAPTCHA_BASE_URL": "http://127.0.0.1:8004",
                            "OHMYCAPTCHA_TURNSTILE_SITEKEY": "sitekey-from-env",
                        },
                        clear=False,
                    ):
                        response = client.get("/api/v1/download/demo/105805")

        assert response.status_code == 200
        assert mock_get.call_count == 2

    def test_demo_download_hint_absent_when_ohmycaptcha_configured(self, client, app):
        challenge_response = Mock()
        challenge_response.status_code = 403
        challenge_response.headers = {
            "Content-Type": "text/html; charset=UTF-8",
            "CF-RAY": "abc123",
        }
        challenge_response.text = (
            "<html><title>Just a moment...</title><body>challenge</body></html>"
        )

        with app.app_context():
            with patch("routes.demos.requests.get", return_value=challenge_response):
                with patch.dict(
                    "os.environ",
                    {
                        "OHMYCAPTCHA_BASE_URL": "http://127.0.0.1:8004",
                        "OHMYCAPTCHA_CLIENT_KEY": "configured-client-key",
                    },
                    clear=False,
                ):
                    response = client.get("/api/v1/download/demo/105805")

        assert response.status_code == 403
        data = json.loads(response.data)
        assert data["solver_attempted"] is False
        assert "ohmycaptcha_hint" not in data

    def test_demo_download_uses_configured_impersonate(self, client, app):
        upstream_response = Mock()
        upstream_response.status_code = 200
        upstream_response.headers = {
            "Content-Type": "application/x-rar-compressed",
            "Content-Length": "4",
            "Content-Disposition": 'attachment; filename="demo.rar"',
        }
        upstream_response.iter_content.return_value = [b"demo"]

        with app.app_context():
            with patch("routes.demos.DEFAULT_HLTV_DEMO_IMPERSONATE", "chrome124"):
                with patch(
                    "routes.demos.requests.get", return_value=upstream_response
                ) as mock_get:
                    response = client.get("/api/v1/download/demo/105805")

        assert response.status_code == 200
        assert mock_get.call_count == 1
        assert mock_get.call_args.kwargs["impersonate"] == "chrome124"

    def test_normalize_ohmycaptcha_health_url(self):
        from routes.demos import _normalize_ohmycaptcha_base_url

        assert (
            _normalize_ohmycaptcha_base_url("http://192.168.5.133:8004/api/v1/health")
            == "http://192.168.5.133:8004"
        )
        assert (
            _normalize_ohmycaptcha_base_url("http://192.168.5.133:8004/api/v1")
            == "http://192.168.5.133:8004"
        )
        assert (
            _normalize_ohmycaptcha_base_url("http://192.168.5.133:8004/health")
            == "http://192.168.5.133:8004"
        )

    def test_event_matches_endpoint_prefers_results_page_links(self, client, app):
        results_html = """
        <html><body>
            <a href="/matches/9999999/unrelated-event-match">Unrelated match</a>
            <div class="results-holder">
                <div class="result-con">
                    <a href="/matches/2391771/aurora-vs-the-mongolz-blast-open-rotterdam-2026">Aurora vs The MongolZ</a>
                    <a href="/matches/2391770/the-mongolz-vs-spirit-blast-open-rotterdam-2026">The MongolZ vs Spirit</a>
                    <a href="/matches/2391771/aurora-vs-the-mongolz-blast-open-rotterdam-2026">Duplicate</a>
                </div>
            </div>
        </body></html>
        """

        with app.app_context():
            with patch("curl_cffi.requests.get") as mock_get:
                results_response = Mock()
                results_response.status_code = 200
                results_response.content = results_html.encode("utf-8")
                mock_get.return_value = results_response

                response = client.get(
                    "/api/v1/events/8248/blast-open-rotterdam-2026/matches"
                )

                assert response.status_code == 200
                assert mock_get.call_count == 1
                assert (
                    mock_get.call_args_list[0].args[0]
                    == "https://www.hltv.org/results?event=8248"
                )
                data = json.loads(response.data)
                assert data["event_id"] == 8248
                assert data["total"] == 2
                assert data["matches"] == [
                    {
                        "id": "2391771",
                        "slug": "aurora-vs-the-mongolz-blast-open-rotterdam-2026",
                        "url": "https://www.hltv.org/matches/2391771/aurora-vs-the-mongolz-blast-open-rotterdam-2026",
                    },
                    {
                        "id": "2391770",
                        "slug": "the-mongolz-vs-spirit-blast-open-rotterdam-2026",
                        "url": "https://www.hltv.org/matches/2391770/the-mongolz-vs-spirit-blast-open-rotterdam-2026",
                    },
                ]

    def test_match_stage_parser_extracts_stage_from_preformatted_text(self):
        html = b"""
        <html><body>
            <div class="teamsBox">
                <div class="date">27th of March 2026</div>
                <div class="time">17:35</div>
                <div class="event text-ellipsis"><a href="/events/8248/blast-open-rotterdam-2026">BLAST Open Rotterdam 2026</a></div>
                <div class="team1-gradient"><div class="teamName">PARIVISION</div><div class="won">2</div></div>
                <div class="team2-gradient"><div class="teamName">Falcons</div><div class="lost">1</div></div>
            </div>
            <div class="standard-box veto-box"><div class="padding preformatted-text">Best of 3 (LAN)  * Quarter-final</div></div>
        </body></html>
        """

        response = HtmlResponse(
            url="https://www.hltv.org/matches/2391772/test", body=html, encoding="utf-8"
        )
        parsed = MatchTeamsBoxParser.parse(response.css(".teamsBox"), response)

        assert parsed["stage"] == "Quarter-final"

    def test_teams_ranking_endpoint(self, client, app):
        """Test teams ranking endpoint."""
        mock_data = {"teams": ["Natus Vincere", "Astralis", "FaZe Clan"]}

        with app.app_context():
            with patch("hltv_scraper.HLTVScraper._get_manager") as mock_get_manager:
                mock_manager = Mock()
                mock_manager.execute.return_value = None
                mock_manager.get_result.return_value = mock_data
                mock_get_manager.return_value = mock_manager

                response = client.get("/api/v1/teams/rankings")

                assert response.status_code == 200
                data = json.loads(response.data)
                assert isinstance(data, dict)
                assert data == mock_data

    def test_upcoming_matches_endpoint(self, client, app):
        """Test upcoming matches endpoint."""
        mock_data = {
            "matches": [{"team1": "NAVI", "team2": "Astralis", "date": "2023-08-30"}]
        }

        with app.app_context():
            with patch("hltv_scraper.HLTVScraper._get_manager") as mock_get_manager:
                mock_manager = Mock()
                mock_manager.execute.return_value = None
                mock_manager.get_result.return_value = mock_data
                mock_get_manager.return_value = mock_manager

                response = client.get("/api/v1/matches/upcoming")

                assert response.status_code == 200
                data = json.loads(response.data)
                assert isinstance(data, dict)
                assert data == mock_data

    def test_news_endpoint(self, client, app):
        """Test news endpoint."""
        mock_data = {
            "news": [{"title": "Major tournament announced", "date": "2023-08-30"}]
        }

        with app.app_context():
            with patch("hltv_scraper.HLTVScraper._get_manager") as mock_get_manager:
                mock_manager = Mock()
                mock_manager.execute.return_value = None
                mock_manager.get_result.return_value = mock_data
                mock_get_manager.return_value = mock_manager

                response = client.get("/api/v1/news")

                assert response.status_code == 200
                data = json.loads(response.data)
                assert isinstance(data, dict)
                assert data == mock_data

    def test_results_endpoint(self, client, app):
        """Test results endpoint."""
        mock_data = {
            "results": [{"team1": "NAVI", "team2": "Astralis", "score": "16-14"}]
        }

        with app.app_context():
            with patch("hltv_scraper.HLTVScraper._get_manager") as mock_get_manager:
                mock_manager = Mock()
                mock_manager.execute.return_value = None
                mock_manager.get_result.return_value = mock_data
                mock_get_manager.return_value = mock_manager

                response = client.get("/api/v1/results/")

                assert response.status_code == 200
                data = json.loads(response.data)
                assert isinstance(data, dict)
                assert data == mock_data

    def test_player_search_success(self, client, app):
        """Test player search with successful result."""
        mock_data = [
            {
                "name": "Oleksandr 's1mple' Kostyliev",
                "profile_link": "/player/7998/s1mple",
                "img": "https://img-cdn.hltv.org/playerbodyshot/example.png",
                "player_image": "https://img-cdn.hltv.org/playerbodyshot/example.png",
            }
        ]

        with app.app_context():
            with patch("hltv_scraper.HLTVScraper._get_manager") as mock_get_manager:
                mock_manager = Mock()
                mock_manager.is_profile.return_value = True
                mock_manager.get_profile.return_value = mock_data
                mock_get_manager.return_value = mock_manager

                response = client.get("/api/v1/players/search/s1mple")

                assert response.status_code == 200
                data = json.loads(response.data)
                assert data == mock_data
                assert isinstance(data, list)
                assert data[0]["player_image"].startswith("https://")

    def test_player_search_not_found(self, client, app):
        """Test player search when player is not found."""
        with app.app_context():
            with patch("hltv_scraper.HLTVScraper._get_manager") as mock_get_manager:
                mock_manager = Mock()
                mock_manager.is_profile.return_value = False
                mock_get_manager.return_value = mock_manager

                response = client.get("/api/v1/players/search/nonexistent")

                assert response.status_code == 404
                data = json.loads(response.data)
                assert data == {"error": "Player not found!"}

    def test_team_search_success(self, client, app):
        """Test team search with successful result."""
        mock_data = {
            "team": "NAVI",
            "country": "Ukraine",
            "players": ["s1mple", "electronic"],
        }

        with app.app_context():
            with patch("hltv_scraper.HLTVScraper._get_manager") as mock_get_manager:
                mock_manager = Mock()
                mock_manager.is_profile.return_value = True
                mock_manager.get_profile.return_value = mock_data
                mock_get_manager.return_value = mock_manager

                response = client.get("/api/v1/teams/search/navi")

                assert response.status_code == 200
                data = json.loads(response.data)
                assert data == mock_data

    def test_team_search_not_found(self, client, app):
        """Test team search when team is not found."""
        with app.app_context():
            with patch("hltv_scraper.HLTVScraper._get_manager") as mock_get_manager:
                mock_manager = Mock()
                mock_manager.is_profile.return_value = False
                mock_get_manager.return_value = mock_manager

                response = client.get("/api/v1/teams/search/nonexistent")

                assert response.status_code == 404
                data = json.loads(response.data)
                assert data == {"error": "Team not found!"}


class TestSearchEvents:
    def test_returns_results_from_events_page(self, app):
        events_html = b"""<html><body>
            <a href="/events/8248/blast-open-rotterdam-2026"><div class="text-ellipsis">BLAST Open Rotterdam 2026</div><td>16</td><td>$1,100,000</td></a>
            <a href="/events/8323/esl-pro-league-season-26"><div class="text-ellipsis">ESL Pro League Season 26</div><td>24</td></a>
        </body></html>"""
        archive_html = b"""<html><body>
            <a href="/events/8413/esl-pro-league-season-23-finals"><div class="text-ellipsis">ESL Pro League Season 23 Finals</div><td>8</td><td>$776,000</td><td>Intl. LAN</td></a>
            <a href="/events/8412/esl-pro-league-season-23-stage-2"><div class="text-ellipsis">ESL Pro League Season 23 Stage 2</div><td>16</td><td>$185,000</td></a>
        </body></html>"""

        with app.app_context():
            with patch("hltv_event_search.requests.get") as mock_get:
                events_response = Mock()
                events_response.status_code = 200
                events_response.content = events_html

                archive_response = Mock()
                archive_response.status_code = 200
                archive_response.content = archive_html

                mock_get.side_effect = [events_response, archive_response]

                from hltv_event_search import search_events

                results = search_events("ESL Pro League Season 23")

                assert len(results) == 2
                assert results[0]["event_id"] == "8413"
                assert (
                    results[0]["url"] == "/events/8413/esl-pro-league-season-23-finals"
                )
                assert results[0]["name"] == "ESL Pro League Season 23 Finals"
                assert results[1]["event_id"] == "8412"
                assert (
                    results[1]["url"] == "/events/8412/esl-pro-league-season-23-stage-2"
                )
                assert results[1]["name"] == "ESL Pro League Season 23 Stage 2"

    def test_search_endpoint_returns_results(self, client, app):
        events_html = b"""<html><body>
            <a href=\"/events/8248/blast-open-rotterdam-2026\">BLAST Open Rotterdam 2026</a>
        </body></html>"""
        archive_html = b"""<html><body></body></html>"""

        with app.app_context():
            with patch("hltv_event_search.requests.get") as mock_get:
                events_response = Mock()
                events_response.status_code = 200
                events_response.content = events_html

                archive_response = Mock()
                archive_response.status_code = 200
                archive_response.content = archive_html

                mock_get.side_effect = [events_response, archive_response]

                response = client.get(
                    "/api/v1/events/search?q=BLAST%20Open%20Rotterdam"
                )

                assert response.status_code == 200
                data = json.loads(response.data)
                assert data["total"] == 1
                assert data["results"][0]["event_id"] == "8248"
                assert (
                    data["results"][0]["url"]
                    == "/events/8248/blast-open-rotterdam-2026"
                )
                assert data["results"][0]["name"] == "BLAST Open Rotterdam 2026"
