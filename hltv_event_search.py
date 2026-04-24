import datetime
import re
from collections import OrderedDict
from urllib.parse import quote, urlparse

from bs4 import BeautifulSoup

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

    location = (
        entry.get("location")
        or entry.get("link")
        or entry.get("url")
    )
    normalized_location = _normalize_hltv_event_url(location)

    return _build_event_result(
        normalized_location,
        entry.get("name") or entry.get("title"),
    )


def _collect_event_links(soup):
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


def _matches_query(slug, text, query_parts):
    haystack = f"{slug.lower()} {text.lower()}"
    return all(part in haystack for part in query_parts)


def _iter_search_event_entries(search_payload):
    if isinstance(search_payload, dict):
        direct_events = search_payload.get("events")
        if isinstance(direct_events, list):
            for event in direct_events:
                if isinstance(event, dict):
                    yield event
            return

        payload_iterable = search_payload.values()
    elif isinstance(search_payload, list):
        payload_iterable = search_payload
    else:
        return

    for group in payload_iterable:
        if not isinstance(group, dict):
            continue

        events = group.get("events")
        if isinstance(events, list):
            for event in events:
                if isinstance(event, dict):
                    yield event
            continue

        if any(key in group for key in ("id", "location", "link", "url")):
            yield group


def _search_events_from_payload(search_payload, query_parts):
    seen = set()
    results = []

    for event in _iter_search_event_entries(search_payload):
        event_result = _build_event_result_from_search_entry(event)
        if not event_result or event_result["url"] in seen:
            continue
        if _matches_query(event_result["slug"], event_result["name"], query_parts):
            seen.add(event_result["url"])
            results.append(event_result)

    return results


def _fetch_archive_links_for_year(year, offset=0):
    archive_url = (
        f"https://www.hltv.org/events/archive?startDate={year}-01-01&endDate={year}-12-31"
        f"&offset={offset}"
    )
    archive_resp = get_with_impersonation_fallback(
        archive_url,
        impersonate="chrome124",
        fallback_impersonations=HLTV_IMPERSONATION_CHAIN,
        timeout=10,
    )
    if archive_resp.status_code != 200:
        return []
    return _collect_event_links(BeautifulSoup(archive_resp.content, "html.parser"))


def _iter_archive_links_for_year(year, *, stop_after_short_page=False):
    offset = 0
    while True:
        archive_links = _fetch_archive_links_for_year(year, offset)
        if not archive_links:
            break
        for link in archive_links:
            yield link
        if stop_after_short_page and len(archive_links) < 50:
            break
        offset += 50


_EVENT_BY_ID_CACHE = OrderedDict()
_EVENT_BY_ID_CACHE_LIMIT = 128


def _get_cached_event_by_id(event_id_str):
    cached_event = _EVENT_BY_ID_CACHE.get(event_id_str)
    if cached_event is not None:
        _EVENT_BY_ID_CACHE.move_to_end(event_id_str)
    return cached_event


def _cache_event_by_id(event_id_str, event_result):
    _EVENT_BY_ID_CACHE[event_id_str] = event_result
    _EVENT_BY_ID_CACHE.move_to_end(event_id_str)
    while len(_EVENT_BY_ID_CACHE) > _EVENT_BY_ID_CACHE_LIMIT:
        _EVENT_BY_ID_CACHE.popitem(last=False)


def get_live_box_event():
    try:
        resp = get_with_impersonation_fallback(
            "https://www.hltv.org",
            impersonate="chrome136",
            fallback_impersonations=HLTV_IMPERSONATION_CHAIN,
            timeout=10,
        )
        if resp.status_code != 200:
            return None

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
            impersonate="chrome136",
            fallback_impersonations=HLTV_IMPERSONATION_CHAIN,
            timeout=10,
        )
        if resp.status_code != 200:
            return None

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
    try:
        query_parts = [part for part in re.findall(r"[a-z0-9]+", query.lower()) if part]
        years = {datetime.datetime.now().year}
        years.update(int(year) for year in re.findall(r"20\d{2}", query))

        def _safe_search_payload(response):
            try:
                payload = response.json()
            except Exception:
                payload = []

            return payload if isinstance(payload, (dict, list)) else []

        query_search_resp = get_with_impersonation_fallback(
            f"https://www.hltv.org/search?query={quote(query)}",
            impersonate="chrome124",
            fallback_impersonations=HLTV_IMPERSONATION_CHAIN,
            timeout=10,
        )
        if query_search_resp.status_code == 200:
            query_content = getattr(query_search_resp, "content", None)
            query_links = []
            has_query_html = isinstance(query_content, (bytes, str))
            if has_query_html:
                query_links = _collect_event_links(
                    BeautifulSoup(query_content, "html.parser")
                )

            seen = set()
            results = []
            for href, text in query_links:
                if href in seen:
                    continue
                event_result = _build_event_result(href, text)
                if event_result and _matches_query(
                    event_result["slug"], event_result["name"], query_parts
                ):
                    seen.add(href)
                    results.append(event_result)

            if results:
                return results

            if not has_query_html:
                results = _search_events_from_payload(
                    _safe_search_payload(query_search_resp), query_parts
                )
                if results:
                    return results

        if isinstance(getattr(query_search_resp, "content", None), (bytes, str)):
            search_resp = get_with_impersonation_fallback(
                f"https://www.hltv.org/search?term={quote(query)}",
                impersonate="chrome124",
                fallback_impersonations=HLTV_IMPERSONATION_CHAIN,
                timeout=10,
            )
            if search_resp.status_code == 200:
                results = _search_events_from_payload(
                    _safe_search_payload(search_resp), query_parts
                )
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
                _collect_event_links(BeautifulSoup(resp.content, "html.parser"))
            )

        for year in sorted(years):
            all_links.extend(
                _iter_archive_links_for_year(year, stop_after_short_page=True)
            )

        seen = set()
        results = []
        for href, text in all_links:
            if href in seen:
                continue
            event_result = _build_event_result(href, text)
            if event_result and _matches_query(
                event_result["slug"], event_result["name"], query_parts
            ):
                seen.add(href)
                results.append(event_result)

        return results
    except Exception as e:
        print(f"Error searching events: {e}")
        return []


def find_event_by_id(event_id):
    try:
        event_id_str = str(event_id).strip()
        if not event_id_str.isdigit():
            return None

        cached_event = _get_cached_event_by_id(event_id_str)
        if cached_event is not None:
            return cached_event

        search_url = f"https://www.hltv.org/search?term={quote(event_id_str)}"
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

            for event in _iter_search_event_entries(search_payload):
                event_result = _build_event_result_from_search_entry(event)
                if event_result and event_result.get("event_id") == event_id_str:
                    _cache_event_by_id(event_id_str, event_result)
                    return event_result

        events_resp = get_with_impersonation_fallback(
            "https://www.hltv.org/events",
            impersonate="chrome124",
            fallback_impersonations=HLTV_IMPERSONATION_CHAIN,
            timeout=10,
        )
        if events_resp.status_code == 200:
            for href, text in _collect_event_links(
                BeautifulSoup(events_resp.content, "html.parser")
            ):
                event_result = _build_event_result(href, text)
                if event_result and event_result.get("event_id") == event_id_str:
                    _cache_event_by_id(event_id_str, event_result)
                    return event_result

        current_year = datetime.datetime.now().year
        for year in range(current_year, 2011, -1):
            for href, text in _iter_archive_links_for_year(year):
                event_result = _build_event_result(href, text)
                if event_result and event_result.get("event_id") == event_id_str:
                    _cache_event_by_id(event_id_str, event_result)
                    return event_result

        return None
    except Exception as e:
        print(f"Error finding event by id: {e}")
        return None


def get_event_with_grouped_events(event_url):
    try:
        event_path = _normalize_hltv_event_url(event_url)
        if not event_path:
            return None
        full_url = f"https://www.hltv.org{event_path}"
        resp = get_with_impersonation_fallback(
            full_url,
            impersonate="chrome136",
            fallback_impersonations=HLTV_IMPERSONATION_CHAIN,
            timeout=10,
        )
        if resp.status_code != 200:
            return None

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
