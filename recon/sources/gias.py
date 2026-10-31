"""Get Information About Schools (Department for Education, Open Government Licence).

Every open school, academy, further education college, sixth form and
university in England (and some in Wales), with website, phone and the head's
name. No emails: Recon finds them on each website. Updated daily.
"""

import os
from datetime import date, timedelta

from . import corporate_name, download, joined, read_csv, record, rule

SOURCE = {
    "name": "gias-schools-colleges",
    "title": "Get Information About Schools (England)",
    "country": "GB",
    "url": "https://get-information-schools.service.gov.uk/Downloads",
    "licence": "Open Government Licence v3.0",
    "updated": "daily",
    "fields": "name, type, phase, address, website, phone, head teacher",
}

DOWNLOAD = "https://ea-edubase-api-prod.azurewebsites.net/edubase/downloads/public/edubasealldata{}.csv"

KINDS = {"Colleges": "college", "Universities": "university"}

# Councils' schools, academy trusts (companies), colleges and universities
# (statutory corporations) are all corporate bodies. Independent schools are
# often companies or charities; only a company name proves it.
PUBLIC_GROUPS = ("Academies", "Free Schools", "Local authority maintained schools", "Special schools",
                 "Colleges", "Universities", "Welsh schools")


def rows(cache):
    for days in range(7):
        day = (date.today() - timedelta(days=days)).strftime("%Y%m%d")
        try:
            path = download(DOWNLOAD.format(day), os.path.join(cache, f"edubasealldata{day}.csv"))
            break
        except OSError:
            continue
    else:
        raise RuntimeError("No GIAS download found for the last week")
    for row in read_csv(path, encoding="cp1252"):
        if not row["EstablishmentStatus (name)"].startswith("Open"):
            continue
        group = row["EstablishmentTypeGroup (name)"]
        is_corp = group in PUBLIC_GROUPS or corporate_name(row["Trusts (name)"]) or \
            corporate_name(row["EstablishmentName"])
        can, why = rule("GB", is_corp, "council school, academy trust, college or university: a "
                        "corporate body" if is_corp else "independent school not shown to be a company")
        head = joined(row["HeadTitle (name)"], row["HeadFirstName"], row["HeadLastName"], sep=" ")
        sixth = row["OfficialSixthForm (name)"] == "Has a sixth form"
        yield record(
            SOURCE, row["URN"], row["EstablishmentName"],
            kind=KINDS.get(group, "school"),
            category=joined(row["TypeOfEstablishment (name)"], row["PhaseOfEducation (name)"],
                            "sixth form" if sixth else "", row["FurtherEducationType (name)"], sep="; "),
            legal_form=group, status=row["EstablishmentStatus (name)"],
            address=joined(row["Street"], row["Locality"], row["Address3"]), town=row["Town"],
            region=row["LA (name)"], postcode=row["Postcode"], country="GB",
            website=row["SchoolWebsite"], phones=row["TelephoneNum"], people=head,
            registration_number=f"URN {row['URN']}", can_email=can, rule_reason=why)
