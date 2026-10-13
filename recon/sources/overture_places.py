"""Overture Maps places in Great Britain and the US (CDLA-Permissive-2.0).

Every business and organisation on Overture's open map, with the emails,
phones, websites and social pages it lists. This is where most of the master
table's contacts come from: the registers rarely give emails. Each country is
copied once from Overture's public bucket into the cache as a small parquet
file, then read from there.

"can email" follows the name: in the UK a place whose name ends in Ltd, LLP
and so on may be emailed, and when the same business is found on Companies
House (same name and postcode, or the same website or email) the joined
organisation may be emailed too. Everyone else is post only. Personal webmail
addresses (Gmail, Hotmail and so on) are kept, and the reason column says so.
"""

import os
import types

from .. import contacts, overture, text
from . import corporate_name, record, rule

RELEASE = "2026-09-23.1"

# Rough boxes (west, south, east, north) so only the right map tiles are read.
BOXES = {"GB": (-8.7, 49.8, 1.8, 60.9), "US": (-179.9, 18.0, -66.0, 71.5)}


def _flat(values):
    return [v for v in values or [] if v]


def _extract(country, cache):
    """This country's places as a local parquet file, copied once."""
    path = os.path.join(cache, f"places-{RELEASE}-{country}.parquet")
    if os.path.exists(path):
        return path
    os.makedirs(cache, exist_ok=True)
    west, south, east, north = BOXES[country]
    db = overture._connect()
    columns = overture._columns(db, RELEASE)
    primary, _ = overture._category_columns(columns)
    emails = "emails" if "emails" in columns else "NULL::VARCHAR[]"
    socials = "socials" if "socials" in columns else "NULL::VARCHAR[]"
    still_open = ("AND coalesce(operating_status, '') <> 'permanently_closed'"
                  if "operating_status" in columns else "")
    db.execute(
        f"""COPY (SELECT id, names.primary AS name, {primary} AS category, websites, phones,
                         {emails} AS emails, {socials} AS socials,
                         addresses[1].freeform AS street, addresses[1].locality AS town,
                         addresses[1].region AS region, addresses[1].postcode AS postcode
                  FROM read_parquet('{overture._source(RELEASE)}', hive_partitioning=1)
                  WHERE bbox.xmin BETWEEN {west} AND {east} AND bbox.ymin BETWEEN {south} AND {north}
                    AND addresses[1].country = '{country}' AND confidence >= 0.5 {still_open}
                    AND names.primary IS NOT NULL)
            TO '{path}.part' (FORMAT parquet, COMPRESSION zstd)""")
    os.replace(path + ".part", path)
    return path


def _loader(country):
    source = {
        "name": f"overture-places-{country.lower()}",
        "title": f"Overture Maps places, {'Great Britain' if country == 'GB' else 'United States'}",
        "country": country,
        "url": "https://docs.overturemaps.org/guides/places/",
        "licence": "CDLA-Permissive-2.0 (Overture Maps Foundation)",
        "updated": "monthly",
        "fields": "name, category, address, website, emails, phones, social pages",
        "release": RELEASE,
    }

    def rows(cache):
        import duckdb
        path = _extract(country, cache)
        result = duckdb.connect().execute(f"SELECT * FROM read_parquet('{path}')")
        while batch := result.fetchmany(50_000):
            for place in batch:
                yield to_record(source, country, *place)

    return types.SimpleNamespace(SOURCE=source, rows=rows)


def to_record(source, country, pid, name, category, websites, phones, emails, socials,
              street, town, region, postcode):
    website = next((w for w in _flat(websites) if text.own_website(w)), "")
    listed = [e.strip().lower() for e in _flat(emails) if "@" in e]
    personal = [e for e in listed if contacts.email_label(e) == contacts.PERSONAL]
    corporate = corporate_name(name)
    if country == "GB":
        why = ("trading as a company" if corporate else
               "not shown to be a company: post only unless Companies House shows it is")
        can, why = rule("GB", corporate, why)
    else:
        can, why = rule("US", None, "US business: CAN-SPAM")
    if personal:
        why += "; personal webmail address listed"
    links = [contacts.social_link(s) for s in [*_flat(socials), *_flat(websites)]]
    return record(
        source, pid, name, kind=(category or "place").replace("_", " "), category=category,
        address=street, town=town, region=region,
        postcode=text.postcode(postcode or street or "", country) or postcode,
        country=country, website=website, emails=listed, phones=_flat(phones),
        socials=[link for link in links if link], can_email=can, rule_reason=why,
        source_url=f"https://explore.overturemaps.org/#id={pid}")


SOURCES = [_loader("GB"), _loader("US")]
