"""Care Inspectorate Scotland datastore (Open Government Licence).

Every registered care service in Scotland: care homes, nurseries, home care,
support services and childminders, almost all with an email, phone and the
manager's name. Updated monthly; the newest file is found on the datastore page.
"""

import os
import re
import urllib.request

from . import USER_AGENT, corporate_name, download, joined, read_csv, record, rule

SOURCE = {
    "name": "care-inspectorate-scotland",
    "title": "Care Inspectorate Scotland datastore",
    "country": "GB",
    "url": "https://www.careinspectorate.scot/resources-data/data-and-statistics/datastore",
    "licence": "Open Government Licence v3.0",
    "updated": "monthly",
    "fields": "service and provider name, type, address, email, phone, manager",
}

_PAGE = re.compile(r'href="(/resources-data/publications-and-statistics/library/datastore-[^"]+)"')
_CSV = re.compile(r'href="(https://[^"]+datastoreexternal\.csv)"')


def _get(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8", "replace")


def latest_csv():
    pages = _PAGE.findall(_get(SOURCE["url"]))
    if not pages:
        raise RuntimeError("No datastore files listed on the Care Inspectorate page")
    links = _CSV.findall(_get("https://www.careinspectorate.scot" + pages[0]))
    if not links:
        raise RuntimeError("The newest datastore page has no CSV link")
    return links[0]


def corporate(row):
    """Councils and health boards are public bodies; private and voluntary
    providers count when their name shows a company or SCIO. Childminders
    are individuals."""
    if row["CareService"] == "Child Minding":
        return False
    if row["ServiceType"] in ("Local Authority", "Health Board"):
        return True
    return corporate_name(row["ServiceProvider"])


def rows(cache):
    url = latest_csv()
    path = download(url, os.path.join(cache, os.path.basename(url)))
    for row in read_csv(path, encoding="cp1252"):
        if row["ServiceStatus"] != "Active" or row["PublicList"] == "No":
            continue
        is_corp = corporate(row)
        if row["CareService"] == "Child Minding":
            why = "childminder: an individual, post only"
        elif is_corp:
            why = "council, health board or incorporated provider: a corporate body under PECR"
        else:
            why = "provider not shown to be incorporated: post only"
        can, why = rule("GB", is_corp, why)
        yield record(
            SOURCE, row["CSNumber"], row["ServiceName"], other_name=row["ServiceProvider"],
            kind="childminder" if row["CareService"] == "Child Minding" else "care service",
            category=joined(row["CareService"], row["Subtype"], sep=": "),
            legal_form=row["ServiceType"], status=row["ServiceStatus"],
            address=joined(*(row[f"Address_line_{i}"] for i in range(1, 5))),
            town=row["Service_town"], region=row["Council_Area_Name"],
            postcode=row["Service_Postcode"], country="GB",
            emails=row["Eforms_email_address"], phones=row["Service_Phone_Number"],
            people=row["Manager_Name"], registration_number=row["CSNumber"],
            can_email=can, rule_reason=why)
