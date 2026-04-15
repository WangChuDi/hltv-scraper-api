import datetime
import re
from urllib.parse import quote, urlparse

from bs4 import BeautifulSoup
from curl_cffi import requests

from http_client import (
    HLTV_IMPERSONATION_CHAIN,
    get_with_impersonation_fallback,
)
from liquipedia_scraper import get_event_tier


def _normalize_hltv_event_url(event_url):
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


def _parse_money_amount(text):
    match = re.search(r"\$([\d,]+)", text or "")
    return int(match.group(1).replace(",", "")) if match else None


def _extract_hltv_date_iso(node):
    unix_value = node.get("data-unix") if node else None
    if not unix_value:
        return None

    try:
        return (
            datetime.datetime.utcfromtimestamp(int(unix_value) / 1000)
            .date()
            .isoformat()
        )
    except (TypeError, ValueError):
        return None


def _build_event_result(href, raw_name):
    match = re.match(r"^/events/(\d+)/([^/?#]+)$", href or "")
    if not match:
        return None

    event_id, slug = match.groups()
    clean_name = (raw_name or slug.replace("-", " ").title()).strip()
    clean_name = re.sub(r"^Live\s*", "", clean_name, flags=re.IGNORECASE)
    clean_name = re.sub(
        r"([A-Z][a-z]{2}\s+\d{1,2}(?:st|nd|rd|th)?(?:-[A-Z][a-z]{2}\s+\d{1,2}(?:st|nd|rd|th)?)?).*$",
        "",
        clean_name,
    ).strip()
    clean_name = re.sub(r"\s*(LAN|Online).*$", "", clean_name).strip()

    return {
        "name": clean_name,
        "url": href,
        "event_id": event_id,
        "slug": slug,
    }


def _build_event_result_from_search_entry(entry):
    if not isinstance(entry, dict):
        return None

    return _build_event_result(
        entry.get("location") or entry.get("eventMatchesLocation"),
        entry.get("name"),
    )


def get_live_box_event():
    try:
        resp = get_with_impersonation_fallback(
            "https://www.hltv.org",
            impersonate="chrome142",
            fallback_impersonations=HLTV_IMPERSONATION_CHAIN,
            timeout=10,
        )
        soup = BeautifulSoup(resp.content, "html.parser")

        live_box = soup.find("span", class_="live-box")
        if not live_box:
            return None

        live_link = live_box.find_parent("a")
        if not live_link:
            return None

        href = live_link.get("href")
        if not isinstance(href, str):
            return None

        raw_name = live_link.get_text(" ", strip=True)
        return _build_event_result(href, raw_name)
    except Exception as e:
        print(f"Error getting live-box event: {e}")
        return None


def get_hltv_event_metadata(event_url):
    try:
        event_path = _normalize_hltv_event_url(event_url)
        if not event_path:
            return None
        full_url = f"https://www.hltv.org{event_path}"
        resp = get_with_impersonation_fallback(
            full_url,
            impersonate="chrome142",
            fallback_impersonations=HLTV_IMPERSONATION_CHAIN,
            timeout=10,
        )
        soup = BeautifulSoup(resp.content, "html.parser")

        title = soup.find("h1", class_="event-hub-title")
        raw_name = title.get_text(strip=True) if title else None

        date_nodes = soup.select("td.eventdate span[data-unix]")
        start_date = (
            _extract_hltv_date_iso(date_nodes[0]) if len(date_nodes) >= 1 else None
        )
        end_date = (
            _extract_hltv_date_iso(date_nodes[-1])
            if len(date_nodes) >= 2
            else start_date
        )

        location_cell = soup.find("td", class_="location")
        location_text = (
            " ".join(location_cell.get_text(" ", strip=True).split())
            if location_cell
            else None
        )

        prize_cell = soup.find("td", class_="prizepool")
        prize_text = ""
        if prize_cell:
            prize_title = prize_cell.get("title")
            prize_text = (
                prize_title
                if isinstance(prize_title, str)
                else prize_cell.get_text(" ", strip=True)
            )
        total_prize_pool_usd = _parse_money_amount(prize_text)

        player_prize_pool_usd = None
        club_prize_pool_usd = None
        prize_header = soup.find("th", class_="prizepool")
        if prize_header:
            for row in prize_header.select(".moneyShare-row"):
                left = row.select_one(".moneyShare-row-left")
                right = row.select_one(".moneyShare-row-right")
                label = left.get_text(" ", strip=True) if left else ""
                value_text = right.get_text(" ", strip=True) if right else ""
                if "Player Share" in label:
                    player_prize_pool_usd = _parse_money_amount(value_text)
                elif "Club Share" in label:
                    club_prize_pool_usd = _parse_money_amount(value_text)

        return {
            "raw_name": raw_name,
            "source": "hltv",
            "url": event_path,
            "start_date": start_date,
            "end_date": end_date,
            "location_text": location_text,
            "locations": None,
            "total_prize_pool_usd": total_prize_pool_usd,
            "player_prize_pool_usd": player_prize_pool_usd,
            "club_prize_pool_usd": club_prize_pool_usd,
        }
    except Exception as e:
        print(f"Error getting HLTV event metadata: {e}")
        return None


def search_events(query):
    def collect_event_links(soup):
        links = []
        for a in soup.find_all("a", href=True):
            href = a.get("href")
            if (
                not isinstance(href, str)
                or not href.startswith("/events/")
                or href == "/events/archive"
            ):
                continue
            title_node = a.select_one("div.text-ellipsis")
            text = (
                title_node.get_text(" ", strip=True)
                if title_node
                else a.get_text(" ", strip=True)
            )
            if text:
                links.append((href, text))
        return links

    def matches_query(slug, text, query_parts):
        haystack = f"{slug.lower()} {text.lower()}"
        return all(part in haystack for part in query_parts)

    try:
        query_parts = [part for part in re.findall(r"[a-z0-9]+", query.lower()) if part]
        years = {datetime.datetime.now().year}
        years.update(int(year) for year in re.findall(r"20\d{2}", query))

        search_url = f"https://www.hltv.org/search?term={quote(query)}"
        search_resp = get_with_impersonation_fallback(
            search_url,
            impersonate="chrome124",
            fallback_impersonations=HLTV_IMPERSONATION_CHAIN,
            timeout=10,
        )
        if search_resp.status_code == 200:
            try:
                search_payload = search_resp.json()
            except Exception:
                search_payload = []
            else:
                seen = set()
                results = []
                for group in search_payload if isinstance(search_payload, list) else []:
                    for event in group.get("events", []):
                        event_result = _build_event_result_from_search_entry(event)
                        if not event_result or event_result["url"] in seen:
                            continue
                        if matches_query(
                            event_result["slug"], event_result["name"], query_parts
                        ):
                            seen.add(event_result["url"])
                            results.append(event_result)

                if results:
                    return results

        all_links = []

        resp = get_with_impersonation_fallback(
            "https://www.hltv.org/events",
            impersonate="chrome124",
            fallback_impersonations=HLTV_IMPERSONATION_CHAIN,
            timeout=10,
        )
        if resp.status_code == 200:
            all_links.extend(
                collect_event_links(BeautifulSoup(resp.content, "html.parser"))
            )

        for year in sorted(years):
            archive_url = f"https://www.hltv.org/events/archive?startDate={year}-01-01&endDate={year}-12-31"
            archive_resp = get_with_impersonation_fallback(
                archive_url,
                impersonate="chrome124",
                fallback_impersonations=HLTV_IMPERSONATION_CHAIN,
                timeout=10,
            )
            if archive_resp.status_code == 200:
                all_links.extend(
                    collect_event_links(
                        BeautifulSoup(archive_resp.content, "html.parser")
                    )
                )

        seen = set()
        results = []
        for href, text in all_links:
            if href in seen:
                continue
            event_result = _build_event_result(href, text)
            if event_result and matches_query(
                event_result["slug"], event_result["name"], query_parts
            ):
                seen.add(href)
                results.append(event_result)

        return results
    except Exception as e:
        print(f"Error searching events: {e}")
        return []


def get_event_with_grouped_events(event_url):
    try:
        event_path = _normalize_hltv_event_url(event_url)
        if not event_path:
            return None
        full_url = f"https://www.hltv.org{event_path}"
        resp = get_with_impersonation_fallback(
            full_url,
            impersonate="chrome142",
            fallback_impersonations=HLTV_IMPERSONATION_CHAIN,
            timeout=10,
        )
        soup = BeautifulSoup(resp.content, "html.parser")

        event_name = None
        event_hub = soup.find("div", class_="event-hub")
        if event_hub:
            title = event_hub.find("h1")
            if title:
                event_name = title.get_text(strip=True)

        if not event_name:
            match = re.search(r"/events/\d+/([^/]+)", event_url)
            if match:
                event_name = match.group(1).replace("-", " ").title()

        grouped_events = []
        grouped_container = soup.find("div", class_="linked-events-container-slider")
        if grouped_container:
            for event_div in grouped_container.find_all("a", href=True):
                title_elem = event_div.find("div", class_="linked-event-title")
                sub_url = event_div.get("href")
                if title_elem and isinstance(sub_url, str):
                    sub_name = title_elem.get_text(strip=True)
                    grouped_events.append({"name": sub_name, "url": sub_url})

        if not grouped_events:
            grouped_events = [{"name": event_name, "url": event_url}]

        return {
            "name": event_name,
            "url": event_path,
            "tier": get_event_tier(event_name) if event_name else None,
            "grouped_events": grouped_events,
        }
    except Exception as e:
        print(f"Error getting event details: {e}")
        return None
