"""
HLTV Event scraper for grouped events
"""

from urllib.parse import urlparse

from bs4 import BeautifulSoup

from http_client import HLTV_IMPERSONATION_CHAIN, get_with_impersonation_fallback


def _normalize_hltv_event_url(event_url):
    if not event_url:
        return None
    if event_url.startswith("/events/"):
        return f"https://www.hltv.org{event_url}"

    parsed = urlparse(event_url)
    if (
        parsed.scheme == "https"
        and parsed.netloc == "www.hltv.org"
        and parsed.path.startswith("/events/")
    ):
        return event_url

    return None


def get_event_details(event_url):
    """Get event details including grouped events"""
    try:
        normalized_url = _normalize_hltv_event_url(event_url)
        if not normalized_url:
            return None

        response = get_with_impersonation_fallback(
            normalized_url,
            impersonate="chrome142",
            fallback_impersonations=HLTV_IMPERSONATION_CHAIN,
            timeout=10,
        )
        soup = BeautifulSoup(response.content, "html.parser")

        # Extract event name
        event_name = None
        event_hub = soup.find("div", class_="event-hub")
        if event_hub:
            title = event_hub.find("h1")
            if title:
                event_name = title.get_text(strip=True)

        if not event_name:
            import re

            match = re.search(r"/events/\d+/([^/]+)", event_url)
            if match:
                event_name = match.group(1).replace("-", " ").title()

        # Extract grouped events
        grouped_events = []
        grouped_container = soup.find("div", class_="linked-events-container-slider")
        if grouped_container:
            for event_div in grouped_container.find_all("a", href=True):
                title_elem = event_div.find("div", class_="linked-event-title")
                if title_elem:
                    sub_name = title_elem.get_text(strip=True)
                    sub_url = "https://www.hltv.org" + event_div.get("href")
                    grouped_events.append({"name": sub_name, "url": sub_url})

        return {
            "name": event_name,
            "url": normalized_url,
            "grouped_events": grouped_events,
        }
    except Exception as e:
        print(f"Error scraping event: {e}")
        return None
