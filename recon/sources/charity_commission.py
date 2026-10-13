"""Charity Commission register of charities in England and Wales (OGL v3).

About 172,000 registered charities, most with an email, phone and website.
Includes most students' unions, which are registered charities. Updated daily.
"""

import csv
import io
import os
import re
import zipfile

from . import download, joined, record, rule

SOURCE = {
    "name": "charity-commission",
    "title": "Charity Commission register (England and Wales)",
    "country": "GB",
    "url": "https://register-of-charities.charitycommission.gov.uk/register/full-register-download",
    "licence": "Open Government Licence v3.0",
    "updated": "daily",
    "fields": "name, type, address, email, phone, website, company number, activities",
}

DOWNLOAD = "https://ccewuksprdoneregsadata1.blob.core.windows.net/data/txt/publicextract.charity.zip"

STUDENTS = re.compile(r"\b(students?['’]? ?union|union of (\w+ )*students|guild of students|"
                      r"students['’]? (association|guild|representative council)|junior common room|"
                      r"athletic union)\b", re.I)
STUDENT_BODIES = re.compile(r"\bstudents?['’]?\b.*\b(society|societies|association|club|federation|"
                            r"movement|union)\b", re.I)


def kind_of(name):
    if STUDENTS.search(name or ""):
        return "students' union"
    if STUDENT_BODIES.search(name or ""):
        return "student organisation"
    return "charity"


def corporate(row):
    """PECR: charitable companies and CIOs are corporate bodies and may be
    emailed; trusts and other unincorporated charities are post only."""
    return (row["charity_type"] in ("CIO", "Charitable company") or row["charity_is_cio"] == "True"
            or bool(row["charity_company_registration_number"].strip()))


def rows(cache):
    archive = download(DOWNLOAD, os.path.join(cache, "publicextract.charity.zip"))
    csv.field_size_limit(1 << 30)
    with zipfile.ZipFile(archive) as z, z.open("publicextract.charity.txt") as raw:
        reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig", errors="replace"),
                                delimiter="\t", quoting=csv.QUOTE_NONE)
        for row in reader:
            if row["charity_registration_status"] != "Registered" or row["linked_charity_number"] != "0":
                continue
            is_corp = corporate(row)
            can, why = rule("GB", is_corp, "charitable company or CIO: a corporate body under PECR"
                            if is_corp else "trust or unincorporated charity: post only under PECR")
            lines = [row[f"charity_contact_address{i}"] for i in range(1, 6)]
            lines = [line for line in lines if line.strip()] or [""]
            yield record(
                SOURCE, row["registered_charity_number"], row["charity_name"],
                kind=kind_of(row["charity_name"]), category=row["charity_activities"][:300],
                legal_form=row["charity_type"] or "Other", status="Registered",
                address=joined(*lines[:-1]), town=lines[-1] or "", postcode=row["charity_contact_postcode"],
                country="GB", website=row["charity_contact_web"], emails=row["charity_contact_email"],
                phones=row["charity_contact_phone"],
                registration_number=joined(row["registered_charity_number"],
                                           row["charity_company_registration_number"], sep="; "),
                company_number=row["charity_company_registration_number"],
                can_email=can, rule_reason=why)
