"""Businesses from Overture Maps Places (open data, CDLA Permissive 2.0).

Reads Overture's public parquet files straight from its open S3 bucket with
DuckDB, so nothing large is downloaded. Needs `pip install duckdb`.
"""

import re
import urllib.request

from . import contacts, places, text
from .emails import best_email

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
                      "SET s3_region='us-west-2'", "SET enable_progress_bar=false",
                      # The bucket is public. An empty key stops any AWS keys on the
                      # computer being sent, which the bucket would refuse.
                      "CREATE SECRET overture (TYPE s3, KEY_ID '', SECRET '', "
                      "REGION 'us-west-2', SCOPE 's3://overturemaps-us-west-2')"):
        db.execute(statement)
    return db


def _source(release):
    return f"s3://overturemaps-us-west-2/release/{release}/theme=places/type=place/*"


def _columns(db, release):
    """Column names in this release. Overture renames things now and then."""
    return {row[0] for row in db.execute(
        f"DESCRIBE SELECT * FROM read_parquet('{_source(release)}', hive_partitioning=1)"
    ).fetchall()}


def _category_columns(columns):
    """(primary, alternates) expressions. From release 2026-09-23.1 the
    'categories' column became 'taxonomy', with 'alternate' renamed 'alternates'."""
    if "taxonomy" in columns:
        return "taxonomy.primary", "taxonomy.alternates"
    return "categories.primary", "categories.alternate"


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
    db = _connect()
    primary, _ = _category_columns(_columns(db, release))
    likes = " OR ".join(f"{primary} ILIKE '%" + w.replace("'", "''") + "%'" for w in words)
    return db.execute(
        f"""SELECT {primary} AS category, count(*) AS places
            FROM read_parquet('{_source(release)}', hive_partitioning=1)
            WHERE {_area(target)} AND ({likes})
            GROUP BY 1 ORDER BY 2 DESC"""
    ).fetchall()


def fetch(target, release=None, min_confidence=0.5):
    """Every place in the target's sectors and country."""
    release = release or latest_release()
    wanted = _sql_list(target.overture_categories())
    db = _connect()
    columns = _columns(db, release)
    primary, alternates = _category_columns(columns)
    emails = "emails" if "emails" in columns else "NULL"
    socials = "socials" if "socials" in columns else "NULL"
    still_open = ("AND coalesce(operating_status, '') <> 'permanently_closed'"
                  if "operating_status" in columns else "")
    rows = db.execute(
        f"""SELECT id, names.primary, {primary}, {alternates},
                   websites, phones, {emails}, {socials},
                   addresses[1].freeform, addresses[1].locality,
                   addresses[1].postcode, ST_Y(geometry), ST_X(geometry)
            FROM read_parquet('{_source(release)}', hive_partitioning=1)
            WHERE {_area(target)}
              AND confidence >= {float(min_confidence)} {still_open}
              AND (list_contains({wanted}, {primary})
                   OR list_has_any({wanted}, {alternates}))"""
    ).fetchall()
    return [p for p in (to_place(target, row) for row in rows) if p], release


def unused_categories(target, found):
    """The target's categories that no place found has as its main category.
    Overture renames categories between releases, and a renamed one silently
    matches nothing (the September 2026 release renamed "spas" to "spa")."""
    return sorted(set(target.overture_categories()) - {p["category"] for p in found})


def to_place(target, row):
    """One Overture row (in the order fetch() selects) as a place, or None."""
    (pid, name, primary, alternates, websites, phones, emails, socials, street, town, code,
     lat, lon) = row
    sector = target.overture_sector(primary, alternates)
    if not sector or not name:
        return None
    website = next((w for w in websites or [] if text.own_website(w)), "")
    listed = [e.strip().lower() for e in emails or [] if "@" in (e or "")]
    email = best_email(listed, text.domain(website))
    place = places.blank(
        name=name, sector=sector, category=primary, address=street, town=town,
        postcode=text.postcode(code or street, target.country),
        lat=round(lat, 6), lon=round(lon, 6), website=website,
        source="overture", source_id=pid,
        email=email, email_found_on="overture" if email else "",
    )
    contacts.add_emails(place, listed, text.domain(website))
    contacts.add_phones(place, [p for p in phones or [] if p], target.country)
    contacts.add_socials(place, [*(socials or []), *(websites or [])])
    return place
