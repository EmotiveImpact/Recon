"""California Contractors State License Board (CSLB) master list of licensed contractors.

CSLB's public data portal offers the whole licence register as free CSV
downloads: the licence master file (about 238,000 licences: business name,
mailing address, phone, business type, classifications, status and dates) and
the personnel file (owners, officers and qualifying managers for each licence).
Only active licences are kept: status "CLEAR", not past expiry and not
inactive. Suspended, cancelled and expired licences are dropped. CSLB does not
publish email addresses (Business and Professions Code section 27).

The download sits behind an ASP.NET form on the portal page: choosing a file
from the drop-down list shows a download button. The loader does the same two
steps a browser does. The site runs on several servers that do not share form
state, so a step that lands on a different server is refused and simply tried
again.
"""

import csv
import os
import re
import shutil
import time
import urllib.parse
import urllib.request
from datetime import date, datetime

from . import USER_AGENT, record, rule

SOURCE = {
    "name": "california-cslb",
    "title": "California CSLB licensed contractors (active licences)",
    "country": "US",
    "url": "https://www.cslb.ca.gov/OnlineServices/DataPortal/ContractorList",
    "licence": "CSLB public data portal: 'There is no charge for this service'; no data licence "
               "or marketing restriction stated. California's conditions of use (ca.gov/use): "
               "information on state websites 'is considered in the public domain' and 'may be "
               "distributed or copied as permitted by law'. Emails withheld by B&P Code s.27",
    "updated": "daily",
    "fields": "business name, mailing address, county, phone, business type, classifications, "
              "owners and officers, licence number",
}

PORTAL = SOURCE["url"]
FILES = {  # drop-down value, download button
    "master": ("M", "ctl00$MainContent$lbMasterCSV"),
    "personnel": ("P", "ctl00$MainContent$lbtnPersonnelcsv"),
}

# Licence classifications, from CSLB's "Licensing Classifications" pages.
CLASSES = {
    "A": "general engineering", "B": "general building", "B-2": "residential remodelling",
    "C-2": "insulation and acoustical", "C-4": "boilers, hot water heating and steam fitting",
    "C-5": "framing and rough carpentry", "C-6": "cabinets, millwork and finish carpentry",
    "C-7": "low voltage systems", "C-8": "concrete", "C-9": "drywall", "C-10": "electrical",
    "C-11": "lifts", "C-12": "earthwork and paving", "C-13": "fencing",
    "C-15": "flooring", "C-16": "fire protection", "C-17": "glazing",
    "C-20": "heating, ventilation and air conditioning", "C-21": "building moving and demolition",
    "C-22": "asbestos abatement", "C-23": "ornamental metal", "C-27": "landscaping",
    "C-28": "locks and security equipment", "C-29": "masonry",
    "C-31": "construction zone traffic control", "C-32": "parking and highway improvement",
    "C-33": "painting and decorating", "C-34": "pipelines", "C-35": "lathing and plastering",
    "C-36": "plumbing", "C-38": "refrigeration", "C-39": "roofing", "C-42": "sanitation systems",
    "C-43": "sheet metal", "C-45": "signs", "C-46": "solar", "C-47": "manufactured housing",
    "C-49": "tree and palm", "C-50": "reinforcing steel", "C-51": "structural steel",
    "C-53": "swimming pools", "C-54": "ceramic and mosaic tile", "C-55": "water conditioning",
    "C-57": "well drilling", "C-60": "welding", "C-61": "limited specialty",
    "D-03": "awnings", "D-04": "central vacuum systems", "D-06": "concrete related services",
    "D-07": "conveyors and cranes", "D-08": "doors and door services",
    "D-09": "drilling, blasting and oil field work", "D-10": "elevated floors",
    "D-12": "synthetic products", "D-13": "fire extinguisher systems", "D-15": "furnaces",
    "D-16": "hardware, locks and safes", "D-17": "industrial insulation", "D-19": "land clearing",
    "D-20": "lead burning and fabrication", "D-21": "machinery and pumps", "D-22": "marble",
    "D-23": "medical gas systems", "D-24": "metal products", "D-25": "mirrors and fixed glass",
    "D-27": "movable partitions", "D-28": "doors, gates and activating devices",
    "D-29": "paperhanging", "D-30": "pile driving and foundation jacking",
    "D-31": "pole installation and maintenance", "D-32": "power nailing and fastening",
    "D-34": "prefabricated equipment", "D-35": "pool and spa maintenance",
    "D-36": "rigging", "D-37": "safes and vaults", "D-38": "sand and water blasting",
    "D-39": "scaffolding", "D-40": "service station equipment", "D-41": "siding and decking",
    "D-42": "non-electrical signs", "D-43": "soil grouting", "D-44": "sprinklers",
    "D-47": "tennis court surfacing", "D-48": "theatre and school equipment",
    "D-49": "tree service", "D-50": "suspended ceilings",
    "D-51": "waterproofing and weatherproofing", "D-52": "window coverings",
    "D-53": "wood tanks", "D-54": "rockscaping", "D-55": "blasting", "D-56": "trenching",
    "D-59": "hydroseed spraying", "D-62": "air and water balancing",
    "D-63": "construction clean-up", "D-64": "non-specialised", "D-65": "weatherisation",
    "HAZ": "hazardous substance removal", "ASB": "asbestos certification",
}

# Personnel titles that are not a current owner or officer.
SKIP_TITLES = {"Deceased", "Continuance Granted", "Entity (JV)", ""}
MAX_PEOPLE = 5


def _hidden(page):
    return dict(re.findall(r'<input type="hidden" name="([^"]+)" id="[^"]*" value="([^"]*)"', page))


def _post(fields):
    request = urllib.request.Request(
        PORTAL, data=urllib.parse.urlencode(fields).encode(),
        headers={"User-Agent": USER_AGENT})
    return urllib.request.urlopen(request, timeout=900)


def fetch(which, path, attempts=12):
    """Download one portal file (master or personnel) to path, once."""
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    choice, button = FILES[which]
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(PORTAL, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=60) as response:
                page = response.read().decode("utf-8", "replace")
            with _post({**_hidden(page), "__EVENTTARGET": "ctl00$MainContent$ddlStatus",
                        "ctl00$MainContent$ddlStatus": choice}) as response:
                page = response.read().decode("utf-8", "replace")
            if button.split("$")[-1] in page:
                with _post({**_hidden(page), "__EVENTTARGET": button,
                            "ctl00$MainContent$ddlStatus": choice}) as response:
                    if "csv" in (response.headers.get("Content-Type") or ""):
                        with open(path + ".part", "wb") as out:
                            shutil.copyfileobj(response, out, 1 << 20)
                        os.replace(path + ".part", path)
                        return path
        except OSError:
            if attempt == attempts - 1:
                raise
        time.sleep(2 + attempt)
    raise OSError(f"CSLB portal refused the {which} download {attempts} times")


def _date(text):
    try:
        return datetime.strptime((text or "").strip(), "%m/%d/%Y").date()
    except ValueError:
        return None


def active(row, today=None):
    """Status CLEAR, not past expiry, and not made inactive (or reactivated since)."""
    if row["PrimaryStatus"].strip().upper() != "CLEAR":
        return False
    expires = _date(row["ExpirationDate"])
    if expires and expires < (today or date.today()):
        return False
    inactive, reactive = _date(row["InactivationDate"]), _date(row["ReactivationDate"])
    return not (inactive and (not reactive or reactive < inactive))


def classes(text):
    """'C10| C-7| D64' -> ['electrical', 'low voltage systems', 'non-specialised']."""
    found = []
    for code in (text or "").split("|"):
        code = code.strip().upper()
        match = re.fullmatch(r"([CD])-?(\d+)", code)
        if match:
            code = f"{match.group(1)}-{int(match.group(2)):0{2 if match.group(1) == 'D' else 1}d}"
        if code:
            name = CLASSES.get(code, code)
            if name not in found:
                found.append(name)
    return found


def person_name(text):
    """'DAVIS      DANA      MICHAEL' (surname first) -> 'DANA MICHAEL DAVIS'."""
    parts = re.split(r"\s{2,}", (text or "").split("|")[0].strip())
    return " ".join(parts[1:] + parts[:1]) if len(parts) > 1 else (parts[0] if parts else "")


def people(path):
    """Licence number -> current owners and officers, as 'NAME (title)'."""
    found = {}
    with open(path, encoding="latin-1", errors="replace", newline="") as handle:
        for row in csv.DictReader(handle):
            if not row["Name-TP"].strip().startswith("Principal"):
                continue
            titles = [t.strip() for t in row["EMP-Titl-CDE"].split("|")]
            ended = [d.strip() for d in row["DIS-ASSN-DT"].split("|")]
            current = []
            for i, title in enumerate(titles):
                if title not in SKIP_TITLES and not (ended[i] if i < len(ended) else "") \
                        and title not in current:
                    current.append(title)
            name = person_name(row["Name"])
            if not current or not name:
                continue
            names = found.setdefault(row["LIC-NO"].strip(), [])
            entry = f"{name} ({', '.join(current)})"
            if len(names) < MAX_PEOPLE and entry not in names:
                names.append(entry)
    return found


def rows(cache):
    master = fetch("master", os.path.join(cache, "MasterLicenseData.csv"))
    try:
        officers = people(fetch("personnel", os.path.join(cache, "PersonnelData.csv")))
    except OSError:
        officers = {}  # The licences are still worth having without names.
    can, why = rule("US", None, "US business: CAN-SPAM allows business email with an opt-out")
    seen = set()
    with open(master, encoding="latin-1", errors="replace", newline="") as handle:
        for row in csv.DictReader(handle):
            number = row["LicenseNo"].strip()
            if not number or number in seen or not active(row):
                continue
            seen.add(number)
            business = row["BusinessName"].strip()
            full = row["FullBusinessName"].strip()
            second = row["BUS-NAME-2"].strip()
            sole = row["BusinessType"].strip() == "Sole Owner"
            # Sole owners are listed surname first; the full name reads naturally.
            name = full if full and sole else business
            other = full if full and full != name else (second if second != name else "")
            zipcode = row["ZIPCode"].strip()
            if re.fullmatch(r"\d{9}", zipcode):  # ZIP+4 written without the dash.
                zipcode = zipcode[:5]
            country = row["country"].strip().upper()
            country = "US" if country in ("", "US", "USA", "UNITED STATES") else country
            yield record(
                SOURCE, number, name, other_name=other, kind="contractor",
                category=", ".join(classes(row["Classifications(s)"])),
                legal_form=row["BusinessType"].strip(), status="Active",
                address=row["MailingAddress"], town=row["City"], region=row["State"],
                postcode=zipcode, country=country,
                phones=row["BusinessPhone"], people=officers.get(number, []),
                registration_number=f"CSLB {number}", can_email=can, rule_reason=why)
