"""UK non-profits from Find that Charity, beyond the Charity Commission list.

Find that Charity (https://findthatcharity.uk, run by Kane Data Ltd) joins up
the UK's open registers of non-profit organisations. It publishes one CSV per
source register and per organisation type. Recon already loads the Charity
Commission for England and Wales directly, so this module takes only the
other registers:

- community interest companies (Companies House, through Find that Charity)
- co-operatives, community benefit societies, working men's clubs, credit
  unions and the rest of the FCA Mutuals Public Register (read straight from
  the FCA's own CSV, which has the registered address that Find that
  Charity's export leaves out)
- Northern Ireland charities (Charity Commission for Northern Ireland)
- universities and colleges known to HESA
- community amateur sports clubs (HMRC)
- Church of England churches

Left out on purpose: the Scottish charity regulator OSCR, whose register
terms forbid using it for direct marketing, and the England and Wales
charities already loaded by charity_commission.py.

Find that Charity's exports carry names, register numbers and, for some, a
website; few carry an address or postcode. Each row keeps the licence of the
register it came from. Find that Charity itself asks only that the original
registers be credited; its code is MIT licensed.
"""

import ast
import os
import types

from . import corporate_name, download, joined, read_csv, record, rule, text

SITE = "https://findthatcharity.uk"
OGL3 = "Open Government Licence v3.0"
CCBY4 = "Creative Commons Attribution 4.0"


def _source(name, title, url, licence, fields, updated="daily"):
    return {"name": name, "title": title, "country": "GB", "url": url,
            "licence": licence, "updated": updated, "fields": fields}


def _list(value):
    """Find that Charity writes lists as Python literals: "['a', 'b']"."""
    try:
        found = ast.literal_eval(value or "[]")
    except (ValueError, SyntaxError):
        return []
    return [str(v) for v in found] if isinstance(found, (list, tuple)) else []


def _company_number(row):
    if row.get("companyNumber", "").strip():
        return row["companyNumber"].strip()
    for org in _list(row.get("linked_orgs")):
        if org.startswith("GB-COH-"):
            return org[len("GB-COH-"):]
    return ""


def _export(cache, path):
    """Rows of one Find that Charity CSV export, active organisations only."""
    local = os.path.join(cache, path.strip("/").replace("/", "-"))
    download(SITE + path, local)
    for row in read_csv(local):
        if row.get("active") == "True" and not row.get("dateRemoved"):
            yield row


def _ftc_record(source, row, kind, legal_form, is_corp, why, **extra):
    can, why = rule("GB", is_corp, why)
    company = _company_number(row)
    return record(
        source, row["id"], row["name"], kind=kind,
        category=row.get("organisationTypePrimary", ""), legal_form=legal_form, status="active",
        postcode=row.get("postalCode", ""), country="GB", website=row.get("url", ""),
        registration_number=joined(row.get("charityNumber", ""),
                                   f"company {company}" if company else "", sep="; "),
        company_number=company or "",
        source_url=f"{SITE}/orgid/{row['id']}", can_email=can, rule_reason=why, **extra)


# ---- community interest companies ----------------------------------------

CIC = _source("ftc-community-interest-companies",
              "Community interest companies (Companies House, via Find that Charity)",
              SITE + "/orgid/type/community-interest-company", OGL3,
              "name, company number, date registered")


def cic_rows(cache):
    for row in _export(cache, "/orgid/type/community-interest-company.csv"):
        yield _ftc_record(CIC, row, "community interest company", "Community Interest Company",
                          True, "community interest company: a limited company under PECR")


# ---- FCA mutuals register --------------------------------------------------

MUTUALS = _source("fca-mutuals", "FCA Mutuals Public Register (co-operatives and societies)",
                  "https://mutuals.fca.org.uk/", OGL3,
                  "name, society type, registered address, industry, co-operative type")
MUTUALS_CSV = "https://fcastoragemprprod.blob.core.windows.net/societylist/SocietyList.csv"

MUTUAL_KINDS = {
    "Co-operative Society": "co-operative",
    "Community Benefit Society": "community benefit society",
    "Working Men's Club": "working men's club",
    "Credit Union": "credit union",
    "Building Society": "building society",
    "Friendly Society": "friendly society",
    "Benevolent Society": "benevolent society",
}

# Societies under these Acts are incorporated (corporate bodies). Friendly
# societies, working men's clubs and benevolent societies registered under
# the Friendly Societies Act 1974 are not: their property is held by trustees.
INCORPORATED_ACTS = ("Co-operative and Community Benefit Societies Act", "Credit Unions",
                     "Building Societies Act", "Friendly Societies Act 1992")


def mutual_kind(row):
    registered_as = row["Registered As"]
    if registered_as == "Registered Society":
        condition = row["Statistics Condition"].lower()
        if "co-op" in condition:
            return "co-operative"
        if "community benefit" in condition:
            return "community benefit society"
        return "registered society"
    return MUTUAL_KINDS.get(registered_as, registered_as.lower() or "society")


def mutual_rows(cache):
    path = download(MUTUALS_CSV, os.path.join(cache, "SocietyList.csv"))
    for row in read_csv(path):
        if row["Society Status"] != "Registered" or row["Deregistration Date"]:
            continue
        act = row["Registration Act"]
        is_corp = any(act.startswith(a) for a in INCORPORATED_ACTS)
        why = (f"registered under the {act}: an incorporated society, a corporate body under PECR"
               if is_corp else f"registered under the {act}: an unincorporated society, post only")
        can, why = rule("GB", is_corp, why)
        address = row["Society Address"]
        postcode = text.postcode(address, "GB")
        lines = [p.strip() for p in address.split(",") if p.strip()]
        if postcode and lines and lines[-1].replace(" ", "").upper() == postcode.replace(" ", ""):
            lines = lines[:-1]
        town = lines[-1] if len(lines) > 1 else ""
        yield record(
            MUTUALS, row["Full Registation Number"], row["Society Name"], kind=mutual_kind(row),
            category=joined(row["Reporting Classification"],
                            row["Standard Industrial Classification Code (SIC)"], sep="; "),
            legal_form=joined(row["Registered As"], act, sep=": "), status=row["Society Status"],
            address=joined(*(lines[:-1] if town else lines)), town=town.title() if town.isupper() else town,
            postcode=postcode, country="GB",
            registration_number=f"FCA {row['Full Registation Number']}",
            source_url=f"https://mutuals.fca.org.uk/Search/Society/{row['Society Number']}",
            can_email=can, rule_reason=why)


# ---- Northern Ireland charities -----------------------------------------------

CCNI = _source("ftc-ccni", "Charity Commission for Northern Ireland register (via Find that Charity)",
               "https://www.charitycommissionni.org.uk/charity-search/", OGL3,
               "name, charity number, company number, website, income")


def ccni_rows(cache):
    for row in _export(cache, "/orgid/source/ccni.csv"):
        is_corp = bool(_company_number(row)) or corporate_name(row["name"])
        yield _ftc_record(CCNI, row, "charity", "NI charitable company" if is_corp else "NI charity",
                          is_corp, "charitable company: a corporate body under PECR" if is_corp
                          else "charity not shown to be a company: post only")


# ---- universities and colleges (HESA) ------------------------------------------

HESA = _source("ftc-hesa", "HESA higher education providers (via Find that Charity)",
               "https://www.hesa.ac.uk/collection/provider-tools/all_hesa_providers", CCBY4,
               "name, UKPRN")


def hesa_rows(cache):
    for row in _export(cache, "/orgid/source/hesa.csv"):
        ukprn = next((o[len("GB-UKPRN-"):] for o in _list(row["orgIDs"]) if o.startswith("GB-UKPRN-")), "")
        kinds = _list(row["organisationType"])
        yield _ftc_record(
            HESA, row, "university" if "university" in kinds else "higher education provider",
            "Higher education institution", True,
            "university or college: a chartered or statutory corporation",
            other_name=f"UKPRN {ukprn}" if ukprn else "")


# ---- community amateur sports clubs (HMRC) ----------------------------------------

CASC = _source("ftc-casc", "Community amateur sports clubs registered with HMRC (via Find that Charity)",
               "https://www.gov.uk/government/publications/community-amateur-sports-clubs-casc-registered-with-hmrc--2",
               OGL3, "club name", updated="monthly")


def casc_rows(cache):
    for row in _export(cache, "/orgid/source/casc.csv"):
        is_corp = ("registered-company" in _list(row["organisationType"]) or bool(_company_number(row))
                   or corporate_name(row["name"]))
        yield _ftc_record(CASC, row, "sports club", "Community amateur sports club", is_corp,
                          "club is a company: a corporate body under PECR" if is_corp
                          else "club not shown to be incorporated: post only")


# ---- Church of England churches -----------------------------------------------------

COE = _source("ftc-church-of-england", "Church of England churches (via Find that Charity)",
              "https://www.churchofengland.org/resources/churchcare/churchcare-grants/open-grant-data-360-giving",
              CCBY4, "church name, type")


def coe_rows(cache):
    for row in _export(cache, "/orgid/source/coe.csv"):
        kinds = [k for k in _list(row["organisationType"]) if k != "church"]
        yield _ftc_record(COE, row, "church", (kinds[0] if kinds else "church").replace("-", " "), False,
                          "parish church: run by an unincorporated church council, post only")


SOURCES = [
    types.SimpleNamespace(SOURCE=CIC, rows=cic_rows),
    types.SimpleNamespace(SOURCE=MUTUALS, rows=mutual_rows),
    types.SimpleNamespace(SOURCE=CCNI, rows=ccni_rows),
    types.SimpleNamespace(SOURCE=HESA, rows=hesa_rows),
    types.SimpleNamespace(SOURCE=CASC, rows=casc_rows),
    types.SimpleNamespace(SOURCE=COE, rows=coe_rows),
]
