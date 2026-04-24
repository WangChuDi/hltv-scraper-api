from typing import Any, Generator

import scrapy
from scrapy.http.response.html import HtmlResponse

from ..http_client import (
    HLTV_IMPERSONATION_CHAIN,
    detect_cloudflare_challenge,
    get_with_impersonation_fallback,
)
from .parsers import ParsersFactory as PF


BLOCKED_PAGE_MARKERS = ("cf-mitigated", "cf-challenge")


def _is_blocked_or_non_match_response(response_data) -> bool:
    if response_data.status_code != 200:
        return True

    headers = getattr(response_data, "headers", {}) or {}
    mitigated_header = headers.get("cf-mitigated")
    if isinstance(mitigated_header, bytes):
        mitigated_header = mitigated_header.decode("utf-8", errors="ignore")
    if isinstance(mitigated_header, str) and mitigated_header.lower() == "challenge":
        return True

    return detect_cloudflare_challenge(
        response_data,
        extra_body_markers=BLOCKED_PAGE_MARKERS,
    )


class HltvMatchSpider(scrapy.Spider):
    name = "hltv_match"
    allowed_domains = ["www.hltv.org"]

    def __init__(self, match: str, **kwargs: Any) -> None:
        self.start_urls = [f"https://www.hltv.org/matches/{match}"]
        super().__init__(**kwargs)

    def start_requests(self) -> Generator[dict[str, object], Any, None]:
        for url in self.start_urls:
            try:
                # Use the shared impersonation fallback chain to bypass Cloudflare
                response_data = get_with_impersonation_fallback(
                    url,
                    impersonate="chrome136",
                    fallback_impersonations=HLTV_IMPERSONATION_CHAIN,
                    validate_response=lambda response: not _is_blocked_or_non_match_response(response),
                )

                if _is_blocked_or_non_match_response(response_data):
                    self.logger.error(
                        f"Error fetching {url}: blocked or non-match response (status={response_data.status_code})"
                    )
                    continue

                response = HtmlResponse(
                    url=url, body=response_data.content, encoding="utf-8"
                )

                yield from self.parse(response)
            except Exception as e:
                self.logger.error(f"Error fetching {url}: {e}")
                continue

    def parse(self, response) -> Generator[dict[str, object], Any, None]:
        teams_box_selector = response.css(".teamsBox")
        if not teams_box_selector:
            self.logger.error(f"Skipping non-match HTML for {response.url}: .teamsBox not found")
            return

        teams_box = PF.get_parser("match_teams_box").parse(teams_box_selector, response)
        if not isinstance(teams_box, dict):
            self.logger.error(f"Skipping invalid match HTML for {response.url}: teams box parser returned no data")
            return

        team1_candidate = teams_box.get("team1")
        team2_candidate = teams_box.get("team2")
        team1 = team1_candidate if isinstance(team1_candidate, dict) else {}
        team2 = team2_candidate if isinstance(team2_candidate, dict) else {}
        if not team1.get("name") and not team2.get("name"):
            self.logger.error(f"Skipping invalid match HTML for {response.url}: both team names missing")
            return
        maps_score = PF.get_parser("map_holders").parse(response)
        player_stats = PF.get_parser("table_stats").parse(response.css("#all-content"))

        demo_url = response.css(
            "a.stream-box[data-demo-link]::attr(data-demo-link)"
        ).get()
        if demo_url and not demo_url.startswith("http"):
            demo_url = f"https://www.hltv.org{demo_url}"
        yield {
            "match": teams_box,
            "maps": maps_score,
            "stats": player_stats,
            "demoUrl": demo_url,
        }
