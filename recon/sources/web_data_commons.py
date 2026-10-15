"""Web Data Commons: the business details websites publish about themselves.

Schema.org "LocalBusiness" markup taken from the Common Crawl (December 2024
release), UK and US only: name, address, phone, website and social pages. It
states no open licence (it is offered for research) and Common Crawl's terms
ban harvesting personal data, so emails were never extracted. Loaded on
Edem's instruction (13 October 2026), tagged so it can be taken out again.

The research thread prepared the file in the shared incoming folder. Rows from
listing sites (site_kind "directory") are copies, so they never give a
website unless the listing names one that is not the listing site itself.
"""

import glob
import os

from . import corporate_name, read_csv, record, rule
from .. import text

SOURCE = {
    "name": "web-data-commons-2024-12",
    "title": "Web Data Commons schema.org LocalBusiness (Common Crawl, December 2024)",
    "country": "GB, US",
    "url": "https://webdatacommons.org/structureddata/2024-12/stats/schema_org_subsets.html",
    "licence": "No open licence (offered for research); Common Crawl terms: no personal data, "
               "no spam. Loaded on Edem's instruction; emails left out",
    "updated": "yearly",
    "fields": "name, address, phone, website, social pages",
}


def incoming():
    folder = os.environ.get("RECON_INCOMING", "/mnt/project-files/master-db/incoming")
    found = sorted(glob.glob(os.path.join(folder, "web-data-commons", "*.csv.gz")))
    if not found:
        raise FileNotFoundError(f"No Web Data Commons file in {folder}/web-data-commons/")
    return found[-1]


def rows(cache):
    for n, row in enumerate(read_csv(incoming(), encoding="utf-8")):
        if row["country"] in ("GB", "US") and row["name"]:
            yield to_record(n, row)


def to_record(n, row):
    country = row["country"]
    own = row["site_kind"] == "own site"
    website = row["website"]
    try:
        if website and not own and text.domain(website) == text.domain(row["page"]):
            website = ""  # The listing site's own address, not the business's.
    except ValueError:  # A malformed address such as "http://[x".
        website = ""
    if own and not website:
        website = "https://" + row["domain"]
    corporate = corporate_name(row["name"])
    if country == "GB":
        can, why = rule("GB", corporate, "trading as a company" if corporate else
                        "not shown to be a company: post only unless Companies House shows it is")
    else:
        can, why = rule("US", None, "US business: CAN-SPAM")
    if not own:
        why += "; copied from a listing site, less reliable"
    return record(
        SOURCE, n, row["name"], kind="business" if own else "business (listing site)",
        category=row["types"], address=row["street"], town=row["locality"],
        region=row["region"], postcode=row["postcode"], country=country, website=website,
        phones=row["telephone"], socials=row["socials"], can_email=can, rule_reason=why,
        source_url=row["page"], fetched="2024-12-01")
