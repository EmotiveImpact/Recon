"""Businesses from OpenStreetMap (ODbL).

OpenStreetMap data needs credit: "© OpenStreetMap contributors".

By default Recon downloads the country's daily OpenStreetMap extract (a
.osm.pbf file, about 2.6 GB for the UK), keeps it for a week, and reads the
businesses out of it with DuckDB. That takes a couple of minutes for the whole
UK, needs no shared server, and works where the Overpass API is blocked or
busy. `--osm-overpass` still uses the old route: one Overpass query per tag.
"""

import json
import os
import time
import urllib.parse
import urllib.request

from . import contacts, places, text

OVERPASS = "https://overpass-api.de/api/interpreter"
USER_AGENT = "recon/0.1 (in-house research)"

# Each country's extract, from the first mirror that answers. A mirror can
# split a country into parts; all parts are downloaded and read.
EXTRACTS = {
    "GB": [["https://download.geofabrik.de/europe/united-kingdom-latest.osm.pbf"],
           ["https://download.openstreetmap.fr/extracts/europe/united_kingdom-latest.osm.pbf"]],
    "IE": [["https://download.geofabrik.de/europe/ireland-and-northern-ireland-latest.osm.pbf"],
           ["https://download.openstreetmap.fr/extracts/europe/ireland-latest.osm.pbf"]],
    "US": [["https://download.geofabrik.de/north-america/us-latest.osm.pbf"],
           [f"https://download.openstreetmap.fr/extracts/north-america/us-{part}-latest.osm.pbf"
            for part in ("midwest", "northeast", "south", "west")]],
}
KEEP_DAYS = 7  # Reuse a downloaded extract for this long before fetching a fresh one.


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
    listed = [e.strip().lower() for key in ("email", "contact:email")
              for e in tags.get(key, "").split(";") if "@" in e]
    email = listed[0] if listed else ""
    place = places.blank(
        name=name, sector=sector, category=category, address=street,
        town=tags.get("addr:city") or tags.get("addr:town") or "",
        postcode=text.postcode(tags.get("addr:postcode", ""), target.country),
        lat=round(lat, 6) if lat else "", lon=round(lon, 6) if lon else "",
        website=website if text.own_website(website) else "",
        source="osm", source_id=f"{element['type']}/{element['id']}",
        email=email, email_found_on="openstreetmap" if email else "",
    )
    contacts.add_emails(place, listed, text.domain(place["website"]))
    contacts.add_phones(place, [n for key in ("phone", "contact:phone", "mobile", "contact:mobile")
                                for n in tags.get(key, "").split(";")], target.country)
    contacts.add_socials(place, [_social(k, v) for k, v in tags.items()] + [website])
    return place


_SOCIAL_BASES = {"instagram": "https://www.instagram.com/", "facebook": "https://www.facebook.com/",
                 "tiktok": "https://www.tiktok.com/@", "twitter": "https://x.com/",
                 "youtube": "https://www.youtube.com/@", "linkedin": "https://www.linkedin.com/company/"}


def _social(key, value):
    """A social tag as a link; OpenStreetMap often holds just the handle."""
    kind = key.replace("contact:", "")
    if kind not in _SOCIAL_BASES or not value:
        return ""
    if "/" in value or "." in value:
        return value
    return _SOCIAL_BASES[kind] + value.lstrip("@")


def fetch_overpass(target, pause=10):
    found = []
    pairs = target.osm_tags()
    for index, (key, value) in enumerate(pairs):
        print(f"  OpenStreetMap {key}={value} ({index + 1} of {len(pairs)})")
        result = _post(_query(target.country, key, value))
        found.extend(p for p in (to_place(target, e) for e in result.get("elements", [])) if p)
        time.sleep(pause)  # Be polite to the shared public server.
    return found


def _fresh(path, days=KEEP_DAYS):
    return os.path.exists(path) and time.time() - os.path.getmtime(path) < days * 86400


def _download(url, path):
    """Fetch url to path, via a .part file so a broken download is never used."""
    temp = path + ".part"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response, open(temp, "wb") as out:
        size = int(response.headers.get("Content-Length") or 0)
        done, shown = 0, 0
        while chunk := response.read(1 << 20):
            out.write(chunk)
            done += len(chunk)
            if done - shown >= 250 << 20:  # A line every 250 MB.
                shown = done
                print(f"    {done >> 20:,} MB" + (f" of {size >> 20:,} MB" if size else ""))
    if size and os.path.getsize(temp) != size:
        os.remove(temp)
        raise OSError(f"{url} stopped early")
    os.replace(temp, path)


def extract_files(country, folder):
    """Paths of the country's OpenStreetMap extract, downloading it when missing
    or more than a week old. Tries each mirror in turn."""
    sources = EXTRACTS.get(country)
    if not sources:
        raise SystemExit(f"No OpenStreetMap extract known for {country}; pass --osm-extract "
                         "with a .osm.pbf file, or add the country to EXTRACTS in recon/osm.py")
    os.makedirs(folder, exist_ok=True)
    for urls in sources:
        paths = [os.path.join(folder, os.path.basename(u)) for u in urls]
        if all(_fresh(p) for p in paths):
            return paths
    problems = []
    for urls in sources:
        paths = [os.path.join(folder, os.path.basename(u)) for u in urls]
        try:
            for url, path in zip(urls, paths):
                if not _fresh(path):
                    print(f"  Downloading {url}")
                    _download(url, path)
            return paths
        except OSError as error:
            problems.append(f"{urls[0]}: {error}")
    raise SystemExit("Could not download the OpenStreetMap extract:\n  " + "\n  ".join(problems))


def _connect():
    try:
        import duckdb
    except ImportError as error:
        raise SystemExit("Reading OpenStreetMap needs DuckDB: pip install duckdb") from error
    db = duckdb.connect()
    # A modest, fixed memory cap: DuckDB otherwise takes most of the
    # computer's memory, and two runs at once can be killed for it.
    db.execute("SET memory_limit = '2GB'")
    db.execute("SET preserve_insertion_order = false")
    db.execute("INSTALL spatial")
    db.execute("LOAD spatial")
    return db


def _quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def read_extract(target, path, db=None):
    """Every node and way in a .osm.pbf file carrying one of the target's tags,
    inside the target's box, as Overpass-style elements. A way (a building
    drawn as an outline) is placed at the average of its corner points."""
    db = db or _connect()
    source = f"ST_ReadOSM({_quote(path)})"
    wanted = " OR ".join(f"list_contains(map_extract(tags, {_quote(k)}), {_quote(v)})"
                         for k, v in target.osm_tags())
    if not wanted:
        return []
    db.execute("DROP TABLE IF EXISTS hits")
    db.execute(f"""CREATE TEMP TABLE hits AS
        SELECT kind, id, tags, refs, lat, lon FROM {source}
        WHERE kind IN ('node', 'way') AND tags IS NOT NULL AND ({wanted})""")
    # A second pass picks up only the corner points of the ways found.
    db.execute("DROP TABLE IF EXISTS corners")
    db.execute(f"""CREATE TEMP TABLE corners AS
        SELECT n.id, n.lat, n.lon FROM {source} n
        SEMI JOIN (SELECT DISTINCT unnest(refs) AS id FROM hits WHERE kind = 'way') r USING (id)
        WHERE n.kind = 'node'""")
    west, south, east, north = target.box
    rows = db.execute(f"""
        WITH centres AS (
            SELECT w.way, avg(c.lat) AS lat, avg(c.lon) AS lon
            FROM (SELECT id AS way, unnest(refs) AS ref FROM hits WHERE kind = 'way') w
            JOIN corners c ON c.id = w.ref GROUP BY w.way)
        SELECT h.kind, h.id, h.tags, coalesce(h.lat, centres.lat) AS lat,
               coalesce(h.lon, centres.lon) AS lon
        FROM hits h LEFT JOIN centres ON h.kind = 'way' AND centres.way = h.id
        WHERE coalesce(h.lat, centres.lat) BETWEEN {south} AND {north}
          AND coalesce(h.lon, centres.lon) BETWEEN {west} AND {east}""").fetchall()
    return [{"type": str(kind), "id": osm_id, "tags": dict(tags or {}), "lat": lat, "lon": lon}
            for kind, osm_id, tags, lat, lon in rows]


def fetch(target, extract=None, folder=os.path.join("data", "osm"), overpass=False):
    """Every place in the target's tags and box. `extract` is a .osm.pbf file
    (or several) to read instead of downloading the country's."""
    if overpass:
        return fetch_overpass(target)
    paths = extract or extract_files(target.country, folder)
    if isinstance(paths, str):
        paths = [paths]
    db = _connect()
    found = []
    for path in paths:
        print(f"  Reading {os.path.basename(path)}")
        found.extend(p for p in (to_place(target, e) for e in read_extract(target, path, db)) if p)
    return found
