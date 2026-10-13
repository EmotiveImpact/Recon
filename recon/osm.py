"""Businesses from OpenStreetMap through the public Overpass API (ODbL).

OpenStreetMap data needs credit: "© OpenStreetMap contributors".
One query per tag keeps each request small enough for the shared public server.
"""

import json
import time
import urllib.parse
import urllib.request

from . import places, text

OVERPASS = "https://overpass-api.de/api/interpreter"
USER_AGENT = "recon/0.1 (in-house research)"


def _query(country, key, value):
    return f"""[out:json][timeout:600];
area["ISO3166-1"="{country}"][admin_level=2]->.country;
nwr["{key}"="{value}"](area.country);
out center tags;"""


def _post(query, retries=3):
    data = urllib.parse.urlencode({"data": query}).encode()
    for attempt in range(retries):
        try:
            request = urllib.request.Request(OVERPASS, data=data,
                                             headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=700) as response:
                return json.loads(response.read())
        except Exception:  # Overpass is busy at times; wait and try again.
            if attempt == retries - 1:
                raise
            time.sleep(30 * (attempt + 1))


def to_place(target, element):
    tags = element.get("tags", {})
    sector = target.osm_sector(tags)
    name = tags.get("name") or tags.get("brand")
    if not sector or not name:
        return None
    lat = element.get("lat") or element.get("center", {}).get("lat")
    lon = element.get("lon") or element.get("center", {}).get("lon")
    street = " ".join(filter(None, [tags.get("addr:housenumber"), tags.get("addr:street")]))
    website = tags.get("website") or tags.get("contact:website") or ""
    category = next((f"{k}={v}" for k, v in target.osm_tags() if tags.get(k) == v), "")
    email = (tags.get("email") or tags.get("contact:email") or "").split(";")[0].strip()
    return places.blank(
        name=name, sector=sector, category=category, address=street,
        town=tags.get("addr:city") or tags.get("addr:town") or "",
        postcode=text.postcode(tags.get("addr:postcode", ""), target.country),
        lat=round(lat, 6) if lat else "", lon=round(lon, 6) if lon else "",
        website=website if text.own_website(website) else "",
        phone=tags.get("phone") or tags.get("contact:phone") or "",
        source="osm", source_id=f"{element['type']}/{element['id']}",
        email=email, email_found_on="openstreetmap" if email else "",
        socials=" ".join(tags[k] for k in ("contact:instagram", "contact:facebook", "contact:tiktok")
                         if tags.get(k)),
    )


def fetch(target, pause=10):
    found = []
    pairs = target.osm_tags()
    for index, (key, value) in enumerate(pairs):
        print(f"  OpenStreetMap {key}={value} ({index + 1} of {len(pairs)})")
        result = _post(_query(target.country, key, value))
        found.extend(p for p in (to_place(target, e) for e in result.get("elements", [])) if p)
        time.sleep(pause)  # Be polite to the shared public server.
    return found
