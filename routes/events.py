import re
from typing import Literal
from urllib.parse import urlparse
from flask import Blueprint, Response, jsonify, request
from flasgger import swag_from

from hltv_scraper import HLTVScraper
import sys

sys.path.append("..")
from http_client import HLTV_IMPERSONATION_CHAIN, get_with_impersonation_fallback
from hltv_event_search import search_events, get_event_with_grouped_events

events_bp = Blueprint("events", __name__, url_prefix="/api/v1/events")


def _normalize_hltv_event_url(event_url: str) -> str | None:
    if not event_url:
        return None

    if event_url.startswith("/events/"):
        return event_url

    parsed = urlparse(event_url)
    if (
        parsed.scheme == "https"
        and parsed.netloc == "www.hltv.org"
        and parsed.path.startswith("/events/")
    ):
        return parsed.path

    return None


def _extract_match_team_names(link_text: str) -> tuple[str | None, str | None]:
    normalized_text = " ".join(str(link_text or "").split())
    if not normalized_text:
        return None, None

    normalized_text = re.sub(r"^\d{1,2}/\d{1,2}/\d{2,4}\s+", "", normalized_text)

    scored_match = re.match(
        r"^(?P<team1>.+?)\s+\d+\s*-\s*\d+\s+(?P<team2>.+?)(?:\s+bo\d+)?$",
        normalized_text,
        flags=re.IGNORECASE,
    )
    if scored_match:
        return scored_match.group("team1").strip(), scored_match.group("team2").strip()

    versus_match = re.match(
        r"^(?P<team1>.+?)\s+vs\.?\s+(?P<team2>.+)$",
        normalized_text,
        flags=re.IGNORECASE,
    )
    if versus_match:
        return versus_match.group("team1").strip(), versus_match.group("team2").strip()

    return None, None


@events_bp.route("/", methods=["GET"])
@swag_from("../swagger_specs/events_list.yml")
def events() -> Response | tuple[Response, Literal[500]]:
    """Get events from HLTV."""
    try:
        data = HLTVScraper.get_events()
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@events_bp.route("/<int:event_id>/<slug>/matches", methods=["GET"])
@swag_from("../swagger_specs/events_matches.yml")
def event_matches(event_id: int, slug: str) -> Response | tuple[Response, Literal[500]]:
    """Get all matches for a specific event."""
    try:
        from bs4 import BeautifulSoup

        def extract_standard_match_links(soup, selector="a[href]"):
            matches = []
            for link in soup.select(selector):
                href = link.get("href")
                if not isinstance(href, str) or not href.startswith("/matches/"):
                    continue

                parts = href.split("/")
                if len(parts) < 4 or not parts[2].isdigit():
                    continue

                link_text = " ".join(link.get_text(" ", strip=True).split())
                team1_name, team2_name = _extract_match_team_names(link_text)

                match_entry = {
                    "id": parts[2],
                    "slug": parts[3],
                    "url": f"https://www.hltv.org{href}",
                }
                if team1_name and team2_name:
                    match_entry["team1_name"] = team1_name
                    match_entry["team2_name"] = team2_name

                matches.append(match_entry)

            seen = {}
            unique = []
            for match in matches:
                existing_match = seen.get(match["id"])
                if existing_match:
                    if not existing_match.get("team1_name") and match.get("team1_name"):
                        existing_match["team1_name"] = match["team1_name"]
                    if not existing_match.get("team2_name") and match.get("team2_name"):
                        existing_match["team2_name"] = match["team2_name"]
                    continue
                seen[match["id"]] = match
                unique.append(match)

            return unique

        matches = []

        results_url = f"https://www.hltv.org/results?event={event_id}"
        results_resp = get_with_impersonation_fallback(
            results_url,
            impersonate="chrome124",
            fallback_impersonations=HLTV_IMPERSONATION_CHAIN,
            timeout=10,
        )
        if results_resp.status_code == 200:
            results_soup = BeautifulSoup(results_resp.content, "html.parser")
            matches = extract_standard_match_links(
                results_soup, "div.results-holder div.result-con > a[href]"
            )

        if not matches:
            event_url = f"https://www.hltv.org/events/{event_id}/{slug}"
            event_resp = get_with_impersonation_fallback(
                event_url,
                impersonate="chrome124",
                fallback_impersonations=HLTV_IMPERSONATION_CHAIN,
                timeout=10,
            )

            if event_resp.status_code != 200:
                return jsonify(
                    {"error": f"Failed to fetch event page: {event_resp.status_code}"}
                ), event_resp.status_code

            event_soup = BeautifulSoup(event_resp.content, "html.parser")
            event_content = event_soup.find("div", class_="contentCol") or event_soup
            matches = extract_standard_match_links(event_content)

        return jsonify(
            {"event_id": event_id, "matches": matches, "total": len(matches)}
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@events_bp.route("/search", methods=["GET"])
@swag_from("../swagger_specs/events_search.yml")
def search() -> Response | tuple[Response, Literal[500]]:
    """Search for events by name."""
    try:
        query = request.args.get("q", "")
        if not query:
            return jsonify({"error": "Query parameter 'q' is required"}), 400

        results = search_events(query)
        return jsonify({"query": query, "results": results, "total": len(results)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@events_bp.route("/discover", methods=["GET"])
@swag_from("../swagger_specs/events_discover.yml")
def discover() -> Response | tuple[Response, Literal[500]]:
    """Discover event and all its grouped events."""
    try:
        event_url = _normalize_hltv_event_url(request.args.get("url", ""))
        if not event_url:
            return jsonify({"error": "URL parameter 'url' is required"}), 400

        result = get_event_with_grouped_events(event_url)
        if not result:
            return jsonify({"error": "Failed to fetch event details"}), 404

        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@events_bp.route("/tier", methods=["GET"])
@swag_from("../swagger_specs/events_tier.yml")
def get_tier() -> Response | tuple[Response, Literal[500]]:
    """Get event tier from Liquipedia."""
    try:
        from liquipedia_scraper import get_event_tier

        event_name = request.args.get("name", "")
        if not event_name:
            return jsonify({"error": "Event name parameter 'name' is required"}), 400

        tier = get_event_tier(event_name)
        return jsonify({"event_name": event_name, "tier": tier})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@events_bp.route("/ongoing", methods=["GET"])
@swag_from("../swagger_specs/events_ongoing.yml")
def get_ongoing() -> Response | tuple[Response, Literal[500]]:
    try:
        from liquipedia_scraper import get_ongoing_tournaments

        tournaments = get_ongoing_tournaments()
        result = [{"name": t} for t in tournaments]
        return jsonify({"tournaments": result, "total": len(result)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@events_bp.route("/completed", methods=["GET"])
@swag_from("../swagger_specs/events_completed.yml")
def get_completed() -> Response | tuple[Response, Literal[500]]:
    """Get completed tournaments from Liquipedia."""
    try:
        from liquipedia_scraper import get_completed_tournaments

        tournaments = get_completed_tournaments()
        result = [{"name": t} for t in tournaments]
        return jsonify({"tournaments": result, "total": len(result)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@events_bp.route("/details", methods=["GET"])
@swag_from("../swagger_specs/events_details.yml")
def get_details() -> Response | tuple[Response, Literal[500]]:
    """Get event details including grouped events."""
    try:
        from hltv_event_scraper import get_event_details

        event_url = _normalize_hltv_event_url(request.args.get("url", ""))
        if not event_url:
            return jsonify({"error": "Event URL parameter 'url' is required"}), 400

        details = get_event_details(event_url)
        if not details:
            return jsonify({"error": "Failed to fetch event details"}), 404

        return jsonify(details)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
