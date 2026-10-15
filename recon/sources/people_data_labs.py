"""People Data Labs free company dataset (CC BY 4.0).

About 24 million companies worldwide, each with its website, LinkedIn page,
industry, size band, founding year and town; no emails or phones. Only the UK
and US companies are kept. Their websites and LinkedIn pages join the same
business in the registers and on the maps (by website, or by name and town),
so those gain a LinkedIn page and a website. This is the company list People
Data Labs publish openly; nothing here comes from personal profiles.
"""

import os

from . import corporate_name, download, joined, read_csv, record, rule

SOURCE = {
    "name": "people-data-labs",
    "title": "People Data Labs free company dataset",
    "country": "GB, US",
    "url": "https://www.peopledatalabs.com/company-dataset",
    "licence": "CC BY 4.0 (People Data Labs)",
    "updated": "quarterly",
    "fields": "name, website, LinkedIn page, industry, size, founded, town and region",
}

FILE = "https://open.peopledatalabs.com/datasets/company_dataset/free_company_dataset.csv.zip"
COUNTRIES = {"united kingdom": "GB", "united states": "US"}


def rows(cache):
    # Despite its name the file is a gzipped CSV.
    path = download(FILE, os.path.join(cache, "free_company_dataset.gz"))
    for row in read_csv(path, encoding="utf-8"):
        country = COUNTRIES.get(row["country"])
        if not country or not row["name"]:
            continue
        yield to_record(row, country)


def to_record(row, country):
    name = row["name"].title() if row["name"].islower() else row["name"]
    corporate = corporate_name(name)
    if country == "GB":
        can, why = rule("GB", corporate, "trading as a company" if corporate else
                        "not shown to be a company: post only unless Companies House shows it is")
    else:
        can, why = rule("US", None, "US business: CAN-SPAM")
    linkedin = row["linkedin_url"]
    if linkedin and "://" not in linkedin:
        linkedin = "https://" + linkedin
    return record(
        SOURCE, row["id"], name, kind="company",
        category=joined(row["industry"], f"{row['size']} staff" if row["size"] else "",
                        f"founded {row['founded']}" if row["founded"] else "", sep="; "),
        town=(row["locality"] or "").title(), region=(row["region"] or "").title(),
        country=country, website=row["website"], socials=linkedin,
        can_email=can, rule_reason=why)
