"""
HLTV Event search and discovery
"""
from curl_cffi import requests
from bs4 import BeautifulSoup

from liquipedia_scraper import get_event_tier
def search_events(query):
    """Search for events on HLTV by name"""
    try:
        resp = requests.get('https://www.hltv.org/events', impersonate='chrome142', timeout=10)
        soup = BeautifulSoup(resp.content, 'html.parser')
        
        results = []
        # Normalize query for matching
        query_parts = query.lower().replace('s', ' season ').split()
        
        for link in soup.find_all('a', href=lambda x: x and '/events/' in x):
            href = link.get('href')
            if not href.startswith('/events/') or href == '/events/archive':
                continue
            
            text = link.get_text(strip=True).lower()
            href_lower = href.lower()
            
            # Match if all query parts are in URL or text
            if all(part in href_lower or part in text for part in query_parts):
                import re
                raw_name = link.get_text(strip=True)
                # Remove date patterns (e.g., 'Mar 1-9')
                clean_name = re.split(r'[A-Z][a-z]{2}\s+\d', raw_name)[0].strip()
                # Remove 'Live' prefix
                clean_name = re.sub(r'^Live\s*', '', clean_name)
                # Remove location suffix (city, country)
                clean_name = re.sub(r'[A-Z][a-z]+,\s*[A-Z][a-z]+$', '', clean_name).strip()
                # Extract event_id and slug from URL (/events/{id}/{slug})
                parts = href.split('/')
                event_id = parts[2] if len(parts) > 2 else None
                slug = parts[3] if len(parts) > 3 else None
                results.append({'name': clean_name, 'url': href, 'event_id': event_id, 'slug': slug})
                results.append({'name': clean_name, 'url': href})
        
        # Deduplicate
        seen = set()
        unique = []
        for r in results:
            if r['url'] not in seen:
                seen.add(r['url'])
                unique.append(r)
        return unique
    except Exception as e:
        print(f"Error searching events: {e}")
        return []

def get_event_with_grouped_events(event_url):
    """Get event details including all grouped events"""
    try:
        full_url = f"https://www.hltv.org{event_url}" if event_url.startswith('/') else event_url
        resp = requests.get(full_url, impersonate='chrome142', timeout=10)
        soup = BeautifulSoup(resp.content, 'html.parser')
        
        # Extract event name
        event_name = None
        event_hub = soup.find('div', class_='event-hub')
        if event_hub:
            title = event_hub.find('h1')
            if title:
                event_name = title.get_text(strip=True)
        
        # Extract grouped events
        grouped_events = []
        grouped_container = soup.find('div', class_='linked-events-container-slider')
        if grouped_container:
            for event_div in grouped_container.find_all('a', href=True):
                title_elem = event_div.find('div', class_='linked-event-title')
                if title_elem:
                    sub_name = title_elem.get_text(strip=True)
                    sub_url = event_div.get('href')
                    grouped_events.append({'name': sub_name, 'url': sub_url})
        
        # If no grouped events, return the event itself
        if not grouped_events:
            grouped_events = [{'name': event_name, 'url': event_url}]
        
        return {
            'name': event_name,
            'url': event_url,
            'tier': get_event_tier(event_name) if event_name else None,
            'grouped_events': grouped_events
        }
    except Exception as e:
        print(f"Error getting event details: {e}")
        return None
