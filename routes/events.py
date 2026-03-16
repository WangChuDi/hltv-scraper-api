from typing import Literal
from flask import Blueprint, Response, jsonify, request
from flasgger import swag_from

from hltv_scraper import HLTVScraper
import sys
sys.path.append('..')
from hltv_event_search import search_events, get_event_with_grouped_events
events_bp = Blueprint("events", __name__, url_prefix="/api/v1/events")

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
        
        url = f"https://www.hltv.org/events/{event_id}/{slug}"
        resp = requests.get(url, impersonate="chrome142", timeout=10)
        
        if resp.status_code != 200:
            return jsonify({"error": f"Failed to fetch event page: {resp.status_code}"}), resp.status_code
        
        soup = BeautifulSoup(resp.content, 'html.parser')
        matches = []
        
        # Find matches in the main event content area only
        # Look for match links within specific containers to avoid sidebar/unrelated matches
        event_content = soup.find('div', class_='contentCol') or soup
        
        for link in event_content.find_all('a', href=lambda x: x and '/matches/' in x):
            href = link.get('href')
            if href.startswith('/matches/'):
                parts = href.split('/')
                if len(parts) >= 4:
                    # Verify the slug contains the event name to filter out unrelated matches
                    slug_lower = parts[3].lower()
                    event_slug_lower = slug.lower()
                    # Extract key parts of event slug for matching
                    event_key_parts = [p for p in event_slug_lower.split('-') if len(p) > 3]
                    # Check if match slug contains event identifier
                    if any(part in slug_lower for part in event_key_parts[:2]):
                        matches.append({"id": parts[2], "slug": parts[3], "url": f"https://www.hltv.org{href}"})
        
        # Deduplicate
        seen = set()
        unique = []
        for m in matches:
            key = m['id']
            if key not in seen:
                seen.add(key)
                unique.append(m)
        
        return jsonify({"event_id": event_id, "matches": unique, "total": len(unique)})
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
        event_url = request.args.get('url', '')
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
    """Get ongoing S-tier tournaments from Liquipedia."""
    try:
        from liquipedia_scraper import get_ongoing_tournaments
        tournaments = get_ongoing_tournaments()
        result = [{'name': t, 'tier': 'S'} for t in tournaments]
        return jsonify({'tournaments': result, 'total': len(result)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@events_bp.route("/completed", methods=["GET"])
@swag_from('../swagger_specs/events_ongoing.yml')
def get_completed() -> Response | tuple[Response, Literal[500]]:
    """Get completed tournaments from Liquipedia."""
    try:
        from liquipedia_scraper import get_completed_tournaments
        tournaments = get_completed_tournaments()
        result = [{'name': t, 'tier': 'S'} for t in tournaments]
        return jsonify({'tournaments': result, 'total': len(result)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@events_bp.route("/details", methods=["GET"])
@swag_from('../swagger_specs/events_details.yml')
def get_details() -> Response | tuple[Response, Literal[500]]:
    """Get event details including grouped events."""
    try:
        from hltv_event_scraper import get_event_details
        event_url = request.args.get('url', '')
        if not event_url:
            return jsonify({"error": "Event URL parameter 'url' is required"}), 400
        
        details = get_event_details(event_url)
        if not details:
            return jsonify({"error": "Failed to fetch event details"}), 404
        
        return jsonify(details)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
