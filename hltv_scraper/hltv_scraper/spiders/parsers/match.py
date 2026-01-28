from .parser import Parser
from .team import TeamParser


class MatchParser(Parser):
    @staticmethod
    def parse(result, date:str = "") -> dict:
        return {
            "id": result.css("a.a-reset::attr(href)").re_first(r"/matches/(\d+)"),
            "link": result.css("a.a-reset::attr(href)").get(),
            "map": result.css("div.map-text::text").get(),
            "event": result.css("span.event-name::text").get(),
            "date": date,
            "team1": TeamParser.parse(result, 1),
            "team2": TeamParser.parse(result, 2),
            "demoUrl": result.xpath('following-sibling::div[contains(@class, "streams")][1]//a[@data-demo-link]/@data-demo-link').get(),
        }
