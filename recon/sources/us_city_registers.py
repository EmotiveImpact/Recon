"""US city and state business registers with names and addresses (open data).

Five large registers of businesses that are trading now: Seattle and Los
Angeles business licences, and the Colorado, Oregon and New York State company
registers. They hold almost no phones and no emails; their value is millions of
live business names and addresses for Recon's website finder to look up later.
"""

import types

from . import corporate_name, joined, record, rule, socrata

CAN_SPAM = "US business: CAN-SPAM allows business email with an opt-out"


def _source(name, title, url, licence, updated, fields):
    return {"name": name, "title": title, "country": "US", "url": url,
            "licence": licence, "updated": updated, "fields": fields}


# ---- Seattle -------------------------------------------------------------

SEATTLE = _source(
    "seattle-business-licences", "Seattle active business licence tax certificates",
    "https://data.seattle.gov/d/wnbq-64tb",
    "Public Domain; Washington law (RCW 42.56.070(8)) bars commercial use of lists of individuals",
    "daily", "legal and trading name, ownership type, NAICS industry, address, business phone")

# Ownership types that are plainly not one person trading under their own name.
SEATTLE_CORPORATE = {"Corporation", "LLC - Single Member", "LLC - Multi Member",
                     "Non Profit Corporation", "Professional Association",
                     "Limited Liability Limited Ptrs", "Limited Liability Ptrs LLP",
                     "Limited Partnership", "LLC Limited Liability Co", "Association",
                     "Municipality", "Tribal Government", "Government Agency"}


def seattle_rows(cache):
    for row in socrata("data.seattle.gov", "wnbq-64tb", cache):
        name = row["business_legal_name"]
        corp = row["ownership_type"] in SEATTLE_CORPORATE or corporate_name(name)
        # Washington agencies may not release lists of individuals for
        # commercial use, so sole traders and the like are post only.
        can, why = rule("US", corp, CAN_SPAM if corp else
                        "may be an individual: Washington bars marketing to lists of individuals")
        trade = row["trade_name"] if row["trade_name"].strip().lower() != name.strip().lower() else ""
        yield record(
            SEATTLE, row["city_account_number"] or row["ubi"], name, other_name=trade,
            kind="business", category=row["naics_description"] or row["naics_code"],
            legal_form=row["ownership_type"], status="Active", address=row["street_address"],
            town=row["city"], region=row["state"], postcode=row["zip"], country="US",
            phones=row["business_phone"], registration_number=f"UBI {row['ubi']}" if row["ubi"] else "",
            can_email=can, rule_reason=why)


# ---- Los Angeles ---------------------------------------------------------

LOS_ANGELES = _source(
    "los-angeles-active-businesses", "City of Los Angeles listing of active businesses",
    "https://data.lacity.org/d/6rrh-rzua",
    "Creative Commons 1.0 Universal (Public Domain Dedication)", "monthly",
    "business and trading name, NAICS industry, location and mailing address")


def los_angeles_rows(cache):
    columns = ("location_account,business_name,dba_name,street_address,city,zip_code,"
               "mailing_address,mailing_city,mailing_zip_code,naics,primary_naics_description,"
               "location_start_date,location_end_date")
    for row in socrata("data.lacity.org", "6rrh-rzua", cache, select=columns,
                       where="location_end_date is null"):
        can, why = rule("US", None, CAN_SPAM)
        yield record(
            LOS_ANGELES, row["location_account"], row["business_name"], other_name=row["dba_name"],
            kind="business", category=row["primary_naics_description"] or row["naics"],
            status="Active", address=row["street_address"] or row["mailing_address"],
            town=row["city"] or row["mailing_city"], region="CA",
            postcode=row["zip_code"] or row["mailing_zip_code"], country="US",
            registration_number=row["location_account"], can_email=can, rule_reason=why)


# ---- Colorado ------------------------------------------------------------

COLORADO = _source(
    "colorado-business-entities", "Colorado Secretary of State business entities (good standing)",
    "https://data.colorado.gov/d/4ykn-tg5h", "Public Domain", "daily",
    "name, legal form, principal and mailing address, registered agent")

COLORADO_FORMS = {
    "DLLC": "Limited liability company", "FLLC": "Foreign limited liability company",
    "DPC": "Profit corporation", "FPC": "Foreign profit corporation",
    "DPC-PBC": "Public benefit corporation", "DNC": "Nonprofit corporation",
    "FNC": "Foreign nonprofit corporation", "DLP": "Limited partnership",
    "FLP": "Foreign limited partnership", "DLLP": "Limited liability partnership",
    "FLLP": "Foreign limited liability partnership", "DLLLP": "Limited liability limited partnership",
    "FLLLP": "Foreign limited liability limited partnership", "GP": "General partnership",
    "DC56": "Cooperative", "DC55": "Cooperative", "DC56-PBC": "Cooperative",
    "DC55-PBC": "Cooperative", "FCOOP": "Foreign cooperative",
    "DLCA": "Limited cooperative association", "DLCA-PBC": "Limited cooperative association",
    "FLCA": "Foreign limited cooperative association", "DLPA": "Limited partnership association",
    "FLPA": "Foreign limited partnership association", "UNA": "Unincorporated nonprofit association",
    "CS": "Corporation sole", "CU": "Credit union", "SL": "Savings and loan association",
    "FO": "Foreign other entity", "DT": "Business trust",
}


def colorado_rows(cache):
    columns = ("entityid,entityname,principaladdress1,principaladdress2,principalcity,"
               "principalstate,principalzipcode,principalcountry,mailingaddress1,mailingaddress2,"
               "mailingcity,mailingstate,mailingzipcode,entitystatus,entitytype,agentfirstname,"
               "agentmiddlename,agentlastname,agentorganizationname")
    for row in socrata("data.colorado.gov", "4ykn-tg5h", cache, select=columns,
                       where="entitystatus='Good Standing'"):
        country = row["principalcountry"] if row["principalcountry"] not in ("", "US", "USA") else "US"
        can, why = rule(country, None, CAN_SPAM if country == "US"
                        else "registered outside the US: check local rules")
        agent = joined(row["agentfirstname"], row["agentmiddlename"], row["agentlastname"], sep=" ")
        principal = bool(row["principaladdress1"])
        yield record(
            COLORADO, row["entityid"], row["entityname"],
            kind="non-profit" if row["entitytype"] in ("DNC", "FNC", "UNA") else "business",
            legal_form=COLORADO_FORMS.get(row["entitytype"], row["entitytype"]),
            status=row["entitystatus"],
            address=joined(row["principaladdress1"], row["principaladdress2"]) if principal
            else joined(row["mailingaddress1"], row["mailingaddress2"]),
            town=row["principalcity"] if principal else row["mailingcity"],
            region=row["principalstate"] if principal else row["mailingstate"],
            postcode=row["principalzipcode"] if principal else row["mailingzipcode"],
            country=country, people=agent, registration_number=row["entityid"],
            can_email=can, rule_reason=why)


# ---- Oregon --------------------------------------------------------------

OREGON = _source(
    "oregon-active-businesses", "Oregon Secretary of State active businesses",
    "https://data.oregon.gov/d/tckn-sxa6",
    "No licence named on data.oregon.gov; Oregon public record (no marketing restriction stated)",
    "weekly", "name, legal form, principal place of business, mailing address, authorised representative")


def oregon_rows(cache):
    """The register has one row per name or address linked to a business;
    they are gathered into one record per registry number."""
    columns = ("registry_number,business_name,entity_type,associated_name_type,first_name,"
               "middle_name,last_name,address,address_continued,city,state,zip,jurisdiction,"
               "entity_of_record_name")
    found = {}
    for row in socrata("data.oregon.gov", "tckn-sxa6", cache, select=columns):
        if row["entity_type"] in ("RESERVED NAME", "REGISTERED NAME"):
            continue
        entry = found.setdefault(row["registry_number"], {"row": row, "places": {}, "people": []})
        role = row["associated_name_type"]
        if role in ("PRINCIPAL PLACE OF BUSINESS", "MAILING ADDRESS"):
            entry["places"][role] = row
        elif role == "AUTHORIZED REPRESENTATIVE":
            person = joined(row["first_name"], row["middle_name"], row["last_name"], sep=" ")
            if person and person not in entry["people"]:
                entry["people"].append(person)
    for number, entry in found.items():
        row = entry["row"]
        place = (entry["places"].get("PRINCIPAL PLACE OF BUSINESS")
                 or entry["places"].get("MAILING ADDRESS") or {})
        owner = row["entity_of_record_name"]
        can, why = rule("US", None, CAN_SPAM)
        yield record(
            OREGON, number, row["business_name"],
            other_name=owner if owner and owner != row["business_name"] else "",
            kind="non-profit" if "NONPROFIT" in row["entity_type"] else "business",
            legal_form=row["entity_type"].capitalize(), status="Active",
            address=joined(place.get("address", ""), place.get("address_continued", "")),
            town=place.get("city", ""), region=place.get("state", ""),
            postcode=place.get("zip", ""), country="US", people=entry["people"],
            registration_number=number, can_email=can, rule_reason=why)


# ---- New York State ------------------------------------------------------

NEW_YORK = _source(
    "new-york-active-corporations", "New York State active corporations",
    "https://data.ny.gov/d/n9v6-gdp6",
    "No licence named on data.ny.gov; New York State Department of State public record "
    "(no marketing restriction stated)",
    "monthly", "name, legal form, county, location or service-of-process address, chief executive")


def new_york_rows(cache):
    columns = ("dos_id,current_entity_name,county,jurisdiction,entity_type,dos_process_name,"
               "dos_process_address_1,dos_process_address_2,dos_process_city,dos_process_state,"
               "dos_process_zip,chairman_name,location_name,location_address_1,location_address_2,"
               "location_city,location_state,location_zip")
    for row in socrata("data.ny.gov", "n9v6-gdp6", cache, select=columns):
        # The location address is where the business is; without it, the
        # address for legal papers, which is often the business itself.
        here = "location" if row["location_address_1"] else "dos_process"
        can, why = rule("US", None, CAN_SPAM)
        yield record(
            NEW_YORK, row["dos_id"], row["current_entity_name"],
            kind="non-profit" if "NOT-FOR-PROFIT" in row["entity_type"] else "business",
            legal_form=row["entity_type"].capitalize(), status="Active",
            address=joined(row[f"{here}_address_1"], row[f"{here}_address_2"]),
            town=row[f"{here}_city"], region=row[f"{here}_state"], postcode=row[f"{here}_zip"],
            country="US", people=row["chairman_name"], registration_number=f"DOS {row['dos_id']}",
            can_email=can, rule_reason=why)


SOURCES = [
    types.SimpleNamespace(SOURCE=SEATTLE, rows=seattle_rows),
    types.SimpleNamespace(SOURCE=LOS_ANGELES, rows=los_angeles_rows),
    types.SimpleNamespace(SOURCE=COLORADO, rows=colorado_rows),
    types.SimpleNamespace(SOURCE=OREGON, rows=oregon_rows),
    types.SimpleNamespace(SOURCE=NEW_YORK, rows=new_york_rows),
]
