from typing import Literal
from urllib.parse import urlparse
from flask import Blueprint, Response, jsonify, request
from flasgger import swag_from

from hltv_scraper import HLTVScraper
import sys
sys.path.append('..')
from hltv_event_search import search_events, get_event_with_grouped_events
events_bp = Blueprint("events", __name__, url_prefix="/api/v1/events")


def _normalize_hltv_event_url(event_url: str) -> str | None:
    if not event_url:
        return None

    if event_url.startswith('/events/'):
        return event_url

    parsed = urlparse(event_url)
    if parsed.scheme == 'https' and parsed.netloc == 'www.hltv.org' and parsed.path.startswith('/events/'):
        return parsed.path

    return None

@events_bp.route("/", methods=["GET"])
@swag_from('../swagger_specs/events_list.yml')
def events() -> Response | tuple[Response, Literal[500]]:
    """Get events from HLTV."""
    try:
        data = HLTVScraper.get_events()
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@events_bp.route("/<int:event_id>/<slug>/matches", methods=["GET"])
@swag_from('../swagger_specs/events_matches.yml')
def event_matches(event_id: int, slug: str) -> Response | tuple[Response, Literal[500]]:
    """Get all matches for a specific event."""
    try:
        from curl_cffi import requests
        from bs4 import BeautifulSoup

        def extract_standard_match_links(soup, selector='a[href]'):
            matches = []
            for link in soup.select(selector):
                href = link.get('href')
                if not isinstance(href, str) or not href.startswith('/matches/'):
                    continue

                parts = href.split('/')
                if len(parts) < 4 or not parts[2].isdigit():
                    continue

                matches.append({
                    "id": parts[2],
                    "slug": parts[3],
                    "url": f"https://www.hltv.org{href}",
                })

            seen = set()
            unique = []
            for match in matches:
                if match['id'] in seen:
                    continue
                seen.add(match['id'])
                unique.append(match)

            return unique
        
        matches = []

        results_url = f"https://www.hltv.org/results?event={event_id}"
        results_resp = requests.get(results_url, impersonate="chrome142", timeout=10)
        if results_resp.status_code == 200:
            results_soup = BeautifulSoup(results_resp.content, 'html.parser')
            matches = extract_standard_match_links(results_soup, 'div.results-holder div.result-con > a[href]')

        if not matches:
            event_url = f"https://www.hltv.org/events/{event_id}/{slug}"
            event_resp = requests.get(event_url, impersonate="chrome142", timeout=10)

            if event_resp.status_code != 200:
                return jsonify({"error": f"Failed to fetch event page: {event_resp.status_code}"}), event_resp.status_code

            event_soup = BeautifulSoup(event_resp.content, 'html.parser')
            event_content = event_soup.find('div', class_='contentCol') or event_soup
            matches = extract_standard_match_links(event_content)

        return jsonify({"event_id": event_id, "matches": matches, "total": len(matches)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@events_bp.route("/search", methods=["GET"])
@swag_from('../swagger_specs/events_search.yml')
def search() -> Response | tuple[Response, Literal[500]]:
    """Search for events by name."""
    try:
        query = request.args.get('q', '')
        if not query:
            return jsonify({"error": "Query parameter 'q' is required"}), 400
        
        results = search_events(query)
        return jsonify({"query": query, "results": results, "total": len(results)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@events_bp.route("/discover", methods=["GET"])
@swag_from('../swagger_specs/events_discover.yml')
def discover() -> Response | tuple[Response, Literal[500]]:
    """Discover event and all its grouped events."""
    try:
        event_url = _normalize_hltv_event_url(request.args.get('url', ''))
        if not event_url:
            return jsonify({"error": "URL parameter 'url' is required"}), 400
        
        result = get_event_with_grouped_events(event_url)
        if not result:
            return jsonify({"error": "Failed to fetch event details"}), 404
        
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
@events_bp.route("/tier", methods=["GET"])
@swag_from('../swagger_specs/events_tier.yml')
def get_tier() -> Response | tuple[Response, Literal[500]]:
    """Get event tier from Liquipedia."""
    try:
        from liquipedia_scraper import get_event_tier
        event_name = request.args.get('name', '')
        if not event_name:
            return jsonify({"error": "Event name parameter 'name' is required"}), 400
        
        tier = get_event_tier(event_name)
        return jsonify({"event_name": event_name, "tier": tier})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
@events_bp.route("/ongoing", methods=["GET"])
@swag_from('../swagger_specs/events_ongoing.yml')
def get_ongoing() -> Response | tuple[Response, Literal[500]]:
    try:
        from liquipedia_scraper import get_ongoing_tournaments
        tournaments = get_ongoing_tournaments()
        result = [{'name': t} for t in tournaments]
        return jsonify({'tournaments': result, 'total': len(result)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@events_bp.route("/completed", methods=["GET"])
@swag_from('../swagger_specs/events_completed.yml')
def get_completed() -> Response | tuple[Response, Literal[500]]:
    """Get completed tournaments from Liquipedia."""
    try:
        from liquipedia_scraper import get_completed_tournaments
        tournaments = get_completed_tournaments()
        result = [{'name': t} for t in tournaments]
        return jsonify({'tournaments': result, 'total': len(result)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@events_bp.route("/details", methods=["GET"])
@swag_from('../swagger_specs/events_details.yml')
def get_details() -> Response | tuple[Response, Literal[500]]:
    """Get event details including grouped events."""
    try:
        from hltv_event_scraper import get_event_details
        event_url = _normalize_hltv_event_url(request.args.get('url', ''))
        if not event_url:
            return jsonify({"error": "Event URL parameter 'url' is required"}), 400
        
        details = get_event_details(event_url)
        if not details:
            return jsonify({"error": "Failed to fetch event details"}), 404
        
        return jsonify(details)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
