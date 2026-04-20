from typing import Any, Generator

import scrapy
from scrapy.http.response.html import HtmlResponse

from ..http_client import (
    HLTV_IMPERSONATION_CHAIN,
    get_with_impersonation_fallback,
)
from .parsers import ParsersFactory as PF


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
                    impersonate="chrome142",
                    fallback_impersonations=HLTV_IMPERSONATION_CHAIN,
                )

                if response_data.status_code != 200:
                    self.logger.error(
                        f"Error fetching {url}: upstream returned {response_data.status_code}"
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
        teams_box = PF.get_parser("match_teams_box").parse(
            response.css(".teamsBox"), response
        )
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
