"""Modern Slavery Statement Registry (Open Government Licence v3.0).

Organisations with a turnover of £36 million or more that publish a modern
slavery statement, plus public bodies and smaller ones that report by choice.
One file per statement year, each listing every organisation a statement
covers (a group statement lists each member company). The newest entry per
organisation is kept: name, address, company number, sector, turnover band,
the director who approved the statement, and the email given when there is
no statement web page. The statement's web address gives the website, unless
it sits on a document host.

Companies and public bodies may be emailed; anyone else is post only.
"""

import os
import re
from datetime import date

from .. import contacts, text
from . import corporate_name, download, joined, read_csv, record, rule
from .gender_pay_gap import incoming, site_from_link

SOURCE = {
    "name": "modern-slavery-statements",
    "title": "Modern Slavery Statement Registry",
    "country": "GB",
    "url": "https://modern-slavery-statement-registry.service.gov.uk/",
    "licence": "Open Government Licence v3.0",
    "updated": "continuously (yearly files)",
    "fields": "organisation name, address, company number, sector, turnover band, approving director, website, email",
}

BASE = "https://downloads.modern-slavery-statement-registry.service.gov.uk/publicdownloads"
FIRST_YEAR = 2020

_UK = {"united kingdom", "uk", "u.k.", "england", "scotland", "wales", "northern ireland",
       "great britain", "gb"}
_US = {"united states", "united states of america", "usa", "us", "u.s.a."}
_COMPANY_NUMBER = re.compile(r"^[A-Z]{0,2}\d{5,8}[A-Z]?$")


def year_file(year, cache):
    """One statement year's CSV. Statements for the current and the coming
    year are still being added, so those copies are dated and fetched again
    on a later day."""
    found = incoming(SOURCE["name"], year)
    if found and year < date.today().year - 1:
        return found
    name = f"StatementSummaries{year}.csv"
    if year >= date.today().year - 1:
        name = f"StatementSummaries{year}-{date.today().isoformat()}.csv"
    return download(f"{BASE}/StatementSummaries{year}.csv", os.path.join(cache, name))


def parse_address(value):
    """(address, town, postcode, country) from the register's address,
    which has one part per line, the country and postcode last."""
    lines = [line.strip().rstrip(",") for line in (value or "").splitlines() if line.strip()]
    postcode, country = "", ""
    for line in lines:
        if line.lower() in _UK:
            country = "GB"
        elif line.lower() in _US:
            country = "US"
    if text.postcode(lines[-1] if lines else "", "GB"):
        postcode, country = text.postcode(lines[-1], "GB"), country or "GB"
    elif country == "US" and lines:
        postcode = text.postcode(lines[-1], "US")
    if not lines:
        country = "GB"
    rest = [line for line in lines if line.lower() not in _UK | _US
            and text.postcode(line, "GB") != postcode]
    if country == "US" and postcode:
        rest = [line for line in rest if text.postcode(line, "US") != postcode]
    town = rest[-1] if len(rest) > 1 else ""
    if country == "US" and len(rest) > 2 and re.fullmatch(r"[A-Z]{2}", rest[-1]):
        town = rest[-2]
    return joined(*rest), town, postcode, country


def company_number(row):
    number = (row.get("CompanyNumber") or "").upper().replace(" ", "")
    return number if _COMPANY_NUMBER.match(number) else ""


def key_of(row):
    return company_number(row) or "name:" + text.name_key(row.get("OrganisationName"))


def to_record(row):
    name = (row.get("OrganisationName") or "").strip()
    number = company_number(row)
    address, town, postcode, country = parse_address(row.get("Address"))
    public = (row.get("SectorType") or "").strip().lower() == "public"
    if country == "US":
        can, why = rule("US", None, "US organisation: CAN-SPAM")
    elif country != "GB":
        can, why = rule(country, None, "address abroad")
    elif number:
        can, why = rule("GB", True, "registered company or corporate body (company number given)")
    elif public:
        can, why = rule("GB", True, "public body")
    elif corporate_name(name):
        can, why = rule("GB", True, "trading as a company")
    else:
        can, why = rule("GB", False, "organisation not shown to be incorporated: post only")
    emails = [e for e in re.split(r"[;,\s]+", row.get("EmailAddressNoURL") or "") if "@" in e]
    labels = {contacts.email_label(e.lower()) for e in emails}
    if contacts.PERSONAL in labels:
        why += "; personal webmail address listed"
    elif labels - {contacts.SHARED}:
        why += "; the statement contact email may be a named person: check before using"
    sectors = [s.strip() for s in re.split(r"[\r\n]+", joined(
        row.get("OrganisationSectors", ""), row.get("OtherOrganisationSector", ""),
        row.get("PublicSectorAuthorities", ""), row.get("OtherPublicSectorAuthorities", ""),
        sep="\n")) if s.strip()]
    turnover = (row.get("Turnover") or "").strip()
    parent = (row.get("ParentName") or "").strip()
    return record(
        SOURCE, key_of(row), name, kind="public body" if public else "organisation",
        category=joined(*sectors, f"turnover {turnover}" if turnover else "", sep="; "),
        status=f"modern slavery statement {row.get('StatementYear', '')}".strip(),
        address=address, town=town, postcode=postcode, country=country,
        website=site_from_link(row.get("StatementURL")),
        emails=emails,
        people=(row.get("ApprovingPerson") or "").strip(),
        company_number=number,
        other_name=f"part of {parent}" if parent and parent.lower() != name.lower() else "",
        can_email=can, rule_reason=why,
        source_url=row.get("StatementSummaryURL") or SOURCE["url"])


def _updated(row):
    day, month, year = ((row.get("LastUpdated") or "").split(" ")[0].split("/") + ["", "", ""])[:3]
    return f"{year}-{month}-{day}"


def rows(cache):
    latest = {}  # organisation -> (statement year, last updated, row)
    for year in range(FIRST_YEAR, date.today().year + 2):
        try:
            path = year_file(year, cache)
        except OSError:
            continue  # A year with no file yet.
        for row in read_csv(path):
            name = (row.get("OrganisationName") or "").strip()
            if not name or name.isdigit():  # A few entries carry only a number.
                continue
            key = key_of(row)
            order = (row.get("StatementYear", ""), _updated(row))
            if key not in latest or order > latest[key][:2]:
                latest[key] = (*order, row)
    for _, _, row in latest.values():
        yield to_record(row)
