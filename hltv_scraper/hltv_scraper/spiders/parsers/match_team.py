from typing import Any
from .parser import Parser


class MatchTeamParser(Parser):
    @staticmethod
    def _get_team_name(teams_box, number: int) -> str | None:
        selectors = (
            f"div.team{number}-gradient .teamName::text",
            f"div.team{number}-gradient a[href*='/team/']::text",
            f"div.team{number}-gradient .team::text",
            f"div.team{number}-gradient img::attr(title)",
            f"div.team{number}-gradient img::attr(alt)",
        )

        for selector in selectors:
            value = teams_box.css(selector).get()
            if isinstance(value, str):
                value = value.strip()
            if value:
                return value

        return None

    @staticmethod
    def parse(teams_box, number: int) -> dict[str, Any]:
        return {
            "name": MatchTeamParser._get_team_name(teams_box, number),
            "logo": teams_box.css(f"div.team{number}-gradient img::attr(src)").get(),
            "score": teams_box.css(
                f".team{number}-gradient > div:nth-child(2)::text"
            ).get(),
        }
