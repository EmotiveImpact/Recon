"""SEC Form D data sets: companies and funds raising money privately (US federal).

Every Form D notice filed with the SEC: the issuer's name, address, phone,
legal form and CIK, the people named as executive officers, directors and
promoters, and the industry group and revenue range of the offering. The SEC
publishes one zip per quarter; the last eight quarters are loaded, newest
first, and each issuer (by CIK) is kept once, from its newest filing. Only
issuers with a US address are kept.

The SEC asks automated users to send a User-Agent that names them, and limits
how often anyone may download (its "fair access" rules). The zips are small
(a few MB each) and are fetched once into the cache.
"""

import csv
import io
import os
import urllib.error
import zipfile
from datetime import date, datetime

from . import download, joined, record, rule

SOURCE = {
    "name": "sec-form-d",
    "title": "SEC Form D data sets (private offerings by US companies and funds)",
    "country": "US",
    "url": "https://www.sec.gov/dera/data/form-d",
    "licence": "US federal government data (public domain)",
    "updated": "quarterly",
    "fields": "issuer name, address, phone, legal form, CIK, executive officers and directors, "
              "industry group, revenue range",
    "pending": "sec.gov refuses downloads from the cloud workspace (403); untested on real files",
}

USER_AGENT = "Recon open-data research (github.com/EmotiveImpact/Recon)"
ZIP_URL = "https://www.sec.gov/files/structureddata/data/form-d-data-sets/{quarter}_d.zip"
QUARTERS = 8

US_STATES = set(
    "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH "
    "NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY PR GU VI AS MP".split())


def recent_quarters(today=None, count=QUARTERS + 2):
    """Quarter names such as '2026q2', newest first, starting with the last
    finished quarter. Two spare ones cover a quarter not yet published."""
    today = today or date.today()
    year, quarter = today.year, (today.month - 1) // 3  # the last finished quarter
    found = []
    while len(found) < count:
        if quarter == 0:
            year, quarter = year - 1, 4
        found.append(f"{year}q{quarter}")
        quarter -= 1
    return found


def quarter_zips(cache):
    """Paths of the newest eight quarterly zips, fetched once. A quarter the
    SEC has not published yet (404) is skipped; any other refusal stops the run."""
    paths = []
    for quarter in recent_quarters():
        path = os.path.join(cache, f"{quarter}_d.zip")
        try:
            download(ZIP_URL.format(quarter=quarter), path, headers={"User-Agent": USER_AGENT},
                     attempts=2)
        except urllib.error.HTTPError as error:
            if error.code == 404:
                continue
            raise OSError(f"SEC refused {ZIP_URL.format(quarter=quarter)} ({error.code}); "
                          "see https://www.sec.gov/developer for its fair access rules") from error
        paths.append(path)
        if len(paths) == QUARTERS:
            break
    return paths


def _table(archive, name):
    """Rows of one tab-separated table inside a quarter's zip."""
    member = next(m for m in archive.namelist() if m.upper().endswith(name.upper() + ".TSV"))
    with archive.open(member) as raw:
        handle = io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline="")
        yield from csv.DictReader(handle, delimiter="\t", quoting=csv.QUOTE_NONE)


def _filed(text):
    """The filing date; the data sets write it as 16-JUN-2025."""
    for pattern in ("%d-%b-%Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime((text or "").strip(), pattern).date()
        except ValueError:
            pass
    return date.min


def person(row):
    """'Jane Smith (Executive Officer, Director)' from a RELATEDPERSONS row."""
    name = " ".join(p.strip().title() for p in (row.get("FIRSTNAME"), row.get("MIDDLENAME"),
                                                row.get("LASTNAME")) if p and p.strip())
    roles = [row.get(f"RELATIONSHIP_{n}", "").strip() for n in (1, 2, 3)]
    roles = [r for r in roles if r]
    return f"{name} ({', '.join(roles)})" if name and roles else name


def to_record(issuer, filed=None, offering=None, people=()):
    """One record from an ISSUERS row and its filing's offering and people,
    or None when the issuer is not in the US."""
    state = (issuer.get("STATEORCOUNTRY") or "").strip().upper()
    if state not in US_STATES:
        return None
    offering = offering or {}
    entity = (issuer.get("ENTITYTYPE") or "").strip()
    if entity.lower() == "other" and issuer.get("ENTITYTYPEOTHERDESC"):
        entity = issuer["ENTITYTYPEOTHERDESC"].strip()
    industry = (offering.get("INDUSTRYGROUPTYPE") or "").strip()
    revenue = (offering.get("REVENUERANGE") or "").strip()
    category = joined(industry, f"revenue {revenue}" if revenue else "", sep="; ")
    can, why = rule("US", None, "US business: CAN-SPAM allows business email with an opt-out")
    cik = issuer["CIK"].strip().lstrip("0")
    return record(
        SOURCE, cik, issuer.get("ENTITYNAME"),
        other_name=issuer.get("ISSUER_PREVIOUSNAME_1") or "",
        kind="fund" if industry == "Pooled Investment Fund" else "company",
        category=category, legal_form=entity,
        status=f"Form D filed {filed.isoformat()}" if filed and filed != date.min else "",
        address=joined(issuer.get("STREET1"), issuer.get("STREET2")), town=issuer.get("CITY"),
        region=state, postcode=issuer.get("ZIPCODE"), country="US",
        phones=issuer.get("ISSUERPHONENUMBER"), people=list(people),
        registration_number=f"CIK {cik}", can_email=can, rule_reason=why,
        source_url=f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}")


def quarter_records(path):
    """Records from one quarter's zip, newest filing first."""
    with zipfile.ZipFile(path) as archive:
        filed = {r["ACCESSIONNUMBER"]: _filed(r.get("FILING_DATE"))
                 for r in _table(archive, "FORMDSUBMISSION")
                 if (r.get("TESTORLIVE") or "LIVE").upper() == "LIVE"}
        offerings = {r["ACCESSIONNUMBER"]: r for r in _table(archive, "OFFERING")}
        people = {}
        for r in _table(archive, "RELATEDPERSONS"):
            if found := person(r):
                people.setdefault(r["ACCESSIONNUMBER"], []).append(found)
        issuers = [r for r in _table(archive, "ISSUERS")
                   if r["ACCESSIONNUMBER"] in filed and (r.get("CIK") or "").strip()]
    issuers.sort(key=lambda r: filed[r["ACCESSIONNUMBER"]], reverse=True)
    for issuer in issuers:
        accession = issuer["ACCESSIONNUMBER"]
        yield issuer["CIK"].strip().lstrip("0"), to_record(
            issuer, filed[accession], offerings.get(accession), people.get(accession, []))


def rows(cache):
    seen = set()
    for path in quarter_zips(cache):  # newest quarter first
        for cik, found in quarter_records(path):
            if cik in seen:
                continue
            seen.add(cik)
            if found:
                yield found
