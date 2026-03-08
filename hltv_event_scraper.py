"""
HLTV Event scraper for grouped events
"""
from curl_cffi import requests
from bs4 import BeautifulSoup

def get_event_details(event_url):
    """Get event details including grouped events"""
    try:
        response = requests.get(event_url, impersonate="chrome142", timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        
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
                    sub_url = 'https://www.hltv.org' + event_div.get('href')
                    grouped_events.append({'name': sub_name, 'url': sub_url})
        
        return {
            'name': event_name,
            'url': event_url,
            'grouped_events': grouped_events
        }
    except Exception as e:
        print(f"Error scraping event: {e}")
        return None
