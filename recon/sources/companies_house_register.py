"""Companies House free company data product (Open Government Licence).

Every live company, LLP and other registered body in the UK: name, legal form,
status, registered office and up to four SIC (trade) codes. No contact details:
it is the UK backbone that says who is a company, so a row from another
register that matches one may be emailed. Updated monthly.

The file is about 500 MB zipped. Pass the folder holding it as the cache, or
let the loader fetch the newest one from the download page.
"""

import csv
import glob
import io
import os
import re
import urllib.request
import zipfile

from .. import companies_house
from . import USER_AGENT, download, joined, record, rule

SOURCE = {
    "name": "companies-house",
    "title": "Companies House basic company data",
    "country": "GB",
    "url": "https://download.companieshouse.gov.uk/en_output.html",
    "licence": "Open Government Licence v3.0 (Companies House)",
    "updated": "monthly",
    "fields": "name, company number, legal form, status, registered office, SIC codes",
}

_LINK = re.compile(r'href="(BasicCompanyDataAsOneFile-[\d-]+\.zip)"')

KINDS = {
    "community interest company": "community interest company",
    "charitable incorporated organisation": "charity",
    "limited liability partnership": "LLP",
    "registered society": "co-operative or society",
}


def latest_zip(cache):
    found = sorted(glob.glob(os.path.join(cache, "BasicCompanyDataAsOneFile-*.zip")))
    if found:
        return found[-1]
    request = urllib.request.Request(SOURCE["url"], headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        names = _LINK.findall(response.read().decode("utf-8", "replace"))
    if not names:
        raise RuntimeError("No company file listed on the Companies House download page")
    name = sorted(names)[-1]
    return download("https://download.companieshouse.gov.uk/" + name, os.path.join(cache, name))


def kind_of(category):
    lowered = (category or "").lower()
    for words, kind in KINDS.items():
        if words in lowered:
            return kind
    return "company"


def rows(cache):
    path = latest_zip(cache)
    with zipfile.ZipFile(path) as archive:
        member = next(n for n in archive.namelist() if n.lower().endswith(".csv"))
        with archive.open(member) as raw:
            reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8", errors="replace"))
            header = [h.strip() for h in next(reader)]
            for values in reader:
                row = dict(zip(header, values))
                if len(values) != len(header) or not row["CompanyStatus"].startswith("Active"):
                    continue
                category = row["CompanyCategory"]
                is_corp = companies_house.is_corporate(category)
                can, why = rule("GB", is_corp, "company or LLP: a corporate body under PECR" if is_corp
                                else f"{category.lower()}: post only under PECR")
                sic = [row[f"SICCode.SicText_{i}"] for i in range(1, 5)]
                yield record(
                    SOURCE, row["CompanyNumber"], row["CompanyName"],
                    kind=kind_of(category), category=joined(*sic, sep="; "), legal_form=category,
                    status=row["CompanyStatus"],
                    address=joined(row["RegAddress.CareOf"], row["RegAddress.POBox"],
                                   row["RegAddress.AddressLine1"], row["RegAddress.AddressLine2"]),
                    town=row["RegAddress.PostTown"], region=row["RegAddress.County"],
                    postcode=row["RegAddress.PostCode"], country="GB",
                    registration_number=row["CompanyNumber"],
                    company_number=row["CompanyNumber"], can_email=can, rule_reason=why)
