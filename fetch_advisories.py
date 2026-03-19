#!/usr/bin/env python3
"""
VAC Advisory Data Fetcher
Runs server-side (no CORS restrictions) to fetch all 4 government advisory sources.
Writes advisory_data.json which the dashboard reads directly.
"""

import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ── VAC city config ────────────────────────────────────────────────────────────
VAC_CITIES = [
    {"city": "Ouagadougou", "country": "Burkina Faso",  "iso": "BF", "uk": "burkina-faso",                        "regional": True},
    {"city": "Bamako",      "country": "Mali",           "iso": "ML", "uk": "mali",                                "regional": False},
    {"city": "Niamey",      "country": "Niger",          "iso": "NE", "uk": "niger",                               "regional": False},
    {"city": "Yaoundé",     "country": "Cameroon",       "iso": "CM", "uk": "cameroon",                            "regional": True},
    {"city": "Kinshasa",    "country": "DR Congo",       "iso": "CD", "uk": "democratic-republic-of-the-congo",    "regional": True},
    {"city": "Addis Ababa", "country": "Ethiopia",       "iso": "ET", "uk": "ethiopia",                            "regional": True},
    {"city": "Abidjan",     "country": "Côte d'Ivoire",  "iso": "CI", "uk": "cote-d-ivoire",                       "regional": True},
    {"city": "Conakry",     "country": "Guinea",         "iso": "GN", "uk": "guinea",                              "regional": False},
    {"city": "Accra",       "country": "Ghana",          "iso": "GH", "uk": "ghana",                               "regional": False},
    {"city": "Abuja",       "country": "Nigeria",        "iso": "NG", "uk": "nigeria",                             "regional": True},
    {"city": "Lagos",       "country": "Nigeria",        "iso": "NG", "uk": "nigeria",                             "regional": True},
    {"city": "Nairobi",     "country": "Kenya",          "iso": "KE", "uk": "kenya",                               "regional": True},
    {"city": "Antananarivo","country": "Madagascar",     "iso": "MG", "uk": "madagascar",                          "regional": False},
    {"city": "Pretoria",    "country": "South Africa",   "iso": "ZA", "uk": "south-africa",                        "regional": True},
    {"city": "Cape Town",   "country": "South Africa",   "iso": "ZA", "uk": "south-africa",                        "regional": True},
    {"city": "Port Louis",  "country": "Mauritius",      "iso": "MU", "uk": "mauritius",                           "regional": False},
    {"city": "Dakar",       "country": "Senegal",        "iso": "SN", "uk": "senegal",                             "regional": False},
]

# ── Fallback data (used if a source fails) ─────────────────────────────────────
FALLBACK = {
    "ca": {"BF":4,"ML":4,"NE":2,"CM":2,"CD":3,"ET":3,"CI":2,"GN":2,"GH":2,"NG":2,"KE":2,"MG":2,"ZA":2,"MU":2,"SN":2},
    "us": {"BF":4,"ML":4,"NE":4,"CM":2,"CD":4,"ET":3,"CI":2,"GN":2,"GH":2,"NG":3,"KE":2,"MG":2,"ZA":2,"MU":1,"SN":1},
    "uk": {"BF":4,"ML":4,"NE":4,"CM":2,"CD":2,"ET":2,"CI":2,"GN":2,"GH":2,"NG":2,"KE":2,"MG":2,"ZA":2,"MU":1,"SN":2},
    "au": {"BF":4,"ML":4,"NE":4,"CM":2,"CD":4,"ET":3,"CI":2,"GN":2,"GH":2,"NG":3,"KE":2,"MG":2,"ZA":2,"MU":2,"SN":2},
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; VAC-Advisory-Monitor/2.0; +https://github.com/vac-advisory)",
    "Accept": "application/json, application/xml, text/html, */*",
}

def get(url, timeout=20):
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r

# ── CANADA ─────────────────────────────────────────────────────────────────────
def fetch_canada():
    """Official GoC JSON API — advisory-state 0-4 maps to L1-L4."""
    print("Fetching Canada...")
    state_map = {0: 1, 1: 2, 2: 2, 3: 3, 4: 4}
    try:
        data = get("https://data.international.gc.ca/travel-voyage/index-updated.json").json()
        result = {}
        for iso, rec in data.get("data", {}).items():
            state = rec.get("advisory-state")
            if state is not None:
                result[iso.upper()] = state_map.get(state, 2)
        print(f"  Canada: {len(result)} countries")
        return result, True
    except Exception as e:
        print(f"  Canada FAILED: {e} — using fallback")
        return FALLBACK["ca"].copy(), False

# ── USA ────────────────────────────────────────────────────────────────────────
def fetch_usa():
    """Official State Dept RSS feed. Extract level from item title text."""
    print("Fetching USA...")
    try:
        xml_text = get("https://travel.state.gov/_res/rss/TAsTWs.xml").text
        result = {}
        # Parse with ElementTree
        root = ET.fromstring(xml_text)
        ns = {"dc": "http://purl.org/dc/elements/1.1/"}
        for item in root.iter("item"):
            title_el = item.find("title")
            if title_el is None or not title_el.text:
                continue
            title = title_el.text.strip()
            # Find ISO from category[domain=Country-Tag]
            iso = None
            lvl = None
            for cat in item.iter("category"):
                domain = cat.get("domain", "")
                text = (cat.text or "").strip()
                if domain == "Country-Tag":
                    iso = text.upper()
                elif domain == "Threat-Level":
                    m = re.search(r"Level\s*(\d)", text, re.I)
                    if m:
                        lvl = int(m.group(1))
            # Fallback: extract from title "Country - Level N: ..."
            if iso and lvl is None:
                m = re.search(r"Level\s*(\d)", title, re.I)
                if m:
                    lvl = int(m.group(1))
            if iso and lvl:
                result[iso] = lvl
        print(f"  USA: {len(result)} countries")
        return result, True
    except Exception as e:
        print(f"  USA FAILED: {e} — using fallback")
        return FALLBACK["us"].copy(), False

# ── UK FCDO ────────────────────────────────────────────────────────────────────
def parse_uk_level(html_lower, slug):
    """Parse FCDO advisory level from page HTML."""
    if "advise against all travel" in html_lower and "all but essential" not in html_lower:
        return 4
    if "all but essential travel to the whole" in html_lower:
        return 3
    if "all but essential travel overall" in html_lower:
        return 3
    if "all but essential travel" in html_lower and "parts of" not in html_lower:
        return 3
    if ("all but essential travel to parts" in html_lower
            or "advise against travel to some" in html_lower
            or "parts of the country" in html_lower):
        return 2
    if "exercise normal" in html_lower or "no travel warnings" in html_lower:
        return 1
    return 2  # conservative default

def fetch_uk():
    """Scrape FCDO country pages. Deduplicated by slug."""
    print("Fetching UK FCDO...")
    slug_cache = {}
    result = {}
    slugs_needed = {c["iso"]: c["uk"] for c in VAC_CITIES}

    for iso, slug in slugs_needed.items():
        if slug in slug_cache:
            result[iso] = slug_cache[slug]
            continue
        try:
            html = get(f"https://www.gov.uk/foreign-travel-advice/{slug}").text
            lvl = parse_uk_level(html.lower(), slug)
            slug_cache[slug] = lvl
            result[iso] = lvl
            print(f"  UK {slug}: L{lvl}")
        except Exception as e:
            print(f"  UK {slug} FAILED: {e}")
            result[iso] = FALLBACK["uk"].get(iso, 2)
            slug_cache[slug] = result[iso]

    return result, True

# ── AUSTRALIA ──────────────────────────────────────────────────────────────────
# The destinations-export API endpoint is unreliable.
# We scrape individual country pages instead — same approach as UK FCDO.
AU_SLUG_MAP = {
    "BF": "africa/burkina-faso",
    "ML": "africa/mali",
    "NE": "africa/niger",
    "CM": "africa/cameroon",
    "CD": "africa/democratic-republic-congo",
    "ET": "africa/ethiopia",
    "CI": "africa/cote-divoire",
    "GN": "africa/guinea",
    "GH": "africa/ghana",
    "NG": "africa/nigeria",
    "KE": "africa/kenya",
    "MG": "africa/madagascar",
    "ZA": "africa/south-africa",
    "MU": "africa/mauritius",
    "SN": "africa/senegal",
}

def parse_au_level(html_lower):
    """Parse Smartraveller advisory level from page HTML.
    Smartraveller uses these exact phrases in their advice level banners:
      Level 1: 'exercise normal safety precautions'
      Level 2: 'exercise a high degree of caution'
      Level 3: 'reconsider your need to travel'
      Level 4: 'do not travel'
    """
    if "do not travel" in html_lower:
        return 4
    if "reconsider your need to travel" in html_lower:
        return 3
    if "high degree of caution" in html_lower:
        return 2
    if "exercise normal safety precautions" in html_lower or "normal safety precautions" in html_lower:
        return 1
    return 2  # conservative default

def fetch_australia():
    """Scrape individual Smartraveller country pages. Deduplicated by slug."""
    print("Fetching Australia (page scrape)...")
    slug_cache = {}
    result = {}
    ok_count = 0
    fail_count = 0

    for iso, slug in AU_SLUG_MAP.items():
        if slug in slug_cache:
            result[iso] = slug_cache[slug]
            continue
        try:
            html = get(f"https://www.smartraveller.gov.au/destinations/{slug}").text
            lvl = parse_au_level(html.lower())
            slug_cache[slug] = lvl
            result[iso] = lvl
            print(f"  AU {slug}: L{lvl}")
            ok_count += 1
        except Exception as e:
            print(f"  AU {slug} FAILED: {e}")
            slug_cache[slug] = FALLBACK["au"].get(iso, 2)
            result[iso] = FALLBACK["au"].get(iso, 2)
            fail_count += 1

    all_ok = fail_count == 0
    print(f"  Australia: {ok_count} live, {fail_count} fallback")
    return result, all_ok

# ── WCRI SCORING ───────────────────────────────────────────────────────────────
PTS = {1: 10, 2: 40, 3: 70, 4: 100}
W   = {"ca": 0.25, "us": 0.30, "uk": 0.25, "au": 0.20}

def calc_wcri(ca, us, uk, au, regional):
    levels = [ca, us, uk, au]
    weighted = sum(PTS.get(v, 0) * w for v, w in zip(levels, W.values()))
    spread = max(levels) - min(levels)
    penalty = 25 if spread >= 3 else (15 if spread >= 2 else 0)
    bonus = 5 if regional else 0
    return min(100, round(weighted + penalty + bonus))

def get_band(score):
    if score >= 76: return "EXTREME"
    if score >= 56: return "HIGH"
    if score >= 31: return "ELEVATED"
    return "MANAGEABLE"

# ── NOTES ──────────────────────────────────────────────────────────────────────
NOTES = {
    "BF": "Terrorism, kidnapping & armed conflict nationwide",
    "ML": "Terrorism, kidnapping, unpredictable security",
    "NE": "DIVERGENCE: Canada L2 vs US/UK/AU L4 — kidnap & terror risk very high",
    "CM": "Far North & anglophone NW/SW regions highest risk",
    "CD": "Eastern DRC extremely volatile; sources diverge significantly",
    "ET": "Tigray, Amhara, Oromia active conflict zones",
    "CI": "Borders with Burkina Faso & Mali rated highest risk",
    "GN": "Crime, political instability, civil unrest",
    "GH": "Relatively stable; Bawku area higher risk (UK FCDO)",
    "NG": "NE Boko Haram zones; US/AU rate higher than CA/UK",
    "KE": "Terrorism risk; N. Kenya & Somali border highest risk",
    "MG": "Crime, political instability",
    "ZA": "High violent crime & carjacking rates",
    "MU": "Relatively safe; Canada/AU L2 vs US/UK L1",
    "SN": "Generally stable; US most relaxed of 4 sources",
}

# ── MAIN ───────────────────────────────────────────────────────────────────────
def main():
    now = datetime.now(timezone.utc).isoformat()
    print(f"\n{'='*60}")
    print(f"VAC Advisory Fetch — {now}")
    print(f"{'='*60}")

    ca_data, ca_ok = fetch_canada()
    us_data, us_ok = fetch_usa()
    uk_data, uk_ok = fetch_uk()
    au_data, au_ok = fetch_australia()

    cities = []
    seen_iso = {}  # for deduplication of scoring (same country, multiple cities)

    for c in VAC_CITIES:
        iso = c["iso"]
        ca  = ca_data.get(iso, FALLBACK["ca"].get(iso, 2))
        us  = us_data.get(iso, FALLBACK["us"].get(iso, 2))
        uk  = uk_data.get(iso, FALLBACK["uk"].get(iso, 2))
        au  = au_data.get(iso, FALLBACK["au"].get(iso, 2))
        score = calc_wcri(ca, us, uk, au, c["regional"])

        cities.append({
            "city":     c["city"],
            "country":  c["country"],
            "iso":      iso,
            "ca":       ca,
            "us":       us,
            "uk":       uk,
            "au":       au,
            "score":    score,
            "band":     get_band(score),
            "regional": c["regional"],
            "notes":    NOTES.get(iso, ""),
        })

    output = {
        "generated":   now,
        "generated_ts": int(datetime.now(timezone.utc).timestamp()),
        "sources": {
            "ca": {"ok": ca_ok, "label": "Canada (travel.gc.ca)"},
            "us": {"ok": us_ok, "label": "USA (travel.state.gov)"},
            "uk": {"ok": uk_ok, "label": "UK FCDO (gov.uk)"},
            "au": {"ok": au_ok, "label": "Australia (smartraveller.gov.au)"},
        },
        "cities": cities,
    }

    # Write the JSON file
    out_path = Path(__file__).parent / "advisory_data.json"
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWritten: {out_path} ({out_path.stat().st_size:,} bytes)")

    # Summary
    bands = {}
    for c in cities:
        bands[c["band"]] = bands.get(c["band"], 0) + 1
    scores = [c["score"] for c in cities]
    print(f"\nSummary: {bands}")
    print(f"Avg WCRI: {sum(scores)/len(scores):.1f} | Max: {max(scores)} | Min: {min(scores)}")
    print(f"Sources: CA={'OK' if ca_ok else 'FALLBACK'} | US={'OK' if us_ok else 'FALLBACK'} | "
          f"UK={'OK' if uk_ok else 'FALLBACK'} | AU={'OK' if au_ok else 'FALLBACK'}")

if __name__ == "__main__":
    main()
