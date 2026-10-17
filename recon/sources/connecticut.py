"""Connecticut Business Registry, Business Master (data.ct.gov, public domain).

About 464,000 active businesses, many with the email they gave the state and
an industry (NAICS) code. Updated daily.
"""

from . import joined, record, rule, socrata

SOURCE = {
    "name": "connecticut-business-registry",
    "title": "Connecticut Business Registry (Business Master)",
    "country": "US",
    "url": "https://data.ct.gov/d/n7gp-d28j",
    "licence": "Public Domain",
    "updated": "daily",
    "fields": "name, legal form, mailing address, email, NAICS industry",
}

# Partnerships and trusts still fall under CAN-SPAM in the US, so every
# Connecticut business may be emailed; the legal form is kept for filtering.
COLUMNS = ("id,name,business_type,status,accountnumber,billingstreet,billing_unit,billingcity,"
           "billingstate,billingpostalcode,business_email_address,naics_code,naics_sub_code")


def rows(cache):
    for row in socrata("data.ct.gov", "n7gp-d28j", cache, select=COLUMNS, where="status='Active'"):
        can, why = rule("US", None, "US business: CAN-SPAM allows business email with an opt-out")
        kind = "non-profit" if row["business_type"] in ("Non-Stock", "Religious", "Cemetery") else "company"
        yield record(
            SOURCE, row["accountnumber"] or row["id"], row["name"],
            kind=kind, category=row["naics_sub_code"] or row["naics_code"],
            legal_form=row["business_type"], status=row["status"],
            address=joined(row["billingstreet"], row["billing_unit"]), town=row["billingcity"],
            region=row["billingstate"], postcode=row["billingpostalcode"], country="US",
            emails=row["business_email_address"], registration_number=row["accountnumber"],
            can_email=can, rule_reason=why)
