"""
Liquipedia scraper for tournament tier information
"""

from bs4 import BeautifulSoup
import re

from http_client import (
    LIQUIPEDIA_IMPERSONATION_CHAIN,
    get_with_impersonation_fallback,
)


def _build_liquipedia_event_url(event_name):
    event_lower = event_name.lower()

    if "esl pro league" in event_lower:
        match = re.search(r"season\s*(\d+)", event_lower)
        if match:
            return f"https://liquipedia.net/counterstrike/ESL/Pro_League/Season_{match.group(1)}"
    elif "iem" in event_lower:
        parts = event_name.split()
        if len(parts) >= 2:
            return f"https://liquipedia.net/counterstrike/Intel_Extreme_Masters/{parts[-1]}"
    elif "blast premier" in event_lower:
        match = re.search(r"(spring|fall|world final)", event_lower)
        year_match = re.search(r"20\d{2}", event_name)
        if match and year_match:
            return f"https://liquipedia.net/counterstrike/BLAST/Premier/{year_match.group(0)}/{match.group(1).title()}"
    elif "blast open" in event_lower:
        year_match = re.search(r"20\d{2}", event_name)
        season_match = re.search(r"(spring|fall)", event_lower)
        if year_match and season_match:
            return f"https://liquipedia.net/counterstrike/BLAST/Open/{year_match.group(0)}/{season_match.group(1).title()}"
        if year_match and "rotterdam" in event_lower:
            return f"https://liquipedia.net/counterstrike/BLAST/Open/{year_match.group(0)}/Spring"
        if year_match and "copenhagen" in event_lower:
            return f"https://liquipedia.net/counterstrike/BLAST/Open/{year_match.group(0)}/Fall"
    elif "pgl" in event_lower:
        parts = event_name.replace("PGL", "").strip().split()
        if parts:
            return f"https://liquipedia.net/counterstrike/PGL/{''.join(parts)}"

    return None


def _parse_money_amount(text):
    match = re.search(r"\$([\d,]+)", text or "")
    return int(match.group(1).replace(",", "")) if match else None


def _extract_text_block(text, start_label, end_labels):
    start_match = re.search(rf"{re.escape(start_label)}:\s*", text)
    if not start_match:
        return None

    tail = text[start_match.end() :]
    end_positions = [
        tail.find(f"{label}:") for label in end_labels if tail.find(f"{label}:") != -1
    ]
    end_pos = min(end_positions) if end_positions else len(tail)
    return tail[:end_pos].strip()


def get_liquipedia_event_metadata(event_name):
    try:
        url = _build_liquipedia_event_url(event_name)
        if not url:
            return None

        response = get_with_impersonation_fallback(
            url,
            timeout=10,
            impersonate="chrome",
            fallback_impersonations=LIQUIPEDIA_IMPERSONATION_CHAIN,
        )
        if response.status_code != 200:
            return None

        soup = BeautifulSoup(response.content, "html.parser")
        raw_name = (
            soup.title.get_text(strip=True).replace(
                " - Liquipedia Counter-Strike Wiki", ""
            )
            if soup.title
            else event_name
        )
        text = soup.get_text("\n", strip=True)

        location_block = _extract_text_block(
            text, "Location", ["Venue", "Prize Pool", "Start Date"]
        )
        locations = (
            [line.strip() for line in location_block.split("\n") if line.strip()]
            if location_block
            else []
        )
        start_date_match = re.search(r"Start Date:\s*(\d{4}-\d{2}-\d{2})", text)
        end_date_match = re.search(r"End Date:\s*(\d{4}-\d{2}-\d{2})", text)
        prize_block = _extract_text_block(
            text, "Prize Pool", ["Start Date", "End Date", "Teams"]
        )

        return {
            "raw_name": raw_name,
            "source": "liquipedia",
            "url": url,
            "start_date": start_date_match.group(1) if start_date_match else None,
            "end_date": end_date_match.group(1) if end_date_match else None,
            "location_text": " | ".join(locations) if locations else None,
            "locations": locations,
            "total_prize_pool_usd": None,
            "player_prize_pool_usd": _parse_money_amount(prize_block or ""),
            "club_prize_pool_usd": None,
        }
    except Exception as e:
        print(f"Error fetching Liquipedia metadata for {event_name}: {e}")
        return None


def get_event_tier(event_name):
    """Get tournament tier from Liquipedia"""
    try:
        url = _build_liquipedia_event_url(event_name)
        if not url:
            return None

        response = get_with_impersonation_fallback(
            url,
            timeout=10,
            impersonate="chrome",
            fallback_impersonations=LIQUIPEDIA_IMPERSONATION_CHAIN,
        )
        if response.status_code == 200:
            match = re.search(r"([SABC])-Tier", response.text, re.IGNORECASE)
            if match:
                return match.group(1).upper()

        return None
    except Exception as e:
        print(f"Error fetching tier for {event_name}: {e}")
        return None


def get_ongoing_tournaments():
    """Scrape ongoing tournaments from Liquipedia"""
    url = "https://liquipedia.net/counterstrike/Main_Page"

    try:
        response = get_with_impersonation_fallback(
            url,
            timeout=10,
            fallback_impersonations=LIQUIPEDIA_IMPERSONATION_CHAIN,
        )
        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.content, "html.parser")

        # Get all text and find the Ongoing section
        full_text = soup.get_text()

        # Find "Ongoing" followed by tournament names until "Concluded"
        pattern = r"Ongoing([\s\S]*?)Concluded"
        match = re.search(pattern, full_text)

        if match:
            ongoing_text = match.group(1)
            # Split by newlines and filter
            lines = [line.strip() for line in ongoing_text.split("\n") if line.strip()]
            tournaments = []
            for line in lines:
                # Filter out UI elements and keep only tournament names
                if len(line) > 10 and not any(
                    x in line.lower()
                    for x in [
                        "edit",
                        "contribute",
                        "support",
                        "report",
                        "submit",
                        "chat",
                        "help",
                        "portal",
                        "guidelines",
                        "twitter",
                        "search",
                        "scroll",
                        "top",
                    ]
                ):
                    tournaments.append(line)

            return tournaments[:5]  # Return top 5

        return []
    except Exception as e:
        print(f"Error scraping Liquipedia: {e}")
        return []


def get_completed_tournaments():
    """Get recently completed tournaments - fallback list"""
    return [
        "ESL Pro League Season 23 Finals",
        "BLAST Premier World Final 2025",
        "IEM Katowice 2026",
        "PGL Major Copenhagen 2025",
        "BLAST Premier Fall Final 2025",
    ]


def get_ongoing_s_tier_tournaments():
    """Scrape ongoing S-tier tournaments from Liquipedia"""
    url = "https://liquipedia.net/counterstrike/Main_Page"
    try:
        response = get_with_impersonation_fallback(
            url,
            timeout=10,
            impersonate="chrome",
            fallback_impersonations=LIQUIPEDIA_IMPERSONATION_CHAIN,
        )
        soup = BeautifulSoup(response.content, "html.parser")

        # Find S-Tier section in ongoing tournaments
        tournaments = []
        ongoing_section = soup.find("div", class_="divRow")
        if ongoing_section:
            # Look for S-Tier tournaments
            for link in ongoing_section.find_all("a", href=True):
                text = link.get_text(strip=True)
                # Check if it's marked as S-Tier or is a major tournament
                if text and len(text) > 5:
                    tournaments.append({"name": text, "tier": "S"})

        return tournaments[:5]
    except Exception as e:
        print(f"Error scraping S-tier tournaments: {e}")
        return []
