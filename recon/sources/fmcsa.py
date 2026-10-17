"""US Department of Transportation FMCSA Company Census File (federal open data).

Every registered truck, bus and moving firm. Only active carriers are kept:
about 2 million, most with email, phone and up to two named officers. Monthly.
"""

from . import joined, record, rule, socrata

SOURCE = {
    "name": "fmcsa-company-census",
    "title": "FMCSA Company Census File (US carriers)",
    "country": "US",
    "url": "https://data.transportation.gov/d/az4n-8mr2",
    "licence": "US federal open data (public domain)",
    "updated": "monthly",
    "fields": "legal and trading name, legal form, address, email, phone, mobile, officers, fleet size",
}

COLUMNS = ("dot_number,legal_name,dba_name,business_org_desc,status_code,phy_street,phy_city,"
           "phy_state,phy_zip,phy_country,phone,cell_phone,email_address,company_officer_1,"
           "company_officer_2,carrier_operation,power_units,total_drivers,crgo_passengers,crgo_household")


def category(row):
    if row["crgo_household"] == "X":
        return "removals"
    if row["crgo_passengers"] == "X":
        return "passenger transport"
    return "road haulage"


def rows(cache):
    for row in socrata("datahub.transportation.gov", "az4n-8mr2", cache, select=COLUMNS,
                       where="status_code='A'"):
        country = "US" if row["phy_country"] in ("", "US") else row["phy_country"]
        can, why = rule(country, None, "US business: CAN-SPAM allows business email with an opt-out")
        yield record(
            SOURCE, row["dot_number"], row["legal_name"], other_name=row["dba_name"],
            kind="carrier", category=category(row), legal_form=row["business_org_desc"].title(),
            status="Active", address=row["phy_street"], town=row["phy_city"], region=row["phy_state"],
            postcode=row["phy_zip"], country=country, emails=row["email_address"],
            phones=joined(row["phone"], row["cell_phone"], sep="; "),
            people=joined(row["company_officer_1"], row["company_officer_2"], sep="; "),
            registration_number=f"USDOT {row['dot_number']}", can_email=can, rule_reason=why)
