"""US colleges and universities from IPEDS (National Center for Education
Statistics, federal public domain).

The "HD" institutional characteristics file lists every college, university,
community college and trade school that takes part in federal student aid:
about 6,000, with address, main phone, website and the chief officer's name
and title. Only institutions open in the current year (CYACTIVE = 1) are kept.
No emails: Recon finds them on each website. A new file appears each autumn;
the loader takes the newest year it can find.

The file also gives admissions, financial aid, veterans', athletics and
disability services page links. The master table has one website column, so
only the main website is kept; the others are in the cached file if needed.
College Scorecard repeats the same names and websites, so it is not loaded.
"""

import os
import zipfile
from datetime import date

from . import download, joined, read_csv, record, rule

SOURCE = {
    "name": "ipeds-colleges",
    "title": "IPEDS institutional characteristics (US colleges and universities)",
    "country": "US",
    "url": "https://nces.ed.gov/ipeds/datacenter/DataFiles.aspx",
    "licence": "US federal government data (public domain)",
    "updated": "yearly",
    "fields": "name, other name, sector, address, phone, website, chief officer and title, EIN",
}

DOWNLOAD = "https://nces.ed.gov/ipeds/datacenter/data/HD{}.zip"

SECTORS = {
    "0": "administrative unit", "1": "public, four-year or above",
    "2": "private not-for-profit, four-year or above", "3": "private for-profit, four-year or above",
    "4": "public, two-year", "5": "private not-for-profit, two-year",
    "6": "private for-profit, two-year", "7": "public, less than two-year",
    "8": "private not-for-profit, less than two-year", "9": "private for-profit, less than two-year",
}
SIZES = {"1": "under 1,000 students", "2": "1,000 to 4,999 students", "3": "5,000 to 9,999 students",
         "4": "10,000 to 19,999 students", "5": "20,000 or more students"}
CONTROLS = {"1": "Public institution", "2": "Private not-for-profit", "3": "Private for-profit"}


def kind(row):
    """university, college, community college, trade school or system office."""
    level, control = row["ICLEVEL"].strip(), row["CONTROL"].strip()
    if row["SECTOR"].strip() == "0":
        return "university system office"
    if level == "1":
        # Four-year places that also teach graduate students count as universities.
        return "university" if row["GROFFER"].strip() == "1" else "college"
    if level == "2":
        return "community college" if control == "1" else "college"
    return "trade school"


def _latest(cache):
    for year in range(date.today().year, date.today().year - 4, -1):
        try:
            return download(DOWNLOAD.format(year), os.path.join(cache, f"HD{year}.zip"))
        except OSError:
            continue
    raise RuntimeError("No IPEDS HD file found for the last four years")


def rows(cache):
    path = _latest(cache)
    folder = os.path.join(cache, os.path.basename(path)[:-4])
    with zipfile.ZipFile(path) as archive:
        name = next(n for n in archive.namelist() if n.lower().endswith(".csv"))
        csv_path = os.path.join(folder, os.path.basename(name))
        if not os.path.exists(csv_path):
            archive.extract(name, folder)
            os.replace(os.path.join(folder, name), csv_path)
    can, why = rule("US", None, "US college or university: CAN-SPAM allows email with an opt-out")
    for row in read_csv(csv_path):
        if row["CYACTIVE"].strip() != "1":
            continue
        flags = joined("HBCU" if row["HBCU"].strip() == "1" else "",
                       "tribal college" if row["TRIBAL"].strip() == "1" else "",
                       "land-grant" if row["LANDGRNT"].strip() == "1" else "", sep="; ")
        chief = joined(row["CHFNM"], f"({row['CHFTITLE'].strip()})" if row["CHFTITLE"].strip() else "",
                       sep=" ")
        number = row["EIN"].strip()
        yield record(
            SOURCE, row["UNITID"], row["INSTNM"], other_name=row["IALIAS"].strip(),
            kind=kind(row),
            category=joined(SECTORS.get(row["SECTOR"].strip(), ""), SIZES.get(row["INSTSIZE"].strip(), ""),
                            flags, sep="; "),
            legal_form=CONTROLS.get(row["CONTROL"].strip(), ""), status="Open",
            address=row["ADDR"], town=row["CITY"], region=row["STABBR"], postcode=row["ZIP"],
            country="US", website=row["WEBADDR"], phones=row["GENTELE"], people=chief,
            registration_number=joined(f"IPEDS {row['UNITID']}",
                                       f"EIN {number[:2]}-{number[2:]}" if len(number) == 9 and number.isdigit() else "", sep="; "),
            can_email=can, rule_reason=why)
