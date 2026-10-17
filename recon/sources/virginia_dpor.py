"""Virginia Department of Professional and Occupational Regulation (DPOR) regulant lists.

DPOR publishes a tab-separated "regulant list" for every licence it issues,
free of charge, refreshed every five business days. Only the lists of firms'
licences are read here, not individual practitioners: contractors (Class A,
B and C, about 50,000 firms, most with an email address), architecture and
engineering firms, salons, barber shops, tattoo parlours, spas, beauty
schools, estate agency firms, appraisal firms, auction firms, cemetery
companies, asbestos and lead firms and community associations.

The lists carry name, postal address, email, licence number and expiry date.
DPOR leaves phone numbers out. Licences past their expiry date are dropped.
"""

import csv
import os
from datetime import date, datetime

from . import download, joined, record, rule

SOURCE = {
    "name": "virginia-dpor",
    "title": "Virginia DPOR regulant lists (firms' licences only)",
    "country": "US",
    "url": "https://www.dpor.virginia.gov/RegulantLists",
    "licence": "Virginia DPOR regulant lists, published for download and 'provided free of "
               "charge in electronic format'; no terms of use or marketing restriction stated "
               "on the page or in DPOR's web policy (public records under Virginia FOIA)",
    "updated": "every 5 business days",
    "fields": "business name, postal address, email, licence type and number, contractor "
              "classifications, expiry date (no phone numbers)",
}

BASE = ("https://www.dpor.virginia.gov/sites/default/files/Records%20and%20Documents/"
        "Regulant%20List/{}__crnt.txt")

# File code: (kind in plain words, licence type as DPOR names it, legal form if the
# licence itself says). Contractor files come first so a firm listed in both the
# older 2701 file and a 2705 file is kept once, from the 2705 file.
FILES = {
    "2705a": ("contractor", "Class A contractor", ""),
    "2705b": ("contractor", "Class B contractor", ""),
    "2705c": ("contractor", "Class C contractor", ""),
    "2701": ("contractor", "Class A contractor", ""),
    "2703": ("contractor", "Temporary contractor", ""),
    "2707": ("energy analyst firm", "Residential building energy analyst firm", ""),
    "0405": ("architecture and engineering firm", "Professional corporation", "professional corporation"),
    "0407": ("architecture and engineering firm", "Business entity", ""),
    "0413": ("architecture and engineering firm", "Professional LLC", "professional LLC"),
    "3306": ("asbestos contractor", "Asbestos contractor", ""),
    "3333": ("asbestos testing laboratory", "Asbestos analytical lab", ""),
    "3334": ("asbestos testing laboratory", "Asbestos analytical lab branch office", ""),
    "3358": ("lead abatement contractor", "Lead abatement contractor", ""),
    "2906": ("auction firm", "Auctioneer firm", ""),
    "2908": ("auction firm", "Auctioneer firm", ""),
    "1202": ("beauty salon", "Cosmetology salon", ""),
    "1205": ("beauty school", "Cosmetology school", ""),
    "1208": ("nail salon", "Nail technician salon", ""),
    "1209": ("beauty school", "Nail technician school", ""),
    "1218": ("waxing salon", "Waxing salon", ""),
    "1219": ("beauty school", "Waxing school", ""),
    "1303": ("barber school", "Barber school", ""),
    "1304": ("barber shop", "Barber shop", ""),
    "1232": ("tattoo parlour", "Tattoo parlor", ""),
    "1235": ("tattoo parlour", "Limited tattoo parlor", ""),
    "1238": ("permanent make-up salon", "Permanent cosmetic tattoo salon", ""),
    "1251": ("tattoo school", "Tattooing school", ""),
    "1252": ("tattoo school", "Permanent cosmetic tattooing school", ""),
    "1242": ("body piercing studio", "Body piercing salon", ""),
    "1246": ("ear piercing studio", "Body piercing (ear only) salon", ""),
    "1266": ("beauty spa", "Esthetics spa", ""),
    "1267": ("beauty school", "Esthetics school", ""),
    "4106": ("wrestling promoter", "Wrestling promoter", ""),
    "4110": ("boxing promoter", "Boxing promoter", ""),
    "4901": ("cemetery company", "Cemetery company", ""),
    "4902": ("cemetery", "Cemetery", ""),
    "0550": ("community association", "Common interest community association", ""),
    "0516": ("timeshare exchange company", "Time-share exchange", ""),
    "4003": ("training provider", "Appraisal school", ""),
    "4008": ("property valuation firm", "Appraiser business", ""),
    "4009": ("appraisal management company", "Appraisal management company", ""),
    "0211": ("training provider", "Real estate school", ""),
    "0226f": ("estate agency", "Real estate firm", ""),
    "0226l": ("estate agency", "Real estate business entity", ""),
    "0226o": ("estate agency", "Real estate sole proprietorship", "sole proprietorship"),
    "0226b": ("estate agency branch", "Real estate branch office", ""),
}

CONTRACTOR_FILES = {"2705a", "2705b", "2705c", "2701", "2703"}

# Contractor classifications and specialties, from DPOR's
# "VA Contractors Classifications & Specialties" (18 VAC 50-22-20 and -30).
SPECIALTIES = {
    "CBC": "commercial building", "RBC": "residential building", "ELE": "electrical",
    "H/H": "highway and heavy", "HVA": "heating, ventilation and air conditioning",
    "PLB": "plumbing", "HIC": "home improvement", "CIC": "commercial improvement",
    "GFC": "gas fitting", "PTC": "painting and wallcovering", "LSC": "landscaping",
    "ROC": "roofing", "CEM": "concrete", "ESC": "electronic and communication services",
    "BRK": "masonry", "EMC": "equipment and machinery", "ISC": "landscape irrigation",
    "FAS": "fire alarm systems", "PAV": "asphalt paving and sealcoating",
    "FIC": "farm improvement", "IBC": "industrialised building", "AES": "alternative energy",
    "ASB": "asbestos", "REF": "refrigeration", "BSC": "billboards and signs",
    "SPR": "fire sprinklers", "RFC": "recreational facilities", "POL": "swimming pools",
    "ADS": "alternative sewage systems", "FSP": "fire suppression",
    "ENV": "environmental specialties", "FLR": "flooring", "FIN": "finish carpentry",
    "MCC": "marine facilities", "WWP": "water wells and pumps",
    "CDS": "conventional sewage systems", "DRY": "drywall", "MHC": "manufactured homes",
    "LAC": "lead abatement", "NGF": "natural gas fitting", "UUC": "underground utilities and excavation",
    "LPG": "liquefied petroleum gas", "STL": "steel erection", "VCC": "vessel construction",
    "GLZ": "glass and glazing", "EMW": "environmental monitoring wells",
    "EEC": "lifts and escalators", "FRM": "framing", "TMC": "tile, marble and terrazzo",
    "INS": "insulation", "BEC": "blasting", "RMC": "radon mitigation",
    "ASC": "accessibility lifts", "ASL": "accessibility lifts", "MSC": "miscellaneous",
    "DLR": "drug lab remediation", "SDS": "sewage disposal systems",
}

HEADER = ["BOARD", "OCCUPATION", "CERTIFICATE #", "INDIVIDUAL NAME", "BUSINESS NAME",
          "FIRST LINE ADDRESS", "SECOND LINE ADDRESS", "P O BOX #", "CITY", "STATE",
          "FIVE DIGIT ZIP CODE", "ZIP CODE EXTENSION", "PROVINCE", "COUNTRY", "POSTAL CODE",
          "EXPIRATION DATE", "CERTIFICATION DATE", "LICENSE RANK", "LICENSE SPECIALTY",
          "EMAILADDRESS"]


def read_list(path):
    """Rows of one regulant list. A comma in a business name sometimes comes
    through as an extra tab, which pushes every later column along by one;
    those spare pieces are put back into the business name."""
    with open(path, encoding="latin-1", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t", quoting=csv.QUOTE_NONE)
        header = [h.strip() for h in next(reader, [])]
        if header[:len(HEADER)] != HEADER:
            raise ValueError(f"Unexpected columns in {path}: {header}")
        width = len(HEADER)
        for parts in reader:
            if not any(p.strip() for p in parts):
                continue
            extra = len(parts) - width
            if extra > 0:
                parts = parts[:4] + [", ".join(p.strip() for p in parts[4:5 + extra])] + parts[5 + extra:]
            elif extra < 0:
                parts = parts + [""] * -extra
            yield {k: v.strip() for k, v in zip(HEADER, parts)}


def expired(text, today=None):
    try:
        return datetime.strptime(text.strip(), "%m/%d/%Y").date() < (today or date.today())
    except ValueError:
        return False  # No readable date: keep it rather than guess.


def specialties(text):
    return [SPECIALTIES.get(code, code) for code in (text or "").split()]


def rows(cache):
    seen = set()
    can, why = rule("US", None, "US business: CAN-SPAM allows business email with an opt-out")
    for code, (kind, licence_type, legal_form) in FILES.items():
        path = download(BASE.format(code), os.path.join(cache, f"{code}__crnt.txt"))
        for row in read_list(path):
            name = row["BUSINESS NAME"] or row["INDIVIDUAL NAME"]
            number = row["CERTIFICATE #"]
            if not name or not number or expired(row["EXPIRATION DATE"]):
                continue
            # Contractor licence numbers are shared across the 2701 and 2705 files.
            source_id = f"27-{number}" if code in CONTRACTOR_FILES else f"{code}-{number}"
            if source_id in seen:
                continue
            seen.add(source_id)
            category = licence_type
            if code in CONTRACTOR_FILES and row["LICENSE SPECIALTY"]:
                category = f"{licence_type}: " + ", ".join(specialties(row["LICENSE SPECIALTY"]))
            box = row["P O BOX #"]
            street = joined(row["FIRST LINE ADDRESS"], row["SECOND LINE ADDRESS"],
                            f"PO Box {box}" if box else "")
            country = "US" if row["COUNTRY"] in ("", "US", "USA") else row["COUNTRY"]
            people = row["INDIVIDUAL NAME"] if row["BUSINESS NAME"] and \
                row["INDIVIDUAL NAME"].lower() != name.lower() else ""
            yield record(
                SOURCE, source_id, name, kind=kind, category=category,
                legal_form=legal_form, status="Licensed",
                address=street, town=row["CITY"], region=row["STATE"],
                postcode=row["FIVE DIGIT ZIP CODE"] or row["POSTAL CODE"], country=country,
                emails=row["EMAILADDRESS"], people=people,
                registration_number=f"DPOR {row['BOARD']}{row['OCCUPATION']}-{number}",
                can_email=can, rule_reason=why,
                source_url=BASE.format(code))
