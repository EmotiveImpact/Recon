"""Open registers loaded into one master table, one loader per source.

Each loader module has a SOURCE description and a `rows(cache)` generator that
yields records in the common shape made by `record()`. Every record carries
where it came from (source, licence, link and the date it was fetched), so any
lead can be traced back to the register it was copied from.

"can email" is decided per source and per legal form, following docs/RULES.md:
UK companies, LLPs, CIOs and public bodies yes; sole traders, partnerships,
unincorporated bodies and individuals "post only"; US businesses yes under
CAN-SPAM unless a source's own terms forbid marketing to them.
"""

import csv
import gzip
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import date

from .. import contacts, text
from ..rules import CAN_EMAIL, POST_ONLY

USER_AGENT = "Mozilla/5.0 (compatible; recon/0.1; in-house research)"

# The master table's columns, in order. Lists (emails, phones, socials, people)
# are stored as text joined with "; " so the table opens in any spreadsheet.
FIELDS = [
    "record_id", "name", "other_name", "kind", "category", "legal_form", "status",
    "address", "town", "region", "postcode", "country",
    "website", "emails", "phones", "socials", "people",
    "registration_number", "company_number", "can_email", "rule_reason",
    "source", "source_id", "licence", "source_url", "fetched",
]

# Words in a name that show a business is incorporated. Used only when a
# register does not say the legal form outright.
_CORPORATE_NAME = re.compile(
    r"\b(ltd|limited|plc|llp|l\.l\.p|cic|cio|inc|incorporated|corp|corporation|"
    r"llc|l\.l\.c|pllc|lp|co\.?|company|pc|p\.c|scio)\b\.?\s*$", re.I)


def record(source, source_id, name, **values):
    """A row in the common shape. Unknown keys are refused, so a loader
    can't quietly invent a column."""
    unknown = set(values) - set(FIELDS)
    if unknown:
        raise ValueError(f"Not master columns: {sorted(unknown)}")
    row = dict.fromkeys(FIELDS, "")
    row.update({k: _flat(v) for k, v in values.items()})
    row["name"] = " ".join((name or "").split())
    row["source"] = source["name"]
    row["source_id"] = str(source_id)
    row["record_id"] = f"{source['name']}:{source_id}"
    row["licence"] = row["licence"] or source["licence"]
    row["source_url"] = row["source_url"] or source["url"]
    row["fetched"] = row["fetched"] or date.today().isoformat()
    row["emails"] = "; ".join(clean_emails(row["emails"]))
    row["phones"] = "; ".join(clean_phones(row["phones"], row["country"]))
    if row["company_number"]:  # Companies House numbers are eight characters.
        number = row["company_number"].upper().replace(" ", "")
        row["company_number"] = number.zfill(8) if number.isdigit() else number
    if row["website"] and "://" not in row["website"]:
        row["website"] = "http://" + row["website"].strip()
    if row["postcode"]:
        found = text.postcode(row["postcode"], row["country"])
        if not found:  # Registers sometimes put the town in the postcode box.
            row["address"] = joined(row["address"], row["postcode"])
        row["postcode"] = found
    return row


def _flat(value):
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return "; ".join(str(v).strip() for v in value if v and str(v).strip())
    return str(value).strip()


def clean_emails(value):
    found = []
    for part in re.split(r"[;,\s]+", value or ""):
        part = part.strip().strip(".").lower()
        if part.startswith("mailto:"):
            part = part[7:]
        if part and contacts.valid_email(part) and part not in found:
            found.append(part)
    return found


def clean_phones(value, country=""):
    found = []
    for part in re.split(r"[;,/]|\bor\b", value or ""):
        digits = re.sub(r"[^\d+]", "", part)
        if len(digits.lstrip("+")) < 7 or set(digits.lstrip("+")) == {"0"}:
            continue
        if country == "US" and len(digits) == 10:
            digits = f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
        if digits not in found:
            found.append(digits)
    return found


def corporate_name(name):
    """True when a name ends in a company word such as Ltd, Inc or LLC."""
    return bool(_CORPORATE_NAME.search((name or "").strip()))


def rule(country, corporate, reason):
    """(can_email, rule_reason) for a record."""
    if country == "GB":
        return (CAN_EMAIL if corporate else POST_ONLY), reason
    if country == "US":
        return (CAN_EMAIL if corporate is not False else POST_ONLY), reason
    return "check local rules", reason


# ---- downloading ---------------------------------------------------------

def download(url, path, headers=None, attempts=4):
    """Fetch url to path once; later runs reuse the copy."""
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    wanted = {"User-Agent": USER_AGENT, **(headers or {})}
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers=wanted)
            with urllib.request.urlopen(request, timeout=300) as response, \
                    open(path + ".part", "wb") as out:
                while chunk := response.read(1 << 20):
                    out.write(chunk)
            os.replace(path + ".part", path)
            return path
        except OSError:
            if attempt == attempts - 1:
                raise
            time.sleep(2 ** (attempt + 1))
    return path


def socrata(domain, dataset, cache, select="*", where="", page=200_000):
    """Rows of a Socrata open-data table (most US state and city portals),
    fetched in pages as CSV and kept in the cache folder."""
    offset = 0
    while True:
        query = {"$select": select, "$limit": page, "$offset": offset, "$order": ":id"}
        if where:
            query["$where"] = where
        url = f"https://{domain}/resource/{dataset}.csv?" + urllib.parse.urlencode(query)
        path = os.path.join(cache, f"{dataset}-{offset}.csv")
        download(url, path)
        count = 0
        with open(path, encoding="utf-8", errors="replace", newline="") as handle:
            for row in csv.DictReader(handle):
                count += 1
                yield row
        if count < page:
            return
        offset += page


def read_csv(path, delimiter=",", encoding="utf-8-sig"):
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding=encoding, errors="replace", newline="") as handle:
        yield from csv.DictReader(handle, delimiter=delimiter)


def joined(*parts, sep=", "):
    return sep.join(p.strip() for p in parts if p and p.strip())


# Loader modules in this folder, in loading order.
LOADERS = ["connecticut", "charity_commission", "washington_vendors", "fmcsa",
           "care_inspectorate_scotland", "gias", "us_open_lists",
           "mot_stations", "nhs_ods", "marriage_venues", "food_hygiene", "companies_house_register",
           "find_that_charity", "traffic_commissioners", "ofs_register", "uk_unions",
           "irs_nonprofits", "us_colleges", "us_unions", "texas_tdlr", "nppes", "us_city_registers",
           "virginia_dpor", "california_cslb", "cqc", "overture_places", "people_data_labs", "recon_runs"]


def registry():
    """Every loader, by source name."""
    import importlib
    found = {}
    for name in LOADERS:
        module = importlib.import_module(f"{__name__}.{name}")
        # A module holds one source (SOURCE and rows) or several (SOURCES).
        for loader in getattr(module, "SOURCES", None) or [module]:
            found[loader.SOURCE["name"]] = loader
    return found


def catalogue():
    """The list of sources, for the sources table in the master database."""
    return [dict(m.SOURCE) for m in registry().values()]
