"""Texas Department of Licensing and Regulation, all licences (data.texas.gov).

About a million licences, most held by individual practitioners (barbers,
cosmetologists, electricians). Only business licences are kept here: salons,
barber shops, electrical and other contractors, fuel retailers and so on, each
with a business name and usually an address and phone. Licences past their
expiry date are dropped. Updated daily.
"""

from datetime import date, datetime

from . import joined, record, rule, socrata

SOURCE = {
    "name": "texas-tdlr-licences",
    "title": "Texas TDLR licences (business licences only)",
    "country": "US",
    "url": "https://data.texas.gov/d/7358-krk7",
    "licence": "No licence named on data.texas.gov; Texas public information published "
               "by TDLR as open data (no marketing restriction stated)",
    "updated": "daily",
    "fields": "business name, owner name, business address, phone, licence type, licence number",
}

# Business licence types, with the kind of business in plain words.
TYPES = {
    "Full Service Establishment": "salon",
    "Mini Establishment": "salon",
    "Mobile Establishment": "mobile salon",
    "Manicurist Establishment": "nail salon",
    "Manicurist/Esthetician Establishment": "nail and beauty salon",
    "Esthetician Establishment": "beauty salon",
    "Eyelash Extension Establishment": "eyelash salon",
    "Hair Weaving  Establishment": "hair weaving salon",
    "Hair Weaving Establishment": "hair weaving salon",
    "Cosmetology Private School": "beauty school",
    "Cosmetology Vocational/High School": "beauty school",
    "Cosmetology Junior College": "beauty school",
    "Barber School": "barber school",
    "Electrical Contractor": "electrical contractor",
    "Electrical Sign Contractor": "electrical sign contractor",
    "Appliance Installation Contractor": "appliance installation contractor",
    "Elevator Contractor": "lift contractor",
    "Water Well Driller/Pump Installer": "water well driller",
    "Used Auto Parts Recycler": "used car parts recycler",
    "Devices": "fuel retailer",
    "Distributor/Wholesaler": "fuel distributor",
    "Supplier": "fuel supplier",
    "Service Company": "fuel pump service company",
    "Professional Employer Organization": "professional employer organisation",
    "Professional Employer Organization (Limited license)": "professional employer organisation",
    "Service Contract Provider": "service contract provider",
    "Licensed Breeder": "dog and cat breeder",
    "Boiler Authorized Inspection Agency": "boiler inspection agency",
    "CS PROMOTER (Business)": "combat sports promoter",
    "CS AMATEUR PROMOTER (Business)": "combat sports promoter",
    "Electrician Apprenticeship Program": "training provider",
    "Cosmetology CE Provider": "training provider",
    "Electrician CE Provider": "training provider",
    "A/C CE Provider": "training provider",
    "Auctioneer CE Provider": "training provider",
    "Tow Operator CE Provider": "training provider",
    "Property Tax Professional CE Provider": "training provider",
    "Property Tax Professional Core Education Provider": "training provider",
    "Property Tax Consultant CE Provider": "training provider",
    "Water Well Driller/Pump Installer CE Provider": "training provider",
    "Elevator Responsible Party CE Provider": "training provider",
    "Registered Accessibility Specialist CE Provider": "training provider",
}

# Barber shops and some salons are listed with no licence type, only a subtype.
SUBTYPES = {
    "BS": "barber shop",
    "Barber Mini Shop": "barber shop",
    "Mini-Dual Shop/Salon": "barber shop and salon",
    "HW": "hair weaving salon",
    "MS": "nail salon",
    "FS": "beauty salon",
    "FM": "nail and beauty salon",
}

COLUMNS = ("license_type,license_number,license_subtype,business_name,business_address_line1,"
           "business_address_line2,business_city_state_zip,business_county,business_telephone,"
           "owner_name,owner_telephone,mailing_address_line1,mailing_address_line2,"
           "mailing_address_city_state_zip,license_expiration_date_mmddccyy")


def _quoted(values):
    return ",".join("'" + v.replace("'", "''") + "'" for v in values)


WHERE = (f"license_type in ({_quoted(TYPES)}) or "
         f"(license_type is null and license_subtype in ({_quoted(SUBTYPES)}))")


def expired(text, today=None):
    try:
        return datetime.strptime(text.strip(), "%m/%d/%Y").date() < (today or date.today())
    except ValueError:
        return False  # No readable date: keep it rather than guess.


def split_town(text):
    """'BRYAN TX 77802-3902' -> ('BRYAN', 'TX', '77802-3902')."""
    parts = (text or "").split()
    if len(parts) >= 3 and len(parts[-2]) == 2 and parts[-1][:5].isdigit():
        return " ".join(parts[:-2]), parts[-2], parts[-1]
    return text or "", "", ""


def rows(cache):
    seen = set()
    for row in socrata("data.texas.gov", "7358-krk7", cache, select=COLUMNS, where=WHERE):
        name = row["business_name"].strip()
        if not name or expired(row["license_expiration_date_mmddccyy"]):
            continue
        kind = TYPES.get(row["license_type"]) or SUBTYPES.get(row["license_subtype"], "business")
        key = (row["license_type"], row["license_subtype"], row["license_number"])
        if key in seen:
            continue
        seen.add(key)
        if row["business_address_line1"]:
            street = joined(row["business_address_line1"], row["business_address_line2"])
            town, region, zipcode = split_town(row["business_city_state_zip"])
        else:  # Fall back to the mailing address.
            street = joined(row["mailing_address_line1"], row["mailing_address_line2"])
            town, region, zipcode = split_town(row["mailing_address_city_state_zip"]
                                               or row["business_city_state_zip"])
        owner = row["owner_name"] if row["owner_name"].strip().lower() != name.lower() else ""
        can, why = rule("US", None, "US business: CAN-SPAM allows business email with an opt-out")
        licence_type = row["license_type"] or row["license_subtype"]
        yield record(
            SOURCE, "-".join(p for p in key if p), name, kind=kind,
            category=licence_type.replace("  ", " "), status="Licensed",
            address=street, town=town, region=region or "TX", postcode=zipcode, country="US",
            phones=joined(row["business_telephone"], row["owner_telephone"], sep="; "),
            people=owner, registration_number=f"TDLR {row['license_number']}",
            can_email=can, rule_reason=why)
