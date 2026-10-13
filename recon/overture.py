"""Businesses from Overture Maps Places (open data, CDLA Permissive 2.0).

Reads Overture's public parquet files straight from its open S3 bucket with
DuckDB, so nothing large is downloaded. Needs `pip install duckdb`.
"""

import re
import urllib.request

from . import places, text

BUCKET = "https://overturemaps-us-west-2.s3.amazonaws.com"


def latest_release():
    """Newest release folder name, such as '2026-09-17.0'."""
    url = f"{BUCKET}/?list-type=2&prefix=release/&delimiter=/"
    with urllib.request.urlopen(url, timeout=30) as response:
        listing = response.read().decode()
    releases = re.findall(r"<Prefix>release/([^/<]+)/</Prefix>", listing)
    if not releases:
        raise RuntimeError("Could not find any Overture release in the bucket listing")
    return sorted(releases)[-1]


def _connect():
    try:
        import duckdb
    except ImportError as error:
        raise SystemExit("This step needs DuckDB: pip install duckdb") from error
    db = duckdb.connect()
    for statement in ("INSTALL spatial", "LOAD spatial", "INSTALL httpfs", "LOAD httpfs",
                      "SET s3_region='us-west-2'"):
        db.execute(statement)
    return db


def _source(release):
    return f"s3://overturemaps-us-west-2/release/{release}/theme=places/type=place/*"


def _area(target):
    west, south, east, north = target.box
    return (f"bbox.xmin BETWEEN {west} AND {east} AND bbox.ymin BETWEEN {south} AND {north} "
            f"AND addresses[1].country = '{target.country}'")


def _sql_list(values):
    return "[" + ", ".join("'" + v.replace("'", "''") + "'" for v in values) + "]"


def categories(target, words, release=None):
    """Count places per category whose name contains any of the words.
    Use it to find Overture's exact category names for a new target list."""
    release = release or latest_release()
    likes = " OR ".join("categories.primary ILIKE '%" + w.replace("'", "''") + "%'"
                        for w in words)
    return _connect().execute(
        f"""SELECT categories.primary AS category, count(*) AS places
            FROM read_parquet('{_source(release)}', hive_partitioning=1)
            WHERE {_area(target)} AND ({likes})
            GROUP BY 1 ORDER BY 2 DESC"""
    ).fetchall()


def fetch(target, release=None, min_confidence=0.5):
    """Every place in the target's sectors and country."""
    release = release or latest_release()
    wanted = _sql_list(target.overture_categories())
    rows = _connect().execute(
        f"""SELECT id, names.primary, categories.primary, categories.alternate,
                   websites, phones, addresses[1].freeform, addresses[1].locality,
                   addresses[1].postcode, ST_Y(geometry), ST_X(geometry)
            FROM read_parquet('{_source(release)}', hive_partitioning=1)
            WHERE {_area(target)}
              AND confidence >= {float(min_confidence)}
              AND (list_contains({wanted}, categories.primary)
                   OR list_has_any({wanted}, categories.alternate))"""
    ).fetchall()

    found = []
    for (pid, name, primary, alternates, websites, phones, street, town, code,
         lat, lon) in rows:
        sector = target.overture_sector(primary, alternates)
        if not sector or not name:
            continue
        found.append(places.blank(
            name=name, sector=sector, category=primary, address=street, town=town,
            postcode=text.postcode(code or street, target.country),
            lat=round(lat, 6), lon=round(lon, 6),
            website=next((w for w in websites or [] if text.own_website(w)), ""),
            phone=(phones or [""])[0], source="overture", source_id=pid,
        ))
    return found, release
