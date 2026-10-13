"""Mark which UK places are companies, using Companies House's free monthly file.

Download "BasicCompanyDataAsOneFile" (or its parts) from
https://download.companieshouse.gov.uk/en_output.html and pass the zip or CSV.
The file has no emails or websites: it only tells us who is a company, which
decides whether UK law lets us email them without asking first.
"""

import csv
import difflib
import io
import re
import zipfile

from . import text

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


def load(paths, sic_codes):
    """Active companies whose trade codes are in sic_codes, indexed by name."""
    index = {}
    total = 0
    for path in paths:
        for row in _rows(path):
            if row.get("CompanyStatus", "").strip().lower() != "active":
                continue
            codes = [row.get(f"SICCode.SicText_{n}", "")[:5] for n in range(1, 5)]
            sector = next((sic_codes[c] for c in codes if c in sic_codes), None)
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


def _pick(place, candidates):
    """Choose the company for a place, or None when it is not clear."""
    district = text.postcode_district(place["postcode"])
    town = place["town"].strip().lower()
    near = [c for c in candidates
            if (district and text.postcode_district(c["postcode"]) == district)
            or (town and c["town"] == town)]
    if len(near) == 1:
        return near[0]
    # The registered office is often an accountant's, so accept a name-only
    # match when the name is distinctive (two words or more) and unique.
    if not near and len(candidates) == 1 and len(text.name_key(place["name"]).split()) >= 2:
        return candidates[0]
    return None


# Near-match linking, after the ideas in Splink and uk_address_matcher (both
# MIT): only compare records that share a postcode district ("blocking"),
# score how alike the names are, add evidence from the address, and accept
# only a clear winner. Written fresh with difflib; no code was copied.
NEAR_NAME = 0.92        # Names this alike match on the postcode district alone.
NEAR_NAME_WITH_ADDRESS = 0.85  # ...or this alike with the same postcode or street.
CLEAR_LEAD = 0.05       # The best must beat the next best by this much.


def name_likeness(a, b):
    """0 to 1: how alike two business names are, ignoring word order and
    company words, and forgiving one name being a shorter form of the other."""
    a, b = text.name_key(a), text.name_key(b)
    if not a or not b:
        return 0.0
    words_a, words_b = set(a.split()), set(b.split())
    numbers = lambda words: {w for w in words if w.isdigit()}
    if numbers(words_a) != numbers(words_b) and numbers(words_a) and numbers(words_b):
        return 0.0  # "Studio 7" is never "Studio 8".
    sorted_a, sorted_b = " ".join(sorted(words_a)), " ".join(sorted(words_b))
    whole = difflib.SequenceMatcher(None, sorted_a, sorted_b).ratio()
    shared = " ".join(sorted(words_a & words_b))
    if not shared:
        return whole
    # Compare what they share with each full name, as a shorter form would.
    parts = [difflib.SequenceMatcher(None, shared, s).ratio() for s in (sorted_a, sorted_b)]
    fewer = min(len(words_a), len(words_b))
    if len(words_a & words_b) < fewer or fewer < 2:
        return whole  # A one-word overlap like "glow" is too weak to lean on.
    return max(whole, 0.95 * max(parts))  # A shorter form is likely, not certain.


def _same_street(place, company):
    words = lambda s: {w for w in re.findall(r"[a-z0-9]+", s.lower()) if len(w) > 1}
    street = words(place["address"])
    return bool(street) and len(street & words(company.get("street", ""))) >= 2


def _near(place, by_district):
    """The company a place most likely is, by near match, with the reason."""
    district = text.postcode_district(place["postcode"])
    if not district:
        return None, ""
    scored = []
    for company in by_district.get(district, []):
        likeness = name_likeness(place["name"], company["name"])
        if likeness < NEAR_NAME_WITH_ADDRESS:
            continue
        same_postcode = place["postcode"] == company["postcode"]
        same_street = _same_street(place, company)
        if likeness >= NEAR_NAME or same_postcode or same_street:
            where = ("same postcode" if same_postcode else
                     "same street" if same_street else "same postcode district")
            scored.append((likeness + (0.03 if same_postcode or same_street else 0),
                           company, f"close name ({likeness:.2f}), {where}"))
    scored.sort(key=lambda item: -item[0])
    if not scored or (len(scored) > 1 and scored[0][0] - scored[1][0] < CLEAR_LEAD):
        return None, ""  # Nothing, or two companies too alike to choose: stay "post only".
    return scored[0][1], scored[0][2]


def mark(places, index):
    by_district = {}
    for companies in index.values():
        for company in companies:
            by_district.setdefault(text.postcode_district(company["postcode"]), []).append(company)
    matched = 0
    for place in places:
        candidates = index.get(text.name_key(place["name"]))
        company = _pick(place, candidates) if candidates else None
        how = "same name" if company else ""
        if not company:
            company, how = _near(place, by_district)
        if company:
            place["company_number"] = company["number"]
            place["company_name"] = company["name"]
            place["company_type"] = company["category"]
            place["company_match"] = how
            matched += 1
    return matched
