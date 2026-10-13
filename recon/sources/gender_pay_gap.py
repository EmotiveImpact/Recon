"""UK Gender Pay Gap service (Open Government Licence v3.0).

Every employer with 250 or more staff has reported its gender pay gap each
year since 2017, with its address, company number, SIC codes, size band, the
person responsible for the report (name and job title) and a link to its own
page about the gap. One file per reporting year; each employer's newest entry
is kept. The link is a page on the employer's own site, so its domain becomes
the website, unless it is a document host or a government site.

Companies and public bodies (councils, NHS bodies, universities and the like)
may be emailed; anyone else is post only.
"""

import glob
import os
import re
import urllib.request
from datetime import date

from .. import text
from . import USER_AGENT, corporate_name, download, joined, read_csv, record, rule

SOURCE = {
    "name": "gender-pay-gap",
    "title": "UK Gender Pay Gap service (employers with 250+ staff)",
    "country": "GB",
    "url": "https://gender-pay-gap.service.gov.uk/viewing/download",
    "licence": "Open Government Licence v3.0",
    "updated": "yearly (reports due each April)",
    "fields": "employer name, address, company number, SIC codes, size band, responsible person, website",
}

BASE = "https://gender-pay-gap.service.gov.uk"
_YEAR_LINK = re.compile(r'href="/viewing/download-data/(\d{4})"')

# A folder where another session may already have fetched the files, one
# subfolder per source; set RECON_INCOMING to look elsewhere.
INCOMING = "/mnt/project-files/master-db/incoming"

# The service uses SIC code 1 for public sector employers.
PUBLIC_SECTOR_SIC = "1"

_PUBLIC = re.compile(
    r"\b(nhs|council|borough|health board|university|college|police|fire and rescue|"
    r"ministry|department|government|authority|academy trust|academies trust|"
    r"multi academy|learning trust|schools trust|education trust|crown prosecution|"
    r"hm revenue|metropolitan|combined authority|parliament)\b", re.I)

_COMPANY_NUMBER = re.compile(r"^[A-Z]{0,2}\d{5,8}[A-Z]?$")

SIZES = {"Less than 250": "under 250 staff", "Not Provided": ""}

# Places a statement or report is often uploaded to that are not the
# organisation's own website. GOV.UK itself counts; a council's own
# something.gov.uk site does not.
DOCUMENT_HOSTS = (
    "service.gov.uk", "ctfassets.net", "drive.google.com", "docs.google.com", "sites.google.com",
    "storage.googleapis.com", "sanity.io", "officeapps.live.com", "onedrive.live.com",
    "1drv.ms", "sharepoint.com", "website-files.com", "amazonaws.com", "cloudfront.net",
    "wpenginepowered.com", "wpengine.com", "azureedge.net", "blob.core.windows.net",
    "dropbox.com", "box.com", "issuu.com", "yumpu.com", "hubspotusercontent-eu1.net",
    "hubspotusercontent-na1.net", "hubspotusercontent.com", "hs-sites.com", "hubfs.net",
    "wixstatic.com", "filesusr.com", "squarespace-cdn.com", "squarespace.com",
    "prismic.io", "contentstack.io", "imgix.net", "akamaihd.net", "cloudinary.com",
    "bit.ly", "tinyurl.com", "ow.ly", "adobe.com", "acrobat.adobe.com",
    "githubusercontent.com", "wordpress.com", "mcusercontent.com", "q4cdn.com",
    "datocms-assets.com", "storyblok.com", "flipsnack.com", "canva.com", "anyflip.com",
)

# Sub-sites that stand for the organisation's main domain.
_PREFIXES = ("www", "cdn", "static", "assets", "files", "media", "careers", "jobs",
             "investors", "investor", "corporate", "about", "docs", "downloads", "content",
             "documents", "resources", "images", "img", "uploads")
_SECOND_LEVEL = {"co", "org", "ac", "gov", "com", "net", "ltd", "plc", "me", "nhs", "sch", "police"}


def site_from_link(link):
    """The organisation's own website from a link to a page or document on
    it, as https://domain; '' when the link is on a document host, a
    government site or a social site."""
    host = text.domain((link or "").strip())
    if not host or "." not in host or " " in host:
        return ""
    if host == "gov.uk" or any(host == bad or host.endswith("." + bad) for bad in DOCUMENT_HOSTS):
        return ""
    if not text.own_website(host):
        return ""
    labels = host.split(".")
    while (len(labels) > 2 and labels[0] in _PREFIXES
           and not (len(labels) == 3 and labels[1] in _SECOND_LEVEL)):
        labels = labels[1:]
    return "https://" + ".".join(labels)


def incoming(source, year):
    """A CSV for this year already fetched into the incoming folder
    (incoming/<source>/, any CSV with the year in its name), or None."""
    folder = os.path.join(os.environ.get("RECON_INCOMING", INCOMING), source)
    for path in sorted(glob.glob(os.path.join(folder, f"*{year}*.csv")), reverse=True):
        if os.path.getsize(path) > 0:
            return path
    return None


def years():
    """The reporting years listed on the download page."""
    try:
        request = urllib.request.Request(SOURCE["url"], headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=60) as response:
            found = sorted({int(y) for y in _YEAR_LINK.findall(response.read().decode("utf-8", "replace"))})
    except OSError:
        found = []
    return found or list(range(2017, date.today().year + 1))


def year_file(year, newest, cache):
    """One year's CSV. The newest year still takes late reports, so its copy
    is named with today's date and fetched again on a later day."""
    if year != newest:
        found = incoming(SOURCE["name"], year)
        if found:
            return found
    name = f"gpg-{year}.csv" if year != newest else f"gpg-{year}-{date.today().isoformat()}.csv"
    return download(f"{BASE}/viewing/download-data/{year}", os.path.join(cache, name))


def public_body(row):
    sics = sic_codes(row.get("SicCodes"))
    return PUBLIC_SECTOR_SIC in sics or bool(_PUBLIC.search(employer_name(row)))


def sic_codes(value):
    return [c.strip() for c in re.split(r"[,\s]+", value or "") if c.strip()]


def employer_name(row):
    return (row.get("CurrentName") or row.get("EmployerName") or "").strip()


def company_number(row):
    number = (row.get("CompanyNumber") or "").upper().replace(" ", "")
    return number if _COMPANY_NUMBER.match(number) else ""


def size_band(value):
    value = (value or "").strip()
    if value in SIZES:
        return SIZES[value]
    return f"{value} staff"


def town_of(address, postcode):
    """The last part of the address before the postcode and country."""
    parts = [p.strip() for p in (address or "").split(",") if p.strip()]
    while parts and (parts[-1].upper().replace(" ", "") == (postcode or "").upper().replace(" ", "")
                     or parts[-1].lower() in {"united kingdom", "uk", "england", "scotland",
                                              "wales", "northern ireland", "great britain"}):
        parts.pop()
    return parts[-1] if len(parts) > 1 else ""


def to_record(row, year):
    name = employer_name(row)
    number = company_number(row)
    public = public_body(row)
    if number:
        can, why = rule("GB", True, "registered company or corporate body (company number given)")
    elif public:
        can, why = rule("GB", True, "public body")
    elif corporate_name(name):
        can, why = rule("GB", True, "trading as a company")
    else:
        can, why = rule("GB", False, "employer not shown to be incorporated: post only")
    sics = ["public sector" if c == PUBLIC_SECTOR_SIC else f"SIC {c}" for c in sic_codes(row.get("SicCodes"))]
    postcode = row.get("PostCode", "")
    other = row.get("EmployerName", "").strip()
    return record(
        SOURCE, row["EmployerId"], name, other_name=other if other.lower() != name.lower() else "",
        kind="public body" if public and not number else "employer",
        category=joined(*sics, size_band(row.get("EmployerSize")), sep="; "),
        address=row.get("Address", ""), town=town_of(row.get("Address"), postcode),
        postcode=postcode, country="GB",
        website=site_from_link(row.get("CompanyLinkToGPGInfo")),
        people=(row.get("ResponsiblePerson") or "").strip(),
        company_number=number, registration_number=f"GPG employer {row['EmployerId']} ({year})",
        can_email=can, rule_reason=why, source_url=f"{BASE}/employers/{row['EmployerId']}")


def rows(cache):
    listed = years()
    newest = max(listed)
    latest = {}  # employer id -> (year, submitted, row)
    for year in listed:
        try:
            path = year_file(year, newest, cache)
        except OSError:
            continue  # A year not published yet.
        for row in read_csv(path):
            employer = (row.get("EmployerId") or "").strip()
            if not employer or not employer_name(row):
                continue
            key = (year, row.get("DateSubmitted", ""))
            if employer not in latest or key > latest[employer][:2]:
                latest[employer] = (*key, row)
    for year, _, row in latest.values():
        yield to_record(row, year)
