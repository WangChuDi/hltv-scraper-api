from typing import Literal
from flask import Blueprint, Response, jsonify, request
from flasgger import swag_from

from hltv_scraper import HLTVScraper
from liquipedia_scraper import get_ongoing_tournaments

results_bp = Blueprint("results", __name__, url_prefix="/api/v1/results")

@results_bp.route("/", defaults={"offset": 0})
@results_bp.route("/<int:offset>", methods=["GET"])
@swag_from('../swagger_specs/results_list.yml')
def results(offset: int) -> Response | tuple[Response, Literal[500]]:
    """Get results from HLTV."""
    try:
        data = HLTVScraper.get_results(offset)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@results_bp.route("/featured", methods=["GET"])
@swag_from('../swagger_specs/results_featured.yml')
def big_results() -> Response | tuple[Response, Literal[500]]:
    """Get featured results from HLTV."""
    try:
        data = HLTVScraper.get_big_results()
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@results_bp.route("/ongoing-events", methods=["GET"])
def ongoing_events() -> Response | tuple[Response, Literal[500]]:
    """Get ongoing tournaments from Liquipedia."""
    try:
        # Fetch ongoing tournaments from Liquipedia
        tournaments = get_ongoing_tournaments()
        
        # Format response
        result = [{'name': t, 'source': 'liquipedia'} for t in tournaments]
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
