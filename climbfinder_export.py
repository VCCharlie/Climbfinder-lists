"""
Parse Climbfinder ranking and climb detail pages for structured export.

Used by streamlit_app for personal aggregation workflows.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE = "https://climbfinder.com/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

# flag-icon-fr → ISO 3166-1 alpha-2 (common on Climbfinder)
FLAG_ICON_TO_ISO2 = {
    "fr": "FR", "es": "ES", "it": "IT", "de": "DE", "nl": "NL", "be": "BE",
    "gb": "GB", "pt": "PT", "ch": "CH", "at": "AT", "ad": "AD", "pl": "PL",
    "no": "NO", "us": "US", "si": "SI", "hr": "HR", "co": "CO", "sk": "SK",
    "cz": "CZ", "se": "SE", "dk": "DK", "ie": "IE", "lu": "LU", "fi": "FI",
    "gr": "GR", "hu": "HU", "ro": "RO", "ua": "UA", "bg": "BG", "rs": "RS",
    "ba": "BA", "me": "ME", "al": "AL", "mk": "MK", "mt": "MT", "cy": "CY",
    "is": "IS", "li": "LI", "mc": "MC", "sm": "SM", "va": "VA", "br": "BR",
    "mx": "MX", "ar": "AR", "cl": "CL", "ec": "EC", "nz": "NZ", "au": "AU",
    "ca": "CA", "jp": "JP", "kr": "KR", "tw": "TW", "cn": "CN", "in": "IN",
    "za": "ZA", "ma": "MA", "tn": "TN", "dz": "DZ", "il": "IL", "tr": "TR",
    "ru": "RU", "by": "BY", "md": "MD", "ge": "GE", "am": "AM", "az": "AZ",
    "kg": "KG", "kz": "KZ", "uz": "UZ", "th": "TH", "vn": "VN", "id": "ID",
    "my": "MY", "ph": "PH", "sg": "SG", "hk": "HK", "ae": "AE", "sa": "SA",
    "eg": "EG", "ke": "KE", "rw": "RW", "ug": "UG", "et": "ET", "ng": "NG",
    "ve": "VE", "pe": "PE", "uy": "UY", "py": "PY", "bo": "BO", "cr": "CR",
    "pa": "PA", "gt": "GT", "cu": "CU", "do": "DO", "pr": "PR", "jm": "JM",
    "tt": "TT", "fk": "FK", "gs": "GS", "gi": "GI", "gg": "GG", "je": "JE",
    "im": "IM", "ax": "AX", "fo": "FO", "gl": "GL", "sj": "SJ", "bv": "BV",
}


def new_http_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://climbfinder.com/en/ranking",
    })
    return s


def fetch_ranking_html(region_id: int | str, page: int, session: requests.Session | None = None) -> str:
    own = session is None
    if own:
        session = new_http_session()
    url = f"{BASE}en/ranking?l={region_id}&p={page}"
    r = session.get(url, timeout=25)
    r.raise_for_status()
    return r.text


def short_name_from_url(page_url: str) -> str:
    path = urlparse(page_url).path.strip("/").split("/")[-1] or ""
    return path.replace("-", " ").title() if path else ""


def fetch_climb_html(path_or_url: str, session: requests.Session | None = None) -> str:
    own = session is None
    if own:
        session = new_http_session()
    if path_or_url.startswith("http"):
        url = path_or_url
    else:
        url = urljoin(BASE, path_or_url.lstrip("/"))
    r = session.get(url, timeout=25)
    r.raise_for_status()
    return r.text


def _flag_iso_from_item(item: BeautifulSoup) -> str:
    span = item.select_one(".ranking-item-flag span[class*='flag-icon-']")
    if not span:
        return ""
    classes = span.get("class") or []
    for c in classes:
        if c.startswith("flag-icon-") and c != "flag-icon":
            code = c.replace("flag-icon-", "").strip()
            return FLAG_ICON_TO_ISO2.get(code, code.upper() if len(code) == 2 else "")
    return ""


def parse_ranking_items(html: str) -> list[dict[str, Any]]:
    """Extract climb rows from a ranking page HTML."""
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict[str, Any]] = []
    for block in soup.select("div.ranking-item-item"):
        link = block.select_one('a.ranking-item-link[href*="climbs/"]')
        if not link or not link.get("href"):
            continue
        href = link["href"].strip()
        if "climbs/" not in href or href.rstrip("/").endswith("climbs"):
            continue
        title = (link.get("title") or "").strip()
        name_el = block.select_one("a.ranking-card-title")
        short_name = name_el.get_text(strip=True) if name_el else ""
        display_name = title or short_name
        path = href.split("?", 1)[0]
        full_url = urljoin(BASE, path)

        climb_id = None
        for btn in block.select("button[data-id]"):
            did = btn.get("data-id")
            if did and did.isdigit():
                climb_id = int(did)
                break

        def stat(sel: str) -> str:
            el = block.select_one(sel)
            return el.get_text(" ", strip=True) if el else ""

        length_t = stat(".ranking-item-length")
        grad_t = stat(".ranking-item-gradient")
        pts_t = stat(".ranking-item-cotacol")
        ascent_t = stat(".ranking-item-ascent")
        finish_t = stat(".ranking-item-finish")

        cat_el = block.select_one(".ranking-item-category")
        category = cat_el.get_text(strip=True) if cat_el else ""

        out.append({
            "climb_id": climb_id,
            "name": display_name,
            "short_name": short_name,
            "path": path,
            "url": full_url,
            "country_iso2": _flag_iso_from_item(block),
            "length_km": _parse_float_stat(length_t),
            "avg_grade": _parse_float_stat(grad_t),
            "difficulty_points": _parse_int_stat(pts_t),
            "ascent_m": _parse_int_stat(ascent_t),
            "summit_m": _parse_int_stat(finish_t),
            "category": category,
        })
    return out


def _parse_float_stat(s: str) -> float:
    if not s:
        return 0.0
    m = re.search(r"([\d]+(?:[.,]\d+)?)", s.replace(",", ""))
    if not m:
        return 0.0
    return float(m.group(1).replace(",", "."))


def _parse_int_stat(s: str) -> int:
    if not s:
        return 0
    m = re.search(r"([\d]+)", s.replace(",", ""))
    return int(m.group(1)) if m else 0


def _linestring_coords(html: str) -> list[list[float]]:
    idx = html.find('"type": "LineString"')
    if idx < 0:
        return []
    sub = html[idx : idx + 500000]
    co = sub.find('"coordinates":')
    if co < 0:
        return []
    b = sub.find("[[", co)
    if b < 0:
        return []
    depth = 0
    for k in range(b, len(sub)):
        if sub[k] == "[":
            depth += 1
        elif sub[k] == "]":
            depth -= 1
            if depth == 0:
                try:
                    arr = json.loads(sub[b : k + 1])
                    return arr if isinstance(arr, list) else []
                except json.JSONDecodeError:
                    return []
    return []


def _point_coords(html: str) -> tuple[float, float] | None:
    # Finish marker: Point after finishgeojson
    idx = html.find("const finishgeojson")
    if idx < 0:
        idx = html.find('"type": "Point"')
    if idx < 0:
        return None
    sub = html[idx : idx + 8000]
    m = re.search(r'"coordinates":\s*\[\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\]', sub)
    if not m:
        return None
    return float(m.group(1)), float(m.group(2))


def _parse_stats_table(soup: BeautifulSoup) -> dict[str, Any]:
    stats: dict[str, Any] = {}
    for tr in soup.select("table tr"):
        th = tr.find("th")
        td = tr.find("td")
        if not th or not td:
            continue
        label = th.get_text(" ", strip=True).lower()
        val = td.get_text(" ", strip=True)
        if "difficulty" in label and "point" in label:
            stats["difficulty_points"] = _parse_int_stat(val)
        elif label.startswith("length") or "length" == label.split()[0]:
            stats["length_km"] = _parse_float_stat(val)
        elif "average" in label and "gradient" in label:
            stats["avg_grade"] = _parse_float_stat(val)
        elif "steepest" in label:
            stats["max_grade"] = _parse_float_stat(val)
        elif "total ascent" in label:
            stats["ascent_m"] = _parse_int_stat(val)
    return stats


def _summit_m_from_blurb(html: str) -> int:
    m = re.search(
        r"(?:summit|top of the ascent|located at)\s+(?:is\s+)?(?:at\s+)?(\d{3,4})\s*m",
        html,
        re.IGNORECASE,
    )
    if m:
        return int(m.group(1))
    return 0


def parse_climb_detail(html: str, page_url: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    m = re.search(r"const\s+climbId\s*=\s*(\d+)\s*;", html)
    climb_id = int(m.group(1)) if m else 0

    line = _linestring_coords(html)
    start_lon, start_lat = (line[0][0], line[0][1]) if len(line) >= 1 else (0.0, 0.0)
    finish = _point_coords(html)
    if finish:
        lon_top, lat_top = finish
    elif len(line) >= 2:
        lon_top, lat_top = line[-1][0], line[-1][1]
    else:
        lon_top, lat_top = 0.0, 0.0

    tbl = _parse_stats_table(soup)
    alt_top = _summit_m_from_blurb(html)
    ascent = int(tbl.get("ascent_m") or 0)
    if alt_top and ascent:
        alt_start = alt_top - ascent
    else:
        alt_start = 0

    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.split("|")[0].strip()
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        title = og["content"].strip()

    cat = ""
    finish_block = re.search(r"const finishgeojson\s*=\s*\{[\s\S]*?'category':\s*'([^']+)'", html)
    if finish_block:
        cat = finish_block.group(1).strip()

    return {
        "climb_id": climb_id,
        "page_url": page_url,
        "title": title or short_name_from_url(page_url),
        "start_lat": round(start_lat, 5),
        "start_lon": round(start_lon, 5),
        "lat": round(lat_top, 5),
        "lon": round(lon_top, 5),
        "alt_top": alt_top,
        "alt_start": alt_start,
        "length_km": float(tbl.get("length_km") or 0),
        "avg_grade": float(tbl.get("avg_grade") or 0),
        "max_grade": float(tbl.get("max_grade") or 0),
        "ascent_m": ascent,
        "difficulty_points": int(tbl.get("difficulty_points") or 0),
        "category": cat,
    }


def build_export_object(
    detail: dict[str, Any],
    summary: dict[str, Any],
    region_label: str,
) -> dict[str, Any]:
    """Shape compatible with user's mountain-list JSON (BIG-like keys)."""
    cid = detail.get("climb_id") or summary.get("climb_id") or 0
    slug = urlparse(detail.get("page_url") or summary.get("url", "")).path.strip("/").split("/")[-1] or "climb"
    ext_id = f"cf_{cid}_{slug}"[:80]

    name = summary.get("name") or detail.get("title") or slug
    url = detail.get("page_url") or summary.get("url") or ""
    country = summary.get("country_iso2") or ""
    region = region_label or ""

    alt_top = int(detail.get("alt_top") or summary.get("summit_m") or 0)
    alt_start = int(detail.get("alt_start") or 0)
    if alt_start <= 0 and alt_top and detail.get("ascent_m"):
        alt_start = alt_top - int(detail["ascent_m"])

    length = float(detail.get("length_km") or summary.get("length_km") or 0)
    avg_g = float(detail.get("avg_grade") or summary.get("avg_grade") or 0)
    max_g = float(detail.get("max_grade") or 0)
    elev_gain = int(detail.get("ascent_m") or summary.get("ascent_m") or 0)
    pts = int(detail.get("difficulty_points") or summary.get("difficulty_points") or 0)
    cat = (detail.get("category") or summary.get("category") or "").strip()
    # Climbfinder difficulty points → score (same scale as on site); fiets not applicable
    score = pts

    return {
        "id": ext_id,
        "name": name,
        "sideUrl": url,
        "country": country,
        "region": region,
        "lat": detail.get("lat") or 0.0,
        "lon": detail.get("lon") or 0.0,
        "altTop": alt_top,
        "startLat": detail.get("start_lat") or 0.0,
        "startLon": detail.get("start_lon") or 0.0,
        "altStart": alt_start,
        "elevation": elev_gain,
        "lengthKm": round(length, 2) if length else 0.0,
        "avgGrade": round(avg_g, 2) if avg_g else 0.0,
        "maxGrade": round(max_g, 2) if max_g else 0.0,
        "score": score,
        "fiets": None,
        "cat": cat,
        "url": url,
        "bigId": cid,
        "source": "Climbfinder.com",
    }


def fetch_details_with_delay(
    rows: list[dict[str, Any]],
    delay_s: float = 0.75,
    session: requests.Session | None = None,
) -> list[tuple[dict[str, Any], str | None]]:
    """Fetch detail pages for ranking rows. Returns (detail_dict, error)."""
    own = session is None
    if own:
        session = new_http_session()
    results: list[tuple[dict[str, Any], str | None]] = []
    for i, row in enumerate(rows):
        url = row.get("url") or ""
        if not url:
            results.append(({}, "missing url"))
            continue
        try:
            html = fetch_climb_html(url, session=session)
            d = parse_climb_detail(html, url)
            results.append((d, None))
        except Exception as exc:  # noqa: BLE001
            results.append(({}, str(exc)))
        if i < len(rows) - 1 and delay_s > 0:
            time.sleep(delay_s)
    return results
