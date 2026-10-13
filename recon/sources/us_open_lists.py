"""Smaller US lists from state and city open-data portals (Socrata) that
publish an email for each business or organisation.

One module holds several sources, so it exposes SOURCES: a list of namespaces,
each with its own SOURCE description and rows(cache) generator, exactly like a
single-source loader module.

Email rules: US businesses may be emailed under CAN-SPAM with an opt-out.
Washington state agencies (including the City of Seattle) publish under
RCW 42.56.070(8), which bars using lists of individuals for commercial
purposes, so anyone there who is not plainly incorporated is post only.
Only active or current rows are kept where a list says which rows are current.
"""

import re
from datetime import date, timedelta
from types import SimpleNamespace

from . import corporate_name, joined, record, rule, socrata

CAN_SPAM = "US business: CAN-SPAM allows business email with an opt-out"
PERSON_OK = "may be a person or home business; no state bar on business email, CAN-SPAM applies"
WA_CORP = "incorporated business: CAN-SPAM allows business email"
WA_PERSON = "may be an individual: Washington bars marketing to lists of individuals (RCW 42.56.070(8))"

NYC_TERMS = "NYC Open Data terms of use (free to use, including commercially)"
NY_TERMS = "Open NY terms of use (free to use, including commercially)"
WA_TERMS = "Washington open data; no commercial use of lists of individuals (RCW 42.56.070(8))"


def _zip(value):
    """A five-digit ZIP from '77075 5065', '662110000' or '7849'."""
    digits = re.sub(r"\D", "", value or "")
    if len(digits) in (5, 9):
        return digits[:5]
    if len(digits) == 4:  # New England ZIPs that lost their leading nought.
        return "0" + digits
    return value or ""


# '32747 Fernwood Lane, Laurel, DE 19956 US', '1200 Abernathy Road,Atlanta,GA 30328',
# '8728 209th pl sw, Edmonds, 98026' or 'PO Box 39145, Seattle, WA'
_ONE_LINE = re.compile(
    r"^(?P<street>.+?)\s*,\s*(?P<town>[^,]+?)\s*,?\s*(?:\b(?P<state>[A-Za-z]{2})\.?)?\s*"
    r"(?P<zip>\d{5}(?:-\d{4})?)?(?:\s+USA?)?\s*$")


def _split(text):
    """(street, town, state, zip) from a one-line address, best effort."""
    text = " ".join((text or "").split())
    match = _ONE_LINE.match(text)
    if match and (match["state"] or match["zip"]):
        return (match["street"], match["town"], (match["state"] or "").upper(),
                match["zip"] or "")
    return text, "", "", ""


def _unique(*items):
    """Non-empty items once each, in order, ignoring case and spacing."""
    found, keys = [], set()
    for item in items:
        item = " ".join((item or "").split())
        if item and item.lower() not in keys:
            keys.add(item.lower())
            found.append(item)
    return found


def _blank(value):
    """Registers write 'NA' or 'None' for an empty box."""
    return "" if (value or "").strip().upper() in ("NA", "N/A", "NONE", "-") else value


def _wa_rule(*names):
    is_corp = any(corporate_name(n) for n in names)
    return rule("US", is_corp, WA_CORP if is_corp else WA_PERSON), is_corp


def _source(name, title, url, licence, updated, fields):
    source = {"name": name, "title": title, "country": "US", "url": url,
              "licence": licence, "updated": updated, "fields": fields}
    return source


# ---- NYC Department of Buildings licences ------------------------------------

NYC_DOB = _source(
    "nyc-dob-licences", "NYC Department of Buildings licence holders",
    "https://data.cityofnewyork.us/d/t8hj-ruu2", NYC_TERMS, "daily",
    "licence type and number, holder, business name, address, email, phone")

# Licence types held by firms rather than by one person.
_FIRM_LICENCES = ("GENERAL CONTRACTOR", "ELECTRICAL FIRM", "ELECTRICAL CONTRACTOR",
                  "FIRE SUPPRESSION CONTRACTOR", "SPECIAL INSPECTION AGENCY",
                  "ELEVATOR AGENCY / INSPECTOR", "CONCRETE TEST LAB / SAFETY MANAGER")


def nyc_dob_rows(cache):
    for row in socrata("data.cityofnewyork.us", "t8hj-ruu2", cache, where="license_status='ACTIVE'"):
        person = joined(row["first_name"], row["last_name"], sep=" ").title()
        name = _blank(row["business_name"]) or person
        corp = corporate_name(name)
        can, why = rule("US", corp or None, CAN_SPAM if corp else PERSON_OK)
        kind = "contractor" if row["license_type"] in _FIRM_LICENCES or name != person else "tradesperson"
        yield record(
            NYC_DOB, row["license_sl_no"], name, kind=kind,
            category=row["license_type"].title(), status="Active",
            address=joined(row["business_house_number"], row["business_street_name"], sep=" "),
            # Some towns are cut to two letters ('BR', 'NE'); those are dropped.
            town=row["license_business_city"] if len(row["license_business_city"]) > 2 else "",
            region=row["business_state"],
            postcode=row["business_zip_code"], country="US", emails=row["business_email"],
            phones=row["business_phone_number"], people=person,
            registration_number=f"{row['license_type'].title()} {row['license_number']}",
            can_email=can, rule_reason=why)


# ---- USAC E-Rate service providers ------------------------------------------

ERATE = _source(
    "usac-erate-providers", "USAC E-Rate service providers (schools and libraries)",
    "https://datahub.usac.org/d/xcy2-bdid", "USAC Open Data (public, no restrictions stated)",
    "daily", "name, trading name, SPIN, FCC number, contacts, emails, phone, addresses")


def erate_rows(cache):
    for row in socrata("datahub.usac.org", "xcy2-bdid", cache, where="status='Active'"):
        can, why = rule("US", None, CAN_SPAM)
        dba = row["doing_business_as_dba_"]
        yield record(
            ERATE, row["spin"], row["service_provider_name"],
            other_name="" if dba.lower() == row["service_provider_name"].lower() else dba,
            kind="telecom provider", category="E-Rate telecoms and internet supplier to schools and libraries",
            status="Active",
            address=joined(row["physical_address_1"], row["physical_address_2"]) or
            joined(row["mailing_address_1"], row["mailing_address_2"]),
            town=row["physical_city"] or row["mailing_city"],
            region=row["physical_state"] or row["mailing_state"],
            postcode=row["physical_zip_code"] or row["mailing_zip_code"], country="US",
            emails=joined(row["general_contact_email"], row["account_administrator_email"], sep="; "),
            phones=row["phone_number"],
            people=_unique(row["general_contact_name"], row["account_administrator_name"]),
            registration_number=f"SPIN {row['spin']}", can_email=can, rule_reason=why)


# ---- Texas HHSC child care operations ---------------------------------------

TEXAS_CCL = _source(
    "texas-hhsc-childcare", "Texas HHSC child care and residential operations",
    "https://data.texas.gov/d/bc5r-88dy", "Creative Commons 1.0 Universal (public domain)",
    "daily", "name, type, address, phone, email, website, director, capacity")

_TEXAS_KIND = {"General Residential Operation": "children's home",
               "Child Placing Agency": "foster care agency"}


def texas_ccl_rows(cache):
    for row in socrata("data.texas.gov", "bc5r-88dy", cache, where="operation_status='Y'"):
        name = row["operation_name"]
        corp = corporate_name(name)
        home = "Home" in row["operation_type"]
        can, why = rule("US", corp or None, PERSON_OK if home and not corp else CAN_SPAM)
        yield record(
            TEXAS_CCL, row["operation_id"], name,
            kind=_TEXAS_KIND.get(row["operation_type"], "childcare"),
            category=row["operation_type"], status="Open",
            address=row["address_line"], town=row["city"].title(), region=row["state"],
            postcode=_zip(row["zipcode"]), country="US", website=row["website_address"],
            emails=row["email_address"], phones=row["phone_number"],
            people=row["administrator_director_name"],
            registration_number=f"Operation {row['operation_number']}",
            can_email=can, rule_reason=why)


# ---- Pennsylvania child care providers --------------------------------------

PA_CHILDCARE = _source(
    "pa-childcare-providers", "Pennsylvania child care providers (current)",
    "https://data.pa.gov/d/ajn5-kaxt", "Public Domain U.S. Government", "monthly",
    "facility and legal entity name, type, address, phone, email, responsible person, licence")


def pa_childcare_rows(cache):
    for row in socrata("data.pa.gov", "ajn5-kaxt", cache):
        name, legal = row["facility_name"], row["legal_entity_name"]
        corp = corporate_name(name) or corporate_name(legal)
        home = "Home" in row["provider_type"]
        can, why = rule("US", corp or None, PERSON_OK if home and not corp else CAN_SPAM)
        person = joined(row["responsible_person_first"], row["responsible_person_last_name"], sep=" ").title()
        if person and row["responsible_person_title"]:
            person += f" ({row['responsible_person_title']})"
        yield record(
            PA_CHILDCARE, row["master_provider_index"] or row["mpi_id"], name,
            other_name="" if legal == name else legal, kind="childcare",
            category=row["provider_type"], status="Current",
            address=joined(row["facility_address"], row["facility_address_continued"]),
            town=row["facility_city"].title(), region="PA", postcode=row["facility_zip_code"],
            country="US", emails=row["facility_email"], phones=row["facility_phone"],
            people=person, registration_number=row["license_number"],
            can_email=can, rule_reason=why)


# ---- New York State DBE directory -------------------------------------------

NY_DBE = _source(
    "nys-dbe-directory", "New York State certified Disadvantaged Business Enterprises",
    "https://data.ny.gov/d/pfeu-dsx6", NY_TERMS, "2016 snapshot",
    "name, work done, address, county, phone, email, NAICS codes")


def ny_dbe_rows(cache):
    for count, row in enumerate(socrata("data.ny.gov", "pfeu-dsx6", cache), 1):
        can, why = rule("US", None, CAN_SPAM)
        yield record(
            NY_DBE, count, row["company_name"], kind="supplier",
            category=row["business_description"], address=row["street_address"],
            town=row["city"].title(), region=row["state"], country="US",
            emails=row["email"], phones=row["phone"], can_email=can, rule_reason=why)


# ---- Supplier diversity directories -----------------------------------------

AUSTIN_SBE = _source(
    "austin-sbe-firms", "City of Austin certified Small Business Enterprises",
    "https://data.austintexas.gov/d/uxwx-55kj", "City of Austin open data terms (public)",
    "as certifications change", "name, trading name, contact, email, phone, address")


def austin_rows(cache):
    seen = set()
    for row in socrata("data.austintexas.gov", "uxwx-55kj", cache):
        if row["vendor_code"] in seen:  # A firm can appear twice; keep the first.
            continue
        seen.add(row["vendor_code"])
        can, why = rule("US", None, CAN_SPAM)
        yield record(
            AUSTIN_SBE, row["vendor_code"], row["legal_name"], other_name=row["alias"],
            kind="supplier", category="Small Business Enterprise (City of Austin)",
            status="Certified", address=joined(row["street_1"], row["street_2"]),
            town=row["city"].title(), region=row["state"], postcode=row["zip"], country="US",
            emails=row["email"], phones=row["phone"], people=row["principle_contact"].title(),
            registration_number=row["vendor_code"], can_email=can, rule_reason=why)


NOLA_DBE = _source(
    "new-orleans-dbe", "New Orleans certified Disadvantaged Business Enterprises",
    "https://data.nola.gov/d/q42h-ptn2", "Creative Commons 1.0 Universal (public domain)",
    "2019 snapshot", "name, trading name, owner, address, phone, email, website, capability")


def nola_rows(cache):
    for count, row in enumerate(socrata("data.nola.gov", "q42h-ptn2", cache), 1):
        can, why = rule("US", None, CAN_SPAM)
        yield record(
            NOLA_DBE, count, row["company_name"], other_name=row["dba_name"], kind="supplier",
            category=row["capability"] or row["service_type"],
            legal_form=row["certification_type"],
            address=row["physical_address"] or row["mailing_address"], region="LA", country="US",
            website=row["website"], emails=row["email"], phones=row["phone"],
            people=joined(row["owner_first"], row["owner_last"], sep=" "),
            can_email=can, rule_reason=why)


CAMBRIDGE = _source(
    "cambridge-business-diversity", "Cambridge (MA) Business Diversity Directory",
    "https://data.cambridgema.gov/d/2b3j-9kdn",
    "Open Data Commons Public Domain Dedication and License", "as businesses join",
    "name, category, description, address, phone, email, website, ownership")


def cambridge_rows(cache):
    for count, row in enumerate(socrata("data.cambridgema.gov", "2b3j-9kdn", cache), 1):
        sole = "Sole proprietor" in row["business_type"]
        can, why = rule("US", None, PERSON_OK if sole else CAN_SPAM)
        yield record(
            CAMBRIDGE, count, row["name"],
            kind="non-profit" if row["nonprofit_status"].lower().startswith("non") else "local business",
            category=joined(row["category"], row["description"], sep=": "),
            legal_form="Sole proprietor" if sole else "", address=row["street_address"],
            town="Cambridge", region="MA", country="US", website=row["website"],
            emails=row["email"], phones=row["phone"], can_email=can, rule_reason=why)


GAINESVILLE = _source(
    "gainesville-businesses", "City of Gainesville (FL) business tax receipts",
    "https://data.cityofgainesville.org/d/hk2b-em59", "Public Domain", "2023 snapshot",
    "name, business type, owner, address, phone, email")


def gainesville_rows(cache):
    where = "statusid='Active' AND business_type != 'REFERENCE OUT OF BUSINESS'"
    for row in socrata("data.cityofgainesville.org", "hk2b-em59", cache, where=where):
        owner = " ".join(row["owner"].split())
        if corporate_name(owner) or owner.rstrip(".").lower() == row["name"].rstrip(".").lower():
            owner = ""  # Owned by the business itself, not a named person.
        same_place = row["mailing_address"] == row["physical_address"]
        can, why = rule("US", None, CAN_SPAM)
        yield record(
            GAINESVILLE, row["id"], row["name"], kind="local business",
            category=row["business_type"].capitalize(), status="Active",
            address=row["physical_address"], town=row["physical_city"].title(),
            region=row["physical_state"], postcode=row["mailing_zip_code"] if same_place else "",
            country="US", emails=row["email"], phones=row["business_phone"], people=owner,
            can_email=can, rule_reason=why)


VERMONT_CHILDCARE = _source(
    "vermont-childcare-providers", "Vermont child care providers",
    "https://data.vermont.gov/d/ctdw-tmfz",
    "Open Database License (commercial use allowed; credit the source, share-alike)",
    "monthly", "name, programme type, licence, address, phone, email, capacity")


def vermont_rows(cache):
    for row in socrata("data.vermont.gov", "ctdw-tmfz", cache):
        name = row["provider_name"]
        corp = corporate_name(name)
        home = "FCCH" in row["provider_program_type"]
        can, why = rule("US", corp or None, PERSON_OK if home and not corp else CAN_SPAM)
        yield record(
            VERMONT_CHILDCARE, row["provider_id"], name, kind="childcare",
            category=row["provider_program_type"].replace("CBCCPP", "Child care centre")
            .replace("FCCH", "family child care home"),
            legal_form=row["license_type"], status=row["provider_referral_status"],
            address=joined(row["address_1"], row["address_2"]), town=row["provider_town"],
            region="VT", postcode=_zip(row["zip_code"]), country="US",
            emails=row["email_address"], phones=row["phone_number"],
            registration_number=f"Licence {row['license_id']}", can_email=can, rule_reason=why)


WA_CHILDCARE = _source(
    "wa-dcyf-childcare-centres", "Washington DCYF licensed child care centres and school-age programmes",
    "https://data.wa.gov/d/was8-3ni8", WA_TERMS, "weekly",
    "name, trading name, type, address, contact, phone, email, capacity")


def wa_childcare_rows(cache):
    where = "latestoperatingstatus='Active'"
    seen = set()
    for row in socrata("data.wa.gov", "was8-3ni8", cache, where=where):
        key = row["famlinkid"] or row["wacompassid"]
        if key in seen:  # A few providers are listed twice; keep the first.
            continue
        seen.add(key)
        (can, why), corp = _wa_rule(row["providername"], row["doingbusinessas"])
        yield record(
            WA_CHILDCARE, key, row["providername"],
            other_name=row["doingbusinessas"] if row["doingbusinessas"] != row["providername"] else "",
            kind="childcare", category=row["facilitytypegeneric"].capitalize(),
            legal_form="incorporated" if corp else "", status="Active",
            address=row["physicalstreetaddress"], town=row["physicalcity"].title(),
            region=row["physicalstate"], postcode=row["physicalzip"], country="US",
            emails=row["primarycontactemail"], phones=row["primarycontactphonenumber"],
            people=row["primarycontactpersonname"].title(),
            registration_number=f"FamLink {row['famlinkid']}" if row["famlinkid"] else "",
            can_email=can, rule_reason=why)


# ---- Found through the Socrata catalogue ------------------------------------

def _delaware_osd(source, dataset):
    def rows(cache):
        for row in socrata("data.delaware.gov", dataset, cache):
            can, why = rule("US", None, CAN_SPAM)
            description = " ".join(row["description"].split())
            yield record(
                source, row["certificatenumber"], row["name"], kind="supplier",
                category=description[:200], status="Certified", address=row["address"],
                town=row["city"], region=row["state"], postcode=_zip(row["zipcode"]),
                country="US", emails=row["email"], phones=row["phonenumber"],
                people=row["primarycontactname"], registration_number=row["certificatenumber"],
                can_email=can, rule_reason=why)
    return rows


DE_DIVERSITY = _source(
    "delaware-supplier-diversity", "Delaware Office of Supplier Diversity certified firms",
    "https://data.delaware.gov/d/8dxf-6ahp", "Public Domain", "daily",
    "name, certificate, contact, address, phone, email, description, NAICS codes")

DE_SMALL = _source(
    "delaware-small-business-focus", "Delaware Small Business Focus certified firms",
    "https://data.delaware.gov/d/gexk-vfam", "Public Domain", "daily",
    "name, certificate, contact, address, phone, email, description, NAICS codes")


def _nyc_bic(source, dataset, kind, category):
    """NYC Business Integrity Commission lists are daily snapshots appended to
    one table, so take only the last fortnight's snapshots and one row per
    BIC number, skipping anything already expired."""
    def rows(cache):
        today = date.today()
        since = (today - timedelta(days=14)).isoformat()
        where = f"created >= '{since}' AND expiration_date >= '{today.isoformat()}'"
        seen = set()
        for row in socrata("data.cityofnewyork.us", dataset, cache, where=where):
            if row["bic_number"] in seen:
                continue
            seen.add(row["bic_number"])
            can, why = rule("US", None, CAN_SPAM)
            yield record(
                source, row["bic_number"], row["account_name"], other_name=row["trade_name"],
                kind=kind, category=category, status="Licensed", address=row["address"],
                town=row["city"].title(), region=row["state"], postcode=row["postcode"],
                country="US", emails=row["email"], phones=row["phone"],
                registration_number=row["bic_number"], can_email=can, rule_reason=why)
    return rows


NYC_HAULERS = _source(
    "nyc-trade-waste-haulers", "NYC Business Integrity Commission trade waste hauler licensees",
    "https://data.cityofnewyork.us/d/867j-5pgi", NYC_TERMS, "daily",
    "name, trading name, address, phone, email, licence dates")

NYC_SELF_HAULERS = _source(
    "nyc-self-haulers", "NYC Business Integrity Commission self-hauler registrants",
    "https://data.cityofnewyork.us/d/a8wp-rerh", NYC_TERMS, "daily",
    "name, trading name, address, phone, email, registration dates")


SEATTLE_TREES = _source(
    "seattle-tree-services", "Seattle registered tree service providers",
    "https://data.seattle.gov/d/uy6s-ine5",
    "Public Domain; Washington bars commercial use of lists of individuals (RCW 42.56.070(8))",
    "daily", "name, address, services, website, email, phone, registration")


def seattle_rows(cache):
    for row in socrata("cos-data.seattle.gov", "uy6s-ine5", cache, where="status='Active'"):
        (can, why), corp = _wa_rule(row["business_name"])
        street, town, state, zipcode = _split(row["company_address"])
        yield record(
            SEATTLE_TREES, row["assigned_tsp_number"], row["business_name"], kind="tree surgeon",
            category=row["tree_services_provided"], legal_form="incorporated" if corp else "",
            status="Active", address=street, town=town.title(), region=state or "WA",
            postcode=zipcode, country="US", website=row["website"], emails=row["email_address"],
            phones=row["phone_number"], registration_number=row["assigned_tsp_number"],
            can_email=can, rule_reason=why)


NYC_VETERANS = _source(
    "nyc-veteran-businesses", "NYC Department of Veterans' Services veteran-owned businesses",
    "https://data.cityofnewyork.us/d/ybdk-jmnn", NYC_TERMS, "2022 snapshot",
    "name, service, address, phone, email, website, certifications")


def nyc_veterans_rows(cache):
    for row in socrata("data.cityofnewyork.us", "ybdk-jmnn", cache):
        can, why = rule("US", None, CAN_SPAM)
        yield record(
            NYC_VETERANS, row["dvs_res_id"], row["name"], kind="veteran-owned business",
            category=joined(row["service"], row["service_details"], sep=": "),
            legal_form=row["certifications"], address=row["address"], town=row["city"],
            region=row["state"], postcode=row["zip"], country="US", website=row["website"],
            emails=row["email_address"], phones=row["phone_number"],
            can_email=can, rule_reason=why)


TXDOT = _source(
    "txdot-prequalified-contractors", "TxDOT prequalified contractor vendor list",
    "https://data.texas.gov/d/dw25-6md2", "Texas Open Data Portal terms (public)", "daily",
    "name, prequalification status, addresses, phone, email")

_TXDOT_STATUS = {"CQ": "Prequalified (financial statement)", "BQ": "Prequalified (bidder's questionnaire)",
                 "MQ": "Prequalified (maintenance)"}


def txdot_rows(cache):
    for row in socrata("data.texas.gov", "dw25-6md2", cache):
        can, why = rule("US", None, CAN_SPAM)
        yield record(
            TXDOT, row["vendor_id"], row["vendor_name"], kind="contractor",
            category="Road and bridge contractor (TxDOT)",
            status=_TXDOT_STATUS.get(row["contractor_qualified_status"], row["contractor_qualified_status"]),
            address=joined(row["physical_address_line_1"], row["physical_address_line_2"]) or
            joined(row["mailing_address_line_1"], row["mailing_address_line_2"]),
            town=(row["physical_address_city"] or row["mailing_city"]).title(),
            region=row["physical_address_state"] or row["mailing_state"],
            postcode=_zip(row["physical_address_zip_code"] or row["mailing_zip_code"]),
            country="US", emails=row["email"], phones=row["phone"],
            registration_number=f"TxDOT vendor {row['vendor_id']}", can_email=can, rule_reason=why)


DE_SEPTIC = _source(
    "delaware-septic-licensees", "Delaware on-site wastewater (septic) system licensees",
    "https://data.delaware.gov/d/56uc-mvju", "Public Domain", "daily",
    "licence holder, company, licence class, address, phone, mobile, email")


def de_septic_rows(cache):
    for row in socrata("data.delaware.gov", "56uc-mvju", cache, where="licstatus='Approved'"):
        name = row["companyname"] or row["displayname"]
        corp = corporate_name(name)
        can, why = rule("US", corp or None, CAN_SPAM if corp else PERSON_OK)
        street, town, state, zipcode = _split(row["companyaddress"])
        yield record(
            DE_SEPTIC, row["licensenumber"], name, kind="contractor",
            category=f"Septic systems: {row['licensesubtype']}", status="Licensed",
            address=street, town=town, region=state, postcode=zipcode, country="US",
            emails=row["companyemailaddress"],
            phones=joined(row["companyphone"], row["cellphone"], sep="; "),
            people=" ".join(row["displayname"].split()),
            registration_number=f"Licence {row['licensenumber']}", can_email=can, rule_reason=why)


DE_WELLS = _source(
    "delaware-well-contractors", "Delaware water well and pump installer contractors",
    "https://data.delaware.gov/d/2dnk-irgr", "Delaware open data (public)", "daily",
    "company, licence type, address, phone, email")


def de_wells_rows(cache):
    for row in socrata("data.delaware.gov", "2dnk-irgr", cache, where="licstatus='Approved'"):
        can, why = rule("US", None, CAN_SPAM)
        street, town, state, zipcode = _split(row["workaddress"])
        yield record(
            DE_WELLS, row["licensenumber"], row["orgname"], kind="contractor",
            category=row["licensesubtype"], status="Licensed", address=street, town=town,
            region=state, postcode=zipcode, country="US", emails=row["emailaddress"],
            phones=row["workphone"], registration_number=f"Licence {row['licensenumber']}",
            can_email=can, rule_reason=why)


FCC_IPR = _source(
    "fcc-intermediate-providers", "FCC Intermediate Provider Registry (voice carriers)",
    "https://opendata.fcc.gov/d/a6ec-cry4", "US federal open data (public domain)", "daily",
    "name, address, states served, regulatory and call-completion contacts with email and phone")


def fcc_rows(cache):
    for count, row in enumerate(socrata("opendata.fcc.gov", "a6ec-cry4", cache), 1):
        can, why = rule("US", None, CAN_SPAM)
        street, town, state, zipcode = _split(row["business_address"])
        people, names = [], set()
        for prefix in ("regulatory_contact", "rural_call_completion_contact"):
            person = " ".join(row[f"{prefix}_name"].split())
            if not person or person.lower() in names:
                continue
            names.add(person.lower())
            title = row[f"{prefix}_title"].strip()
            people.append(f"{person} ({title})" if title else person)
        previous = row["previous_business_names"]
        yield record(
            FCC_IPR, count, row["business_name"],
            other_name="" if previous.lower() in ("", "none", "n/a", "na") else previous,
            kind="telecom provider", category=f"Intermediate voice provider; serves {row['states_serviced']}"[:200],
            address=street, town=town, region=state, postcode=zipcode, country="US",
            emails=joined(row["regulatory_contact_email"], row["rural_call_completion_contact_email"], sep="; "),
            phones=joined(row["regulatory_contact_telephone"],
                          row["rural_call_completion_contact_telephone"], sep="; "),
            people=people, can_email=can, rule_reason=why)


NYSERDA_WIND = _source(
    "nyserda-offshore-wind-suppliers", "NYSERDA offshore wind supply chain database (US firms)",
    "https://data.ny.gov/d/tb54-h6gg", NY_TERMS, "monthly",
    "name, type, services, address, contact, email, phone, website, MWBE status")


def nyserda_rows(cache):
    where = "country in ('USA', 'United States')"
    for count, row in enumerate(socrata("data.ny.gov", "tb54-h6gg", cache, where=where), 1):
        can, why = rule("US", None, CAN_SPAM)
        main = row["organization_type_main"]
        yield record(
            NYSERDA_WIND, count, row["organization_name"],
            kind="trade union" if main == "Labor Organizations" else "supplier",
            category=joined(main, row["organization_type_sub"], sep=": ")[:200],
            legal_form="MWBE certified" if row["certified_mwbe"] == "Yes" else "",
            address=joined(row["street_address_1"], row["street_address_2"]),
            town=row["city"], region=row["state_or_province"], postcode=_zip(row["postal_code"]),
            country="US", website=row["website"], emails=row["email"], phones=row["phone_1"],
            people=joined(row["contact_first_name"], row["contact_last_name"], sep=" "),
            can_email=can, rule_reason=why)


SOURCES = [SimpleNamespace(SOURCE=source, rows=rows) for source, rows in [
    (NYC_DOB, nyc_dob_rows),
    (ERATE, erate_rows),
    (TEXAS_CCL, texas_ccl_rows),
    (PA_CHILDCARE, pa_childcare_rows),
    (NY_DBE, ny_dbe_rows),
    (AUSTIN_SBE, austin_rows),
    (NOLA_DBE, nola_rows),
    (CAMBRIDGE, cambridge_rows),
    (GAINESVILLE, gainesville_rows),
    (VERMONT_CHILDCARE, vermont_rows),
    (WA_CHILDCARE, wa_childcare_rows),
    (DE_DIVERSITY, _delaware_osd(DE_DIVERSITY, "8dxf-6ahp")),
    (DE_SMALL, _delaware_osd(DE_SMALL, "gexk-vfam")),
    (NYC_HAULERS, _nyc_bic(NYC_HAULERS, "867j-5pgi", "waste carrier", "Commercial waste collection")),
    (NYC_SELF_HAULERS, _nyc_bic(NYC_SELF_HAULERS, "a8wp-rerh", "business",
                                "Carts its own trade waste (registered self-hauler)")),
    (SEATTLE_TREES, seattle_rows),
    (NYC_VETERANS, nyc_veterans_rows),
    (TXDOT, txdot_rows),
    (DE_SEPTIC, de_septic_rows),
    (DE_WELLS, de_wells_rows),
    (FCC_IPR, fcc_rows),
    (NYSERDA_WIND, nyserda_rows),
]]
