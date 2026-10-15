"""Washington state WEBS registered vendors (data.wa.gov).

About 105,000 suppliers to the state, all with an email, phone and often a
website. Washington law (RCW 42.56.070(8)) bars using lists of individuals for
commercial purposes, so anyone not plainly incorporated is post only.
"""

from . import corporate_name, joined, record, rule, socrata

SOURCE = {
    "name": "washington-webs-vendors",
    "title": "Washington state WEBS vendors",
    "country": "US",
    "url": "https://data.wa.gov/d/3kwi-7zsj",
    "licence": "Washington open data; no commercial use of lists of individuals (RCW 42.56.070(8))",
    "updated": "2017 snapshot",
    "fields": "name, trading name, town, state, email, phone, website, work done",
}


def rows(cache):
    seen = set()
    for row in socrata("data.wa.gov", "3kwi-7zsj", cache):
        key = (row["company_name"], row["contact_email"])
        if key in seen:  # One row per commodity code; keep the first.
            continue
        seen.add(key)
        is_corp = corporate_name(row["company_name"]) or corporate_name(row["dba_name"])
        can, why = rule("US", is_corp, "incorporated business: CAN-SPAM allows business email"
                        if is_corp else "may be an individual: Washington bars marketing to lists of individuals")
        yield record(
            SOURCE, len(seen), row["company_name"], other_name=row["dba_name"],
            kind="supplier", category=row["description_of_work"],
            legal_form="incorporated" if is_corp else "", town=row["city"], region=row["state"],
            country="US", website=row["web_address"], emails=row["contact_email"],
            phones=row["phone_number"],
            can_email=can, rule_reason=why)
