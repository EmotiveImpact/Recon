"""Combine places from several sources so each business appears once."""

import hashlib

from . import text

# Columns holding several values: every source's values are kept.
LISTS = {"all_emails": "; ", "all_phones": "; ", "socials": " "}

# Prefer Overture's record; OpenStreetMap fills its gaps.
SOURCE_ORDER = {"overture": 0, "osm": 1, "companies_house": 2}


def match_key(place):
    """Same name and postcode, or same name within about 100 metres."""
    name = text.name_key(place["name"])
    if not name:
        return ""
    if place["postcode"]:
        return f"{name}|{place['postcode']}"
    if place["lat"] and place["lon"]:
        return f"{name}|{float(place['lat']):.3f},{float(place['lon']):.3f}"
    return f"{name}|{text.domain(place['website'])}" if place["website"] else ""


def _short_hash(value):
    return hashlib.sha1(value.encode()).hexdigest()[:12]


def combine(*groups):
    merged = {}
    loose = []
    everything = sorted((p for group in groups for p in group),
                        key=lambda p: SOURCE_ORDER.get(p["source"], 9))
    for place in everything:
        key = match_key(place)
        if not key:
            place["key"] = _short_hash(place["source"] + place["source_id"])
            loose.append(place)
            continue
        if key not in merged:
            place["key"] = _short_hash(key)
            merged[key] = place
            continue
        kept = merged[key]
        for field, value in place.items():
            if value and not kept.get(field):
                kept[field] = value
            elif value and field in LISTS:
                sep = LISTS[field]
                items = kept[field].split(sep) + [v for v in value.split(sep)
                                                  if v not in kept[field].split(sep)]
                kept[field] = sep.join(items)
        if place["source"] not in kept["source"].split("+"):
            kept["source"] += "+" + place["source"]
    return list(merged.values()) + loose
