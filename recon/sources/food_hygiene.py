"""Food Standards Agency food hygiene ratings (Open Government Licence).

Every food business inspected by a council in England, Wales, Northern
Ireland and Scotland: restaurants, cafes, takeaways, pubs, shops, hotels,
caterers, care homes, schools and manufacturers, with business type and
address. No contact details at all: the list is here so Recon can look up
each business's website later. One XML file per council, each updated
daily; they are read one at a time, element by element, to keep memory low.
"""

import os
import re
import urllib.request
import xml.etree.ElementTree as ET

from . import USER_AGENT, corporate_name, download, joined, record, rule

SOURCE = {
    "name": "fsa-food-hygiene",
    "title": "Food Standards Agency food hygiene ratings",
    "country": "GB",
    "url": "https://ratings.food.gov.uk/open-data",
    "licence": "Open Government Licence v3.0",
    "updated": "daily",
    "fields": "business name, business type, address, postcode, rating, council",
}

BASE = "https://ratings.food.gov.uk"
# English-language files only; Welsh councils also publish a Welsh copy (cy-GB).
_FILE = re.compile(r'href="(/api/open-data-files/FHRS\d+en-GB\.xml)"')


def council_files():
    request = urllib.request.Request(SOURCE["url"], headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        page = response.read().decode("utf-8", "replace")
    files = sorted(set(_FILE.findall(page)))
    if not files:
        raise RuntimeError("No council files listed on the food hygiene open data page")
    return [BASE + f for f in files]


def establishments(path):
    """Each establishment in one council file, as a dict of its simple fields."""
    for _, element in ET.iterparse(path):
        if element.tag != "EstablishmentDetail":
            continue
        yield {child.tag: (child.text or "").strip() for child in element}
        element.clear()


def rows(cache, limit=None):
    """`limit` stops after that many council files, for quick checks."""
    for url in council_files()[:limit]:
        path = download(url, os.path.join(cache, os.path.basename(url)))
        for item in establishments(path):
            lines = [item.get(f"AddressLine{i}", "") for i in range(1, 5)]
            lines = [line for line in lines if line]
            # Home-based businesses ask for their address to be withheld.
            if not lines and not item.get("PostCode"):
                continue
            name = item.get("BusinessName", "")
            is_corp = corporate_name(name)
            can, why = rule("GB", is_corp, "business named as a company" if is_corp
                            else "food business not shown to be incorporated: post only")
            yield record(
                SOURCE, item["FHRSID"], name, kind="food business",
                category=item.get("BusinessType", ""),
                status=joined(item.get("SchemeType", ""), "rating " + item["RatingValue"]
                              if item.get("RatingValue") else "", sep=" "),
                # Councils fill the lines differently (town or county last), so
                # the address is kept whole rather than guessing the town.
                address=joined(*lines),
                region=item.get("LocalAuthorityName", ""), postcode=item.get("PostCode", ""),
                country="GB", registration_number=f"FHRS {item['FHRSID']}",
                can_email=can, rule_reason=why, source_url=url)
