from flask import Request
import scrapy
from typing import Any, Generator
import cloudscraper
from scrapy.http.response.html import HtmlResponse
from .parsers import ParsersFactory as PF
from http_client import HLTV_IMPERSONATION_CHAIN, get_with_impersonation_fallback


class HltvMatchSpider(scrapy.Spider):
    name = "hltv_match"
    allowed_domains = ["www.hltv.org"]

    def __init__(self, match: str, **kwargs: Any) -> None:
        self.start_urls = [f"https://www.hltv.org/matches/{match}"]
        super().__init__(**kwargs)

    def start_requests(self) -> Generator[dict[str, None] | Request, Any, None]:
        for url in self.start_urls:
            try:
                # Impersonate Safari 15.3 to bypass Cloudflare
                response_data = get_with_impersonation_fallback(
                    url,
                    impersonate="chrome142",
                    fallback_impersonations=HLTV_IMPERSONATION_CHAIN,
                )

                if response_data.status_code == 403:
                    self.logger.error(
                        f"Error fetching {url}: 403 Forbidden (Cloudflare block)"
                    )

                response = HtmlResponse(
                    url=url, body=response_data.content, encoding="utf-8"
                )

                yield from self.parse(response)
            except Exception as e:
                self.logger.error(f"Error fetching {url}: {e}")
                # Fallback to standard request if curl_cffi completely fails (unlikely to help if CF blocked)
                yield scrapy.Request(
                    url=url,
                    callback=self.parse,
                )

    def parse(self, response) -> Generator[dict[str, None], Any, None]:
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
