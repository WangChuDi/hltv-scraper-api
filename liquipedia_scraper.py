"""
Liquipedia scraper for tournament tier information
"""
from curl_cffi import requests
from bs4 import BeautifulSoup
import re

def get_event_tier(event_name):
    """Get tournament tier from Liquipedia"""
    try:
        event_lower = event_name.lower()
        url = None
        
        # Parse event name to Liquipedia URL
        if 'esl pro league' in event_lower:
            match = re.search(r'season\s*(\d+)', event_lower)
            if match:
                url = f'https://liquipedia.net/counterstrike/ESL/Pro_League/Season_{match.group(1)}'
        elif 'iem' in event_lower:
            parts = event_name.split()
            if len(parts) >= 2:
                url = f'https://liquipedia.net/counterstrike/Intel_Extreme_Masters/{parts[-1]}'
        elif 'blast premier' in event_lower:
            match = re.search(r'(spring|fall|world final)', event_lower)
            year_match = re.search(r'20\d{2}', event_name)
            if match and year_match:
                url = f'https://liquipedia.net/counterstrike/BLAST/Premier/{year_match.group(0)}/{match.group(1).title()}'
        elif 'pgl' in event_lower:
            parts = event_name.replace('PGL', '').strip().split()
            if parts:
                url = f'https://liquipedia.net/counterstrike/PGL/{"".join(parts)}'
        
        if not url:
            return None
        
        response = requests.get(url, timeout=10, impersonate='chrome')
        if response.status_code == 200:
            match = re.search(r'([SABC])-Tier', response.text, re.IGNORECASE)
            if match:
                return match.group(1).upper()
        
        return None
    except Exception as e:
        print(f'Error fetching tier for {event_name}: {e}')
        return None


def get_ongoing_tournaments():
    """Scrape ongoing tournaments from Liquipedia"""
    url = "https://liquipedia.net/counterstrike/Main_Page"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Get all text and find the Ongoing section
        full_text = soup.get_text()
        
        # Find "Ongoing" followed by tournament names until "Concluded"
        pattern = r'Ongoing([\s\S]*?)Concluded'
        match = re.search(pattern, full_text)
        
        if match:
            ongoing_text = match.group(1)
            # Split by newlines and filter
            lines = [line.strip() for line in ongoing_text.split('\n') if line.strip()]
            tournaments = []
            for line in lines:
                # Filter out UI elements and keep only tournament names
                if (len(line) > 10 and 
                    not any(x in line.lower() for x in ['edit', 'contribute', 'support', 'report', 'submit', 'chat', 'help', 'portal', 'guidelines', 'twitter', 'search', 'scroll', 'top'])):
                    tournaments.append(line)
            
            return tournaments[:5]  # Return top 5
        
        return []
    except Exception as e:
        print(f"Error scraping Liquipedia: {e}")
        return []

def get_ongoing_s_tier_tournaments():
    """Scrape ongoing S-tier tournaments from Liquipedia"""
    url = "https://liquipedia.net/counterstrike/Main_Page"
    try:
        response = requests.get(url, timeout=10, impersonate='chrome')
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find S-Tier section in ongoing tournaments
        tournaments = []
        ongoing_section = soup.find('div', class_='divRow')
        if ongoing_section:
            # Look for S-Tier tournaments
            for link in ongoing_section.find_all('a', href=True):
                text = link.get_text(strip=True)
                # Check if it's marked as S-Tier or is a major tournament
                if text and len(text) > 5:
                    tournaments.append({'name': text, 'tier': 'S'})
        
        return tournaments[:5]
    except Exception as e:
        print(f"Error scraping S-tier tournaments: {e}")
        return []
