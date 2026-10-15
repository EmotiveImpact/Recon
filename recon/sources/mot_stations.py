"""Active MOT test stations (DVSA, Open Government Licence).

Every garage in Great Britain approved to carry out MOT tests, with its
trading name, address, phone and the vehicle classes it tests. No emails or
websites: Recon finds them later. Updated monthly; the current file is found
on the GOV.UK publication page.
"""

import os
import re
import urllib.request

from . import USER_AGENT, corporate_name, download, joined, read_csv, record, rule

SOURCE = {
    "name": "dvsa-mot-stations",
    "title": "DVSA active MOT test stations",
    "country": "GB",
    "url": "https://www.gov.uk/government/publications/active-mot-test-stations",
    "licence": "Open Government Licence v3.0",
    "updated": "monthly",
    "fields": "trading name, address, phone, MOT vehicle classes",
}

_CSV = re.compile(r'href="(https://assets\.publishing\.service\.gov\.uk/[^"]+\.csv)"')

# What each MOT class covers, in plain words.
CLASSES = {"1": "motorbikes up to 200cc", "2": "motorbikes", "3": "three-wheelers",
           "4": "cars and light vans", "5": "minibuses and buses", "7": "goods vehicles 3 to 3.5 tonnes"}


def latest_csv():
    request = urllib.request.Request(SOURCE["url"], headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        page = response.read().decode("utf-8", "replace")
    links = _CSV.findall(page)
    if not links:
        raise RuntimeError("No CSV listed on the active MOT test stations page")
    return links[0]


def rows(cache):
    url = latest_csv()
    # The asset folder id changes with each release, so keep it in the file name.
    folder = url.rstrip("/").split("/")[-2]
    path = download(url, os.path.join(cache, f"{folder}-{os.path.basename(url)}"))
    for row in read_csv(path):
        name = row["Trading_Name"]
        is_corp = corporate_name(name)
        can, why = rule("GB", is_corp, "garage trading as a company" if is_corp
                        else "garage not shown to be incorporated: post only")
        classes = [CLASSES[c] for c in CLASSES if row.get(f"Class_{c}") == "Y"]
        yield record(
            SOURCE, row["Site_Number"], name, kind="garage",
            category=joined("MOT test station", *classes, sep="; "), status="active",
            address=joined(row["Address1"], row["Address2"], row["Address3"]),
            town=row["Town"], postcode=row["Postcode"], country="GB",
            phones=row["Phone"], registration_number=f"MOT site {row['Site_Number']}",
            can_email=can, rule_reason=why, source_url=url)
