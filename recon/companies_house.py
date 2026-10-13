"""Mark which UK places are companies, using Companies House's free monthly file.

Download "BasicCompanyDataAsOneFile" (or its parts) from
https://download.companieshouse.gov.uk/en_output.html and pass the zip or CSV.
The file has no emails or websites: it only tells us who is a company, which
decides whether UK law lets us email them without asking first.
"""

import collections
import csv
import io
import math
import re
import zipfile

from . import text, words
from .words import Vocabulary

# Under PECR, companies and LLPs are "corporate subscribers" and can be emailed
# about business products with an opt-out. Sole traders and ordinary
# partnerships cannot without consent, and they are not on the register at all.
NOT_CORPORATE = ("limited partnership",)


def is_corporate(category):
    category = (category or "").lower()
    if "limited liability partnership" in category:
        return True
    return bool(category) and not any(word in category for word in NOT_CORPORATE)


def _rows(path):
    """Yield rows from a CSV, or from every CSV inside a zip."""
    if path.lower().endswith(".zip"):
        with zipfile.ZipFile(path) as archive:
            for member in archive.namelist():
                if member.lower().endswith(".csv"):
                    with archive.open(member) as raw:
                        yield from _read(io.TextIOWrapper(raw, encoding="utf-8", errors="replace"))
    else:
        with open(path, newline="", encoding="utf-8", errors="replace") as handle:
            yield from _read(handle)


def _read(handle):
    reader = csv.reader(handle)
    header = [h.strip() for h in next(reader)]  # Some headers start with a space.
    for row in reader:
        yield dict(zip(header, row))


def load(paths, sic_codes, named=()):
    """Active companies whose trade codes are in sic_codes, indexed by name.
    Companies whose name key is in `named` (operators a register names) are
    kept whatever their trade codes."""
    index = {}
    total = 0
    named = set(named)
    for path in paths:
        for row in _rows(path):
            if row.get("CompanyStatus", "").strip().lower() != "active":
                continue
            codes = [row.get(f"SICCode.SicText_{n}", "")[:5] for n in range(1, 5)]
            sector = next((sic_codes[c] for c in codes if c in sic_codes), None)
            if not sector and text.name_key(row.get("CompanyName", "")) in named:
                sector = "named by a register"
            if not sector:
                continue
            company = {
                "number": row.get("CompanyNumber", "").strip(),
                "name": row.get("CompanyName", "").strip(),
                "category": row.get("CompanyCategory", "").strip(),
                "postcode": text.postcode(row.get("RegAddress.PostCode", "")),
                "town": row.get("RegAddress.PostTown", "").strip().lower(),
                "street": row.get("RegAddress.AddressLine1", "").strip().lower(),
                "sector": sector,
            }
            index.setdefault(text.name_key(company["name"]), []).append(company)
            total += 1
    return index, total


# Matching a place to its company, after the ideas in Splink and
# uk_address_matcher (both MIT), written fresh with the standard library.
#
# A wrong match is worse than a missed one: it marks a sole trader "can
# email". So a match needs evidence on two fronts:
#
# - The names. Words are weighted by how rarely they appear in company names
#   in these trades (Splink's term-frequency idea): "hair" or "Brighton"
#   appear in thousands and prove little; "Lazarus" proves a lot. Trade
#   words (recon/words.py) and the street, area and town words around the
#   business never count as rare.
# - The distance to the registered office. The closer it is, the less alike
#   the names need to be. A company registered with an accountant in the next
#   town needs the very same name, one hardly any other company has. Beyond
#   that there is no match: a sole trader elsewhere may share the name.
#
# Then, when one company would take several places, the strongest match keeps
# it and the rest stay "post only".
SPOT, NEAR, AREA, FAR = 3, 2, 1, 0  # How close the registered office is.
NEAR_KM = 5           # Registered this close counts as near.
AREA_KM = 40          # ...and this close as the same area (the next town).
SAME_SPOT = 0.55      # Name likeness needed at the same postcode or street.
SAME_AREA = 0.8       # ...when near.
CLEAR_LEAD = 0.1      # The best company must beat the next best by this much.
VERY_RARE = 2         # Company names a word, or a whole name, may appear in and still be rare.


def _street(address):
    """The street words of an address. Map sources often start the address with
    the business's own name ("Sunshine Beauty, 166 Old Shoreham Rd"), so only
    the part with a house number counts."""
    parts = [p for p in (address or "").split(",") if p.strip()]
    numbered = [p for p in parts if re.search(r"\d", p)]
    street = " ".join(numbered or parts[-1:])
    return set(words.tokens(re.sub(r"\d+[a-z]?\b", " ", street.lower())))


class Rarity:
    """How rare each word, and each whole name, is among company names, so
    shared common words count for little."""

    def __init__(self, names, vocab):
        self.vocab = vocab
        self.counts = collections.Counter()
        self.holders = collections.defaultdict(set)  # word -> names using it
        self.total = 0
        for n, name in enumerate(names):
            found = set(words.tokens(name))
            self.counts.update(found)
            for word in found:
                self.holders[word].add(n)
            self.total += 1
        # A word in no more than one name in a thousand (and at least a
        # handful) says which business this is.
        self.rare_limit = max(3, self.total // 1000)

    def weight(self, word, local=()):
        if word in local or self.vocab.is_trade(word) or word.isdigit():
            return 0.5
        return math.log((self.total + 1) / (self.counts[word] + 0.5)) + 1

    def distinctive(self, word, local=()):
        return (word not in local and not self.vocab.is_trade(word) and not word.isdigit()
                and len(word) > 1 and self.counts[word] <= self.rare_limit)

    def names_with(self, found):
        """How many company names contain all these words ("Nick Brain
        Hairdressing": each word is common, the three together are not)."""
        sets = sorted((self.holders.get(w, set()) for w in set(found)), key=len)
        if not sets:
            return self.total
        return len(set.intersection(*sets))


def _joined(found, other):
    """Join neighbouring words that the other name writes as one ("Tip Top",
    "TIPTOP")."""
    out, i = [], 0
    while i < len(found):
        if i + 1 < len(found) and found[i] + found[i + 1] in other:
            out.append(found[i] + found[i + 1])
            i += 2
        else:
            out.append(found[i])
            i += 1
    return out


def likeness(place_name, company_name, rarity, local=()):
    """(0 to 1, shared rare words): weighted overlap of the two names. Words in
    `local` (the town, the street, the area) count for little and are never
    rare."""
    a, b = words.tokens(place_name), words.tokens(company_name)
    if not a or not b:
        return 0.0, []
    a, b = _joined(a, set(b)), _joined(b, set(a))
    numbers_a = {w for w in a if w.isdigit()}
    numbers_b = {w for w in b if w.isdigit()}
    if numbers_a and numbers_b and numbers_a != numbers_b:
        return 0.0, []  # "Studio 7" is never "Studio 8".
    shared, either = set(a) & set(b), set(a) | set(b)
    score = (sum(rarity.weight(w, local) for w in shared)
             / sum(rarity.weight(w, local) for w in either))
    return score, sorted(w for w in shared if rarity.distinctive(w, local))


def _same_street(place, company):
    found = lambda s: {w for w in re.findall(r"[a-z]+", (s or "").lower()) if len(w) > 2}
    street = found(place["address"]) - {"road", "street", "lane", "avenue", "the"}
    return bool(street) and len(street & found(company.get("street", ""))) >= 1 and \
        len(found(place["address"]) & found(company.get("street", ""))) >= 2


def _metres(a, b):
    lat_a, lon_a, lat_b, lon_b = map(math.radians, (a[0], a[1], b[0], b[1]))
    x = (lon_b - lon_a) * math.cos((lat_a + lat_b) / 2)
    return 6_371_000 * math.hypot(x, lat_b - lat_a)


def _position(place):
    try:
        return float(place["lat"]), float(place["lon"])
    except (KeyError, TypeError, ValueError):
        return None


def district_middles(places, fewest=3):
    """The middle of each postcode district, from the places found. Used when
    the postcode file is not to hand."""
    sums = collections.defaultdict(lambda: [0.0, 0.0, 0])
    for place in places:
        where = _position(place)
        district = text.postcode_district(place.get("postcode", ""))
        if where and district:
            total = sums[district]
            total[0] += where[0]
            total[1] += where[1]
            total[2] += 1
    return {d: (lat / n, lon / n) for d, (lat, lon, n) in sums.items() if n >= fewest}


def district_words(places):
    """The street, area and town words used in each postcode district's
    addresses. A name sharing only one of these with a company ("Marina
    Tanning", MARINA SERVICES near Brighton Marina) is no evidence."""
    found = collections.defaultdict(set)
    for place in places:
        district = text.postcode_district(place.get("postcode", ""))
        if district:
            own = set(words.tokens(place["name"]))
            found[district] |= (_street(place.get("address", "")) - own)
            found[district] |= set(words.tokens(place.get("town", "")))
    return found


class _Map:
    """Positions of postcodes: the postcode file's when given, else the middle
    of the district from the places found."""

    def __init__(self, places, postcodes=None):
        self.postcodes = postcodes
        self.middles = district_middles(places)

    def find(self, postcode):
        if self.postcodes:
            found = self.postcodes.find(postcode)
            if found:
                return found
        return self.middles.get(text.postcode_district(postcode))


def _where(place, company, where_is):
    """(closeness, words): how close the registered office is to the business."""
    if place["postcode"] and place["postcode"] == company["postcode"]:
        return SPOT, "same postcode"
    if _same_street(place, company):
        return SPOT, "same street"
    district = text.postcode_district(place["postcode"])
    if district and district == text.postcode_district(company["postcode"]):
        return NEAR, "same postcode district"
    here = _position(place) or where_is.find(place["postcode"])
    there = where_is.find(company["postcode"])
    if here and there:
        km = _metres(here, there) / 1000
        if km <= NEAR_KM:
            return NEAR, f"registered {km:.0f} km away"
        if km <= AREA_KM:
            return AREA, f"registered {km:.0f} km away"
        return FAR, f"registered {km:.0f} km away"
    if place["town"] and place["town"].strip().lower() == company["town"]:
        return NEAR, "same town"
    return FAR, "registered elsewhere"


def _judge(place, company, rarity, where_is, nearby=()):
    """(score, reason, closeness) when the evidence is enough, else None.
    `nearby` holds the street and area words of the place's district."""
    vocab = rarity.vocab
    towns = set(words.tokens(f"{place.get('town', '')} {company.get('town', '')}"))
    local = towns | _street(place.get("address", "")) | set(nearby)
    mine, theirs = words.tokens(place["name"]), words.tokens(company["name"])
    if vocab.different_trades(mine, theirs):
        return None  # "Luxe Nails" is not LUXE HAIR LTD.
    score, rare = likeness(place["name"], company["name"], rarity, local)
    closeness, where = _where(place, company, where_is)
    named = [w for w in mine if w not in towns]
    same_name = bool(named) and named == [w for w in theirs if w not in towns]
    how = f"same name, {where}" if same_name else f"close name ({score:.2f}), {where}"
    if closeness == SPOT:
        # At the company's own address: the same name, or the same name apart
        # from trade words ("Creative Nails Spa", CREATIVE NAILS), or a close
        # name sharing a rare word.
        core = lambda found: {w for w in found if w not in towns and not vocab.is_trade(w)}
        if same_name or (core(theirs) and core(mine) == core(theirs)):
            return SPOT + 1.0, how, closeness
        if rare and score >= SAME_SPOT:
            return SPOT + score, how, closeness
        return None
    # The same name, and hardly any other company has it ("Nick Brain
    # Hairdressing", "The Brow Place"): believable nearby or in the next town.
    rare_name = (same_name and any(w not in local for w in named)
                 and rarity.names_with(named) <= VERY_RARE)
    if closeness == NEAR:
        very_rare = [w for w in rare if rarity.counts[w] <= VERY_RARE]
        if rare_name or (rare and (score >= SAME_AREA or (very_rare and score >= SAME_SPOT))):
            return NEAR + score, how, closeness
    if closeness == AREA and rare_name:
        return AREA + score, how, closeness
    return None


def _keys(found):
    """A name's words, and each pair of neighbouring words written as one, so
    "Tip Top" finds TIPTOP and "Beautyworks" finds BEAUTY WORKS."""
    return set(found) | {a + b for a, b in zip(found, found[1:])}


class _Finder:
    """The companies worth judging for a place: the same name anywhere, or a
    shared word within the place's postcode district. Comparing every place
    with every company in its district would take hours for the whole UK."""

    def __init__(self, index):
        self.by_name = index
        self.by_word = collections.defaultdict(lambda: collections.defaultdict(list))
        for companies in index.values():
            for company in companies:
                district = text.postcode_district(company["postcode"])
                for key in _keys(words.tokens(company["name"])):
                    self.by_word[district][key].append(company)

    def __call__(self, place):
        seen = {}
        for company in self.by_name.get(text.name_key(place["name"]), []):
            seen[company["number"]] = company
        nearby = self.by_word.get(text.postcode_district(place["postcode"]), {})
        for key in _keys(words.tokens(place["name"])):
            for company in nearby.get(key, ()):
                seen.setdefault(company["number"], company)
        return list(seen.values())


def _best(place, companies, rarity, where_is, nearby=()):
    judged = [(verdict[0], company, verdict[1], verdict[2]) for company in companies
              if (verdict := _judge(place, company, rarity, where_is, nearby))]
    if not judged:
        return None
    judged.sort(key=lambda item: -item[0])
    close = [j for j in judged if judged[0][0] - j[0] < CLEAR_LEAD]
    if len(close) == 1:
        return judged[0]
    # Too alike to choose between, unless exactly one has the very same name
    # (KINDRED HAIR & BEAUTY LIMITED over KINDRED HAIR & BEAUTY (HOVE) LTD).
    exact = [j for j in close if words.tokens(j[1]["name"]) == words.tokens(place["name"])]
    return exact[0] if len(exact) == 1 else None


def _named_by_register(place, index):
    """A regulator's register that names the operating company settles it."""
    if not place.get("legal_name"):
        return None
    same = [c for c in index.get(text.name_key(place["legal_name"]), [])
            if words.tokens(c["name"]) == words.tokens(place["legal_name"])]
    if len(same) != 1:
        return None
    register = "+".join(s for s in place["source"].split("+") if s not in ("overture", "osm"))
    return SPOT + 2.0, same[0], f"named by the {register or 'regulator'} register", SPOT


def wanted_postcodes(index):
    return {c["postcode"] for companies in index.values() for c in companies if c["postcode"]}


def mark(places, index, target=None, postcodes=None):
    """Fill the company columns of the places that match a company. postcodes
    is a geo.Postcodes; without it, distances come from the places found."""
    names = [company["name"] for companies in index.values() for company in companies]
    rarity = Rarity(names, Vocabulary(target))
    candidates = _Finder(index)
    where_is = _Map(places, postcodes)
    areas = district_words(places)

    found = {}
    for i, place in enumerate(places):
        named = _named_by_register(place, index)
        if named:
            found[i] = named
            continue
        nearby = areas.get(text.postcode_district(place["postcode"]), ())
        best = _best(place, candidates(place), rarity, where_is, nearby)
        if best:
            found[i] = best

    # One company, several places. The same name in several spots may be
    # branches, or unrelated businesses sharing a name, so only matches near
    # the registered office stay. Differently named places: only the
    # strongest match at the company's own address keeps it.
    by_company = collections.defaultdict(list)
    for i, (score, company, how, closeness) in found.items():
        by_company[company["number"]].append(i)
    for members in by_company.values():
        if len(members) < 2:
            continue
        if len({tuple(words.tokens(places[i]["name"])) for i in members}) == 1:
            keep = [i for i in members if found[i][3] >= NEAR]
        else:
            at_office = sorted((i for i in members if found[i][3] == SPOT),
                               key=lambda i: -found[i][0])
            keep = at_office[:1]
        for i in members:
            if i not in keep:
                del found[i]

    for i, (score, company, how, closeness) in found.items():
        place = places[i]
        place["company_number"] = company["number"]
        place["company_name"] = company["name"]
        place["company_type"] = company["category"]
        place["company_match"] = how
    return len(found)
