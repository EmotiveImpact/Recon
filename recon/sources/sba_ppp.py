"""SBA Paycheck Protection Program loan data (US federal, released under FOIA).

Every business that took a PPP loan in 2020-21: about 11.5 million loans over
thirteen CSV files (one for loans over $150,000, twelve for smaller loans),
about 5 GB in all. Each borrower comes with its address, NAICS industry code,
business type, jobs reported and loan status. A borrower with two loans
(first and second draw) is loaded once, matched on name and ZIP code. The
files are read row by row and never held in memory.

Sole proprietors, self-employed people, independent contractors and joint
ventures between spouses are individuals, so they are post only. Borrowers
the SBA withheld under FOIA exemptions ("Exemption 6", "NOT AVAILABLE") are
dropped. Loan amounts are left out: they say nothing about how to reach a
business.
"""

import hashlib
import os
import re

from . import download, read_csv, record, rule

SOURCE = {
    "name": "sba-ppp-borrowers",
    "title": "SBA Paycheck Protection Program borrowers (2020-21)",
    "country": "US",
    "url": "https://data.sba.gov/dataset/ppp-foia",
    "licence": "US federal government data (public domain)",
    "updated": "final release 30 September 2024",
    "fields": "borrower name, address, NAICS code, business type, jobs reported, loan status",
}

BASE = "https://data.sba.gov/sites/default/files/distribution/SBA-OCA-2022-07-001/"
RELEASE = "240930"
FILES = [f"public_150k_plus_{RELEASE}.csv"] + [
    f"public_up_to_150k_{n}_{RELEASE}.csv" for n in range(1, 13)]

INDIVIDUAL = {"sole proprietorship", "self-employed individuals", "independent contractors",
              "qualified joint-venture (spouses)"}
WITHHELD = re.compile(r"^(exemption \d+|not available|n/?a|none|unknown)?$", re.I)
NON_PROFIT = re.compile(r"non-?profit|501\(c\)|cooperative|tribal|housing co-?op", re.I)


def borrower_key(row):
    """Name and five-digit ZIP, hashed small so 11.5 million fit in memory."""
    name = " ".join((row.get("BorrowerName") or "").upper().split())
    key = f"{name}|{(row.get('BorrowerZip') or '')[:5]}"
    return int.from_bytes(hashlib.blake2b(key.encode(), digest_size=8).digest(), "big")


def _jobs(text):
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return None


def to_record(row):
    # The files are Windows-1252, with a stray "¿" where a dash was meant.
    business = " ".join((row.get("BusinessType") or "").replace("\xbf", "-").split())
    jobs = _jobs(row.get("JobsReported"))
    category = "; ".join(p for p in (
        f"{jobs} job{'s' if jobs != 1 else ''} reported (PPP 2020-21)" if jobs is not None else "",
        f"NAICS {row['NAICSCode'].strip()}" if (row.get("NAICSCode") or "").strip() else "",
        business) if p)
    if business.lower() in INDIVIDUAL:
        kind = "sole trader"
        can, why = rule("US", False, "individual: post only")
    else:
        kind = "nonprofit" if (row.get("NonProfit") == "Y" or NON_PROFIT.search(business)) \
            else "business"
        can, why = rule("US", None, "US business: CAN-SPAM allows business email with an opt-out")
    state = (row.get("BorrowerState") or row.get("ProjectState") or "").strip()
    return record(
        SOURCE, row["LoanNumber"], row.get("BorrowerName"), kind=kind, category=category,
        legal_form=business, status=f"PPP loan {(row.get('LoanStatus') or '').strip()}".strip(),
        address=row.get("BorrowerAddress"), town=(row.get("BorrowerCity") or "").title(),
        region=state, postcode=row.get("BorrowerZip"), country="US",
        registration_number=f"PPP loan {row['LoanNumber']}", can_email=can, rule_reason=why)


def rows(cache):
    seen = set()
    for name in FILES:
        path = download(BASE + name, os.path.join(cache, name))
        for row in read_csv(path, encoding="cp1252"):
            if WITHHELD.match((row.get("BorrowerName") or "").strip()):
                continue
            key = borrower_key(row)
            if key in seen:
                continue
            seen.add(key)
            yield to_record(row)
