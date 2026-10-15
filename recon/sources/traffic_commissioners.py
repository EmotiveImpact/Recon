"""Traffic Commissioners' goods and passenger vehicle operator licences (OGL v3).

Every haulier, own-account lorry operator, and bus and coach firm licensed in
Great Britain, published weekly by the DVSA as one CSV per traffic area.
Each row gives the operator's name, legal form (limited company, LLP,
partnership, sole trader or other), company number, correspondence address,
fleet size and its directors or partners. There is no email, phone or
website: Recon finds those on each firm's own site.

The CSV repeats a licence once for every director, partner and transport
manager; this loader folds those rows back into one record per licence.
"""

import os
import re
import urllib.parse
import urllib.request

from . import USER_AGENT, corporate_name, download, joined, read_csv, record, rule

SOURCE = {
    "name": "traffic-commissioners-operators",
    "title": "Traffic Commissioners goods and PSV operator licences (Great Britain)",
    "country": "GB",
    "url": "https://www.data.gov.uk/dataset/2a67d1ee-8f1b-43a3-8bc6-e8772d162a3c/"
           "traffic-commissioners-goods-and-public-service-vehicle-operator-licence-records",
    "licence": "Open Government Licence v3.0",
    "updated": "weekly",
    "fields": "operator name, legal form, company number, licence number and type, "
              "address, vehicles authorised, directors or partners, transport manager",
}

BASE = "https://content.mgmt.dvsacloud.uk/olcs.app.prod.dvsa.aws/data-gov-uk-export/"
# The traffic areas as named in the export, used when the dataset page
# can't be read. The page is checked first in case an area is renamed.
REGIONS = ["East of England", "London and the South East of England", "North East of England",
           "North West of England", "Scotland", "Wales", "West Midlands", "West of England"]
_LINK = re.compile(r'href="(https://content\.mgmt\.dvsacloud\.uk/[^"]*OLBSLicenceReport_[^"]+\.csv)"')

# Licences still in force. Suspended licences may not be used for now.
CURRENT = {"lsts_valid": "valid", "lsts_curtailed": "curtailed"}

CORPORATE_FORMS = {"Limited Company", "Limited Liability Partnership"}
PUBLIC_BODY = re.compile(r"\b(council|county|borough|university|college|nhs|trust|authority|"
                         r"police|fire|ministry|secretary of state|school|academy)\b", re.I)


def csv_links():
    try:
        request = urllib.request.Request(SOURCE["url"], headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=60) as response:
            page = response.read().decode("utf-8", "replace")
        links = sorted(set(_LINK.findall(page)))
    except OSError:
        links = []
    if not links:
        links = [BASE + f"OLBSLicenceReport_{region}.csv" for region in REGIONS]
    # The page writes some links with raw spaces and some with %20.
    return [BASE + urllib.parse.quote(urllib.parse.unquote(link[len(BASE):])) for link in links]


def split_address(value):
    """'1 HIGH STREET  TOWN GB AB1 2CD' -> ('1 High Street Town', 'AB1 2CD')."""
    value = " ".join((value or "").split())
    head, sep, tail = value.rpartition(" GB ")
    if not sep:
        return value, ""
    return head, tail


def corporate(row):
    form = row["OperatorType"]
    if form in CORPORATE_FORMS:
        return True, f"{form.lower()}: a corporate body under PECR"
    if form.startswith("Other"):
        if corporate_name(row["OperatorName"]) or PUBLIC_BODY.search(row["OperatorName"]):
            return True, "public body or incorporated organisation: a corporate body under PECR"
        return False, "other organisation not shown to be incorporated: post only"
    if form == "Partnership" and corporate_name(row["OperatorName"]):
        return True, "partnership trading as a company: a corporate body under PECR"
    return False, f"{form.lower() or 'operator'}: post only under PECR"


def licences(cache):
    """One merged dict per licence number."""
    found = {}
    for url in csv_links():
        name = urllib.parse.unquote(url.rsplit("/", 1)[1]).replace(" ", "_")
        path = download(url, os.path.join(cache, name))
        for row in read_csv(path):
            if row["LicenceStatus"] not in CURRENT:
                continue
            number = row["LicenceNumber"].strip()
            held = found.setdefault(number, {**row, "people": [], "managers": []})
            person = row["DirectorOrPartner"].strip()
            if person and person != "None" and person not in held["people"]:
                held["people"].append(person)
            manager = row["TransportManager"].strip()
            if manager and manager != "No Transport Manager" and manager not in held["managers"]:
                held["managers"].append(manager)
    return found


def rows(cache):
    for number, row in licences(cache).items():
        passenger = number.upper().startswith("P")
        is_corp, why = corporate(row)
        can, why = rule("GB", is_corp, why)
        address, postcode = split_address(row["CorrespondenceAddress"])
        centre, _ = split_address(row["OCAddress"])
        people = row["people"] + [f"{m} (Transport Manager)" for m in row["managers"]]
        vehicles = row["NumberOfVehiclesAuthorised"]
        company = row["CompanyRegNumber"].strip()
        yield record(
            SOURCE, number, row["OperatorName"],
            kind="bus or coach operator" if passenger else "haulier",
            category=joined("passenger (PSV)" if passenger else "goods vehicles", row["LicenceType"],
                            f"{vehicles} vehicles authorised" if vehicles else "",
                            f"operating centre: {centre}" if centre else "", sep="; "),
            legal_form=row["OperatorType"], status=CURRENT[row["LicenceStatus"]],
            address=address, region=row["GeographicRegion"], postcode=postcode, country="GB",
            people=people,
            registration_number=joined(f"licence {number}", f"company {company}" if company else "",
                                       sep="; "),
            company_number=company or "", can_email=can, rule_reason=why)
