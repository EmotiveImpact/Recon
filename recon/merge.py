"""Combine places from several sources so each business appears once.

Two records are the same business when they sit within about 120 metres of
each other and either their names are alike or they share a website or phone
number. Records without a position fall back to the same name and postcode.
"""

import difflib
import hashlib
import math
import re

from . import text

# Columns holding several values: every source's values are kept.
LISTS = {"all_emails": "; ", "all_phones": "; ", "socials": " "}

# Prefer Overture's record; OpenStreetMap fills its gaps.
SOURCE_ORDER = {"overture": 0, "osm": 1, "companies_house": 2}

NEARBY_METRES = 120  # Map sources place the same shop up to a few dozen metres apart.

# Words that say what a business does rather than which business it is. Two
# salons called "Luxe Nails" and "Luxe Hair" next door are different
# businesses, so each word also names its trade.
TRADE_WORDS = {
    "hair": "hair", "hairs": "hair", "hairdresser": "hair", "hairdressers": "hair",
    "hairdressing": "hair", "hairstylist": "hair", "hairstylists": "hair", "stylist": "hair",
    "stylists": "hair", "barber": "hair", "barbers": "hair", "barbershop": "hair",
    "barbering": "hair", "blowdry": "hair", "cutting": "hair", "cuts": "hair", "cut": "hair",
    "salon": "", "salons": "",
    "nail": "nails", "nails": "nails", "manicure": "nails", "pedicure": "nails",
    "beauty": "beauty", "beautician": "beauty", "aesthetics": "beauty", "aesthetic": "beauty",
    "skin": "beauty", "skincare": "beauty", "lash": "beauty", "lashes": "beauty",
    "brow": "beauty", "brows": "beauty", "wax": "beauty", "waxing": "beauty",
    "tan": "beauty", "tanning": "beauty", "laser": "beauty", "cosmetic": "beauty",
    "spa": "spa", "massage": "spa", "therapy": "spa", "therapies": "spa", "wellness": "spa",
    "wellbeing": "spa", "holistic": "spa", "sauna": "spa", "reflexology": "spa",
    "tattoo": "tattoo", "tattoos": "tattoo", "tattooing": "tattoo", "piercing": "tattoo",
    "piercings": "tattoo", "ink": "tattoo",
    "physio": "health", "physiotherapy": "health", "physiotherapist": "health",
    "chiropractic": "health", "chiropractor": "health", "osteopath": "health",
    "osteopathy": "health", "osteopaths": "health", "clinic": "health", "health": "health",
    "dog": "pets", "dogs": "pets", "pet": "pets", "pets": "pets", "grooming": "pets",
    "groomer": "pets", "groomers": "pets",
    "studio": "", "studios": "", "parlour": "", "lounge": "", "bar": "", "boutique": "",
    "shop": "", "room": "", "rooms": "", "house": "", "lab": "", "collective": "",
    "centre": "", "center": "", "care": "", "by": "", "of": "", "at": "", "and": "",
}


def _words(name, town=""):
    """A name's words, without company words or the town's name."""
    drop = set(text.name_key(town).split())
    return [w for w in text.name_key(name).split() if w not in drop]


def _trades(words):
    return {TRADE_WORDS[w] for w in words if TRADE_WORDS.get(w)}


def _squash(words):
    return "".join(words)


def alike(a, b, town_a="", town_b="", streets=""):
    """Whether two names could be the same business, once we already know the
    records are close together. Forgives word order, spacing ("Hair Studio",
    "Hairstudio"), plurals and a name being a shorter form of the other
    ("Taper Barbers", "Taper Barber Brighton"). Town and street words
    ("Southwick Barbers" on Southwick Square) do not count as the name."""
    full_a = _words(a, f"{town_a} {town_b}")
    full_b = _words(b, f"{town_a} {town_b}")
    where = set(text.name_key(streets).split())
    if not full_a or not full_b:
        return False
    trades_a, trades_b = _trades(full_a), _trades(full_b)
    if trades_a and trades_b and not trades_a & trades_b:
        return False  # "Luxe Nails" is not "Luxe Hair".
    core_a = [w for w in full_a if w not in TRADE_WORDS and w not in where]
    core_b = [w for w in full_b if w not in TRADE_WORDS and w not in where]
    whole_a, whole_b = _squash(full_a).rstrip("s"), _squash(full_b).rstrip("s")
    if whole_a == whole_b:
        return True  # "City Barbers", "CityBarbers"; "Beauty Rooms", "Beauty Room".
    # One name written inside the other ("The Riah Hair Studio" in "The
    # Riahhair Studio / Duke's Beauty"), when the shorter one is more than
    # trade words and long enough not to turn up by chance.
    shorter, longer, shorter_core = ((whole_a, whole_b, core_a) if len(whole_a) <= len(whole_b)
                                     else (whole_b, whole_a, core_b))
    if shorter_core and len(shorter) >= 8 and shorter in longer:
        return True
    numbers = lambda words: {w for w in words if w.isdigit()}
    if numbers(core_a) and numbers(core_b) and numbers(core_a) != numbers(core_b):
        return False  # "Studio 7" is never "Studio 8".
    if not core_a or not core_b:
        return False  # Only trade words, like "House of Hair", and not the same.
    if set(core_a) <= set(core_b) or set(core_b) <= set(core_a):
        return True
    squashed_a, squashed_b = _squash(core_a), _squash(core_b)
    if squashed_a.rstrip("s") == squashed_b.rstrip("s"):
        return True  # "Med's", "Meds"; "Max Oliver", "MaxOliver".
    return difflib.SequenceMatcher(None, squashed_a, squashed_b).ratio() >= 0.85


def _phones(place):
    return {re.sub(r"\D", "", p.split(" (")[0])[-10:]
            for p in [place["phone"]] + place["all_phones"].split("; ") if p.strip()} - {""}


def _metres(a, b):
    lat_a, lon_a, lat_b, lon_b = map(math.radians, (a[0], a[1], b[0], b[1]))
    x = (lon_b - lon_a) * math.cos((lat_a + lat_b) / 2)
    return 6_371_000 * math.hypot(x, lat_b - lat_a)


def _position(place):
    try:
        return float(place["lat"]), float(place["lon"])
    except (TypeError, ValueError):
        return None


def _site(url):
    """A website as domain plus page, so shops that each have a page on one
    shopping centre's site are not taken for one business."""
    if not url:
        return ""
    page = re.sub(r"^[a-z]+://", "", url.strip().lower()).split("?")[0].split("#")[0]
    page = page.split("/", 1)[1].strip("/") if "/" in page else ""
    return f"{text.domain(url)}/{page}"


def same_business(a, b):
    """Two nearby records are one business if their names are alike, or they
    give the same website or phone number, unless their names say they are in
    different trades."""
    trades_a = _trades(_words(a["name"]))
    trades_b = _trades(_words(b["name"]))
    if trades_a and trades_b and not trades_a & trades_b:
        return False
    streets = " ".join(re.sub(r"\d", " ", p["address"]) for p in (a, b))
    if alike(a["name"], b["name"], a["town"], b["town"], streets):
        return True
    site_a, site_b = _site(a["website"]), _site(b["website"])
    if site_a and site_a == site_b:
        return True
    return bool(_phones(a) & _phones(b))


def match_key(place):
    """For records without a position: same name and postcode, or same website."""
    name = text.name_key(place["name"])
    if not name:
        return ""
    if place["postcode"]:
        return f"{name}|{place['postcode']}"
    return f"{name}|{text.domain(place['website'])}" if place["website"] else ""


def _short_hash(value):
    return hashlib.sha1(value.encode()).hexdigest()[:12]


def _groups(everything):
    """Indexes of records that are one business, joined transitively."""
    parent = list(range(len(everything)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def join(i, j):
        i, j = root(i), root(j)
        if i != j:
            parent[max(i, j)] = min(i, j)  # The earlier, preferred record leads.

    # Records in a grid of cells about NEARBY_METRES wide; each record is only
    # compared with records in its own and the eight neighbouring cells.
    cell_size = NEARBY_METRES / 111_000
    cells = {}
    for i, place in enumerate(everything):
        where = _position(place)
        if not where:
            continue
        lat, lon = where
        squeeze = max(math.cos(math.radians(lat)), 0.1)
        cell = (int(lat // cell_size), int(lon * squeeze // cell_size))
        for d_lat in (-1, 0, 1):
            for d_lon in (-1, 0, 1):
                for j in cells.get((cell[0] + d_lat, cell[1] + d_lon), []):
                    if (_metres(where, _position(everything[j])) <= NEARBY_METRES
                            and same_business(place, everything[j])):
                        join(i, j)
        cells.setdefault(cell, []).append(i)

    keys = {}
    for i, place in enumerate(everything):
        key = match_key(place)
        if key:
            if key in keys:
                join(i, keys[key])
            else:
                keys[key] = i

    groups = {}
    for i in range(len(everything)):
        groups.setdefault(root(i), []).append(i)
    return [members for _, members in sorted(groups.items())]


def _absorb(kept, place):
    for field, value in place.items():
        if field in ("key", "source", "source_id"):
            continue
        if value and not kept.get(field):
            kept[field] = value
        elif value and field in LISTS:
            sep = LISTS[field]
            items = [v for v in kept[field].split(sep) if v]
            items += [v for v in value.split(sep) if v and v not in items]
            kept[field] = sep.join(items)
    for source in place["source"].split("+"):
        if source not in kept["source"].split("+"):
            kept["source"] += "+" + source


def _phone_flags(place):
    """Keep mobile_only true to the joined list of numbers."""
    kinds = [p.rsplit("(", 1)[-1].rstrip(")") for p in place["all_phones"].split("; ") if p]
    if kinds:
        place["mobile_only"] = "yes" if all(k == "mobile" for k in kinds) else ""


def combine(*groups):
    everything = sorted((p for group in groups for p in group),
                        key=lambda p: SOURCE_ORDER.get(p["source"], 9))
    combined = []
    for members in _groups(everything):
        kept = everything[members[0]]
        for i in members[1:]:
            _absorb(kept, everything[i])
        if len(members) > 1:
            _phone_flags(kept)
        kept["key"] = _short_hash(match_key(kept) or kept["source"] + kept["source_id"])
        combined.append(kept)
    return combined
