"""CMS NPPES National Provider Identifier registry, organisations only (US federal).

Every US healthcare organisation with an NPI: clinics, practices, pharmacies,
care homes, labs, suppliers. About 2 million organisation records with a
practice address, phone, and the name and title of the person authorised to
act for them. The monthly file is about 1 GB zipped and 12 GB unzipped, so the
CSV is read straight out of the zip and never unpacked to disk. Deactivated
NPIs are dropped. Individual practitioners (entity type 1) are not loaded.
"""

import csv
import io
import os
import re
import urllib.request
import zipfile
from datetime import datetime

from . import USER_AGENT, download, joined, record, rule

SOURCE = {
    "name": "nppes-organisations",
    "title": "CMS NPPES NPI registry (healthcare organisations)",
    "country": "US",
    "url": "https://download.cms.gov/nppes/NPI_Files.html",
    "licence": "US federal government data (public domain); NPPES data is published "
               "under FOIA for public use",
    "updated": "monthly, with weekly updates",
    "fields": "organisation name, other name, practice address, phone, authorised official "
              "and title, taxonomy (type of provider)",
}

PAGE = "https://download.cms.gov/nppes/NPI_Files.html"
TAXONOMY_PAGE = ("https://www.nucc.org/index.php/code-sets-mainmenu-41/"
                 "provider-taxonomy-mainmenu-40/csv-mainmenu-57")


def _fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read().decode("utf-8", "replace")


def latest_zip(cache):
    """The current monthly full file, found on the CMS download page. If the
    page can't be read, the newest zip already in the cache is used."""
    try:
        found = re.search(r"href='\./(NPPES_Data_Dissemination_[A-Za-z]+_\d{4}_V2\.zip)'",
                          _fetch(PAGE))
        if found:
            name = found.group(1)
            return download(f"https://download.cms.gov/nppes/{name}", os.path.join(cache, name))
    except OSError:
        pass
    have = sorted((f for f in os.listdir(cache) if f.startswith("NPPES_Data_Dissemination_")
                   and f.endswith(".zip")), key=lambda f: os.path.getmtime(os.path.join(cache, f)))
    if not have:
        raise OSError(f"No NPPES file found on {PAGE}")
    return os.path.join(cache, have[-1])


def taxonomy_names(cache):
    """Taxonomy code -> plain name, from the NUCC code list. Empty if unreachable,
    in which case the bare code is used as the category."""
    try:
        links = re.findall(r'href="(/images/stories/CSV/nucc_taxonomy_(\d+)\.csv)"',
                           _fetch(TAXONOMY_PAGE))
        path, version = max(links, key=lambda link: int(link[1]))
        local = download("https://www.nucc.org" + path,
                         os.path.join(cache, f"nucc_taxonomy_{version}.csv"))
    except (OSError, ValueError):
        return {}
    with open(local, encoding="utf-8-sig", errors="replace", newline="") as handle:
        return {r["Code"]: r["Display Name"] or joined(r["Classification"], r["Specialization"])
                for r in csv.DictReader(handle)}


def _date(text):
    try:
        return datetime.strptime(text, "%m/%d/%Y").date()
    except ValueError:
        return None


def deactivated(row):
    gone, back = _date(row["NPI Deactivation Date"]), _date(row["NPI Reactivation Date"])
    return bool(gone) and not (back and back >= gone)


def zip_code(text):
    """NPPES writes ZIP+4 without the hyphen: '283044552' -> '28304-4552'."""
    text = text.strip()
    return f"{text[:5]}-{text[5:]}" if len(text) == 9 and text.isdigit() else text


def primary_taxonomy(row):
    codes = [row.get(f"Healthcare Provider Taxonomy Code_{i}", "") for i in range(1, 16)]
    for i, code in enumerate(codes, 1):
        if code and row.get(f"Healthcare Provider Primary Taxonomy Switch_{i}") == "Y":
            return code
    return next((c for c in codes if c), "")


def rows(cache):
    os.makedirs(cache, exist_ok=True)
    names = taxonomy_names(cache)
    with zipfile.ZipFile(latest_zip(cache)) as archive:
        member = next(n for n in archive.namelist()
                      if n.startswith("npidata_pfile_") and not n.endswith("_fileheader.csv"))
        with archive.open(member) as raw:
            text = io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline="")
            for row in csv.DictReader(text):
                if row["Entity Type Code"] != "2" or deactivated(row):
                    continue
                row = {k: "" if v == "<UNAVAIL>" else v for k, v in row.items()}
                name = row["Provider Organization Name (Legal Business Name)"]
                if not name.strip():
                    continue
                code = primary_taxonomy(row)
                official = joined(row["Authorized Official First Name"],
                                  row["Authorized Official Middle Name"],
                                  row["Authorized Official Last Name"], sep=" ")
                if official and row["Authorized Official Title or Position"]:
                    official = f"{official} ({row['Authorized Official Title or Position'].strip()})"
                foreign = row["Provider Business Practice Location Address Country Code (If outside U.S.)"]
                country = "US" if foreign in ("", "US") else foreign
                can, why = rule(country, None,
                                "US business: CAN-SPAM allows business email with an opt-out")
                yield record(
                    SOURCE, row["NPI"], name, other_name=row["Provider Other Organization Name"],
                    kind="healthcare provider", category=names.get(code, code),
                    legal_form="subpart of an organisation" if row["Is Organization Subpart"] == "Y" else "",
                    status="Active",
                    address=joined(row["Provider First Line Business Practice Location Address"],
                                   row["Provider Second Line Business Practice Location Address"]),
                    town=row["Provider Business Practice Location Address City Name"],
                    region=row["Provider Business Practice Location Address State Name"],
                    postcode=zip_code(row["Provider Business Practice Location Address Postal Code"]),
                    country=country,
                    phones=joined(row["Provider Business Practice Location Address Telephone Number"],
                                  row["Provider Business Mailing Address Telephone Number"],
                                  row["Authorized Official Telephone Number"], sep="; "),
                    people=official, registration_number=f"NPI {row['NPI']}",
                    can_email=can, rule_reason=why)
