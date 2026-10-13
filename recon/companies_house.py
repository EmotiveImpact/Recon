"""Mark which UK places are companies, using Companies House's free monthly file.

Download "BasicCompanyDataAsOneFile" (or its parts) from
https://download.companieshouse.gov.uk/en_output.html and pass the zip or CSV.
The file has no emails or websites: it only tells us who is a company, which
decides whether UK law lets us email them without asking first.
"""

import csv
import io
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


def mark(places, index):
    matched = 0
    for place in places:
        candidates = index.get(text.name_key(place["name"]))
        company = _pick(place, candidates) if candidates else None
        if company:
            place["company_number"] = company["number"]
            place["company_name"] = company["name"]
            place["company_type"] = company["category"]
            matched += 1
    return matched
