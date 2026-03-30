from typing import Any
import re
from .parser import Parser
from .match_team import MatchTeamParser as MTP

class MatchTeamsBoxParser(Parser):
    @staticmethod
    def extract_stage(response) -> str | None:
        for node in response.css('div.standard-box.veto-box div.padding.preformatted-text::text').getall():
            text = re.sub(r'\s+', ' ', (node or '').strip())
            match = re.search(r'Best of\s+\d+\s*\((?:LAN|Online)\)\s*\*\s*(.+)', text, re.IGNORECASE)
            if match:
                stage = match.group(1).strip()
                if stage:
                    return stage
        return None

    @staticmethod
    def parse(teams_box, response=None) -> dict[str, Any]:
        return {
        "date": teams_box.css("div.date::text").get(),
        "hour": teams_box.css("div.time::text").get(),
        "event": teams_box.css("div.event ::text").get(),
        "eventUrl": teams_box.css("div.event a::attr(href)").get(),
        "stage": MatchTeamsBoxParser.extract_stage(response) if response is not None else None,
        "team1": MTP.parse(teams_box, 1),
        "team2": MTP.parse(teams_box, 2),
    }
