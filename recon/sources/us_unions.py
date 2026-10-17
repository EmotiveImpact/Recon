"""US labour unions from the Department of Labor's Office of Labor-Management
Standards (OLMS) Online Public Disclosure Room (US federal data, public domain).

Every private-sector union in the US files a yearly financial report (form
LM-2, LM-3 or LM-4). OLMS publishes all of a year's reports as one zip of
pipe-delimited text files; lm_data_data_<year>.txt holds each filer's name,
affiliation, designation (for example "LU 123"), address and file number.
We take the two newest complete years, so unions that file late are still
caught, and keep one row per file number (its latest report). About 20,000
unions.

Guide to the files:
https://olmsapps.dol.gov/query/Guide_to_Working_with_OLMS_LM_Data.pdf
"""

import csv
import io
import os
import re
import urllib.parse
import zipfile
from datetime import date

from . import USER_AGENT, download, joined, record, rule

SOURCE = {
    "name": "olms-unions",
    # The Department of Labor's server leaves out part of its certificate
    # chain, so the download fails from the cloud workspace.
    "pending": "download blocked by the Department of Labor's certificate; untested",
    "title": "US Department of Labor OLMS union reports (LM-2, LM-3, LM-4)",
    "country": "US",
    "url": "https://olmsapps.dol.gov/olpdr/",
    "licence": "US federal public data (public domain)",
    "updated": "daily; yearly zips",
    "fields": "union name, affiliation, designation and number, address, phone, file number, members",
}

YEARLY_PAGE = "https://olmsapps.dol.gov/query/getYearlyData.do"

# OLMS designation codes, spelt out so names read naturally.
DESIGNATIONS = {
    "LU": "Local", "LG": "Lodge", "BR": "Branch", "C": "Council", "DC": "District Council",
    "JC": "Joint Council", "JB": "Joint Board", "DLG": "District Lodge", "CH": "Chapter",
    "D": "District", "R": "Region", "CONF": "Conference", "SA": "State Association",
    "SC": "System Council", "SFED": "State Federation", "SLB": "State Legislative Board",
    "GCA": "General Committee of Adjustment", "SBA": "System Board of Adjustment",
    "LEC": "Local Executive Council", "BCTC": "Building and Construction Trades Council",
    "CLC": "Central Labor Council", "UNIT": "Unit", "LLG": "Local Lodge", "DIV": "Division",
    "ASSN": "Association", "COUNCIL": "Council", "LOCAL": "Local", "LODGE": "Lodge",
}
HEADQUARTERS = {"NHQ", "IHQ", "HQ", ""}

# Column names differ a little between years, so each field has a few spellings.
COLUMNS = {
    "file": ("F_NUM", "FILE_NUMBER", "FNUM"),
    "union": ("UNION_NAME", "UNION_NM"),
    "aff": ("AFF_ABBR", "AFFILIATION"),
    "desig_pre": ("DESIG_PRE",),
    "desig": ("DESIG_NAME", "DESIGNATION"),
    "desig_num": ("DESIG_NUM",),
    "desig_suf": ("DESIG_SUF",),
    "unit": ("UNIT_NAME",),
    "street": ("STREET_ADR", "STREET_ADDRESS", "ADDRESS", "STREET"),
    "street2": ("STREET_ADR2", "ADDRESS2"),
    "city": ("CITY",),
    "state": ("STATE",),
    "zip": ("ZIP", "ZIP_CODE"),
    "phone": ("PHONE", "PHONE_NUM", "TELEPHONE"),
    "year": ("YR_COVERED", "YEAR"),
    "received": ("RECEIVE_DATE", "RCV_DATE"),
    "form": ("FORM_TYPE",),
    "members": ("MEMBERS",),
}


def _value(row, field):
    for name in COLUMNS[field]:
        if row.get(name):
            return row[name].strip()
    return ""


def yearly_links(page):
    """{year: url} for every yearly zip linked from the download page."""
    links = {}
    for href in re.findall(r'href="([^"]+)"', page):
        if ".zip" not in href.lower() and "year" not in href.lower():
            continue
        found = re.search(r"(20\d\d)", href)
        if found:
            links.setdefault(int(found.group(1)), urllib.parse.urljoin(YEARLY_PAGE, href.replace("&amp;", "&")))
    return links


def _header(names):
    return [n.strip().strip('"').upper() for n in names]


def read_filers(archive):
    """Rows of lm_data_data_<year>.txt as dicts keyed by upper-case column name."""
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        data = next((n for n in names if re.search(r"lm_data_data", n, re.I)), None)
        if not data:
            return
        meta = next((n for n in names if re.search(r"lm_data_meta", n, re.I)), None)
        csv.field_size_limit(1 << 30)
        with z.open(data) as raw:
            reader = csv.reader(io.TextIOWrapper(raw, encoding="latin-1", newline=""), delimiter="|")
            first = next(reader, None)
            if first is None:
                return
            header = _header(first)
            rows_before = []
            if not ({"F_NUM", "UNION_NAME"} & set(header)) and meta:
                # No header row: take the column names from the meta file.
                with z.open(meta) as m:
                    lines = io.TextIOWrapper(m, encoding="latin-1").read().splitlines()
                header = _header(re.split(r"[|,\t ]", line.strip())[0] for line in lines if line.strip())
                header = [h for h in header if h and h not in ("FIELD", "FIELD_NAME", "NAME")]
                rows_before = [first]
            for values in rows_before + list(reader):
                yield dict(zip(header, values))


def union_name(row):
    """A natural name such as "Teamsters Local 123" from the OLMS parts."""
    base = _value(row, "union")
    desig = _value(row, "desig").upper()
    number = _value(row, "desig_num")
    if desig in HEADQUARTERS and not number:
        return _tidy(base)
    words = [_value(row, "desig_pre"), DESIGNATIONS.get(desig, desig.title()), number,
             _value(row, "desig_suf")]
    return joined(_tidy(base), *[w for w in words if w], sep=" ")


def short_name(row):
    """OLMS's own short form, such as "IBT LU 123", kept as the other name."""
    return joined(_value(row, "aff"), _value(row, "desig_pre"), _value(row, "desig"),
                  _value(row, "desig_num"), _value(row, "desig_suf"), sep=" ")


KEEP_UPPER = {"AFL-CIO", "AFL", "CIO", "CLC", "IBT", "UAW", "SEIU", "AFSCME", "IBEW", "UFCW",
              "USW", "CWA", "IUOE", "IAM", "NEA", "AFT", "UNITE", "HERE", "II", "III", "IV",
              "USA", "US", "NFFE", "AFGE", "NAGE", "NALC", "APWU", "ILA", "ILWU", "SMART", "BLET",
              "TCU", "OPEIU", "IATSE", "RWDSU", "LIUNA", "UA", "BCTGM", "IUPAT", "UBC"}


def _tidy(name):
    """Title case for names held in capitals, keeping known initialisms."""
    name = " ".join((name or "").split())
    if not name or not name.isupper():
        return name
    words = [w if w.strip(",.()") in KEEP_UPPER else w.title() for w in name.split()]
    return " ".join(w.lower() if i and w.lower() in SMALL_WORDS else w for i, w in enumerate(words))


SMALL_WORDS = {"of", "and", "the", "for", "in", "on", "at", "to", "a", "an", "&"}


def _newer(a, b):
    return (_value(a, "year"), _value(a, "received")) >= (_value(b, "year"), _value(b, "received"))


def rows(cache):
    page_path = download(YEARLY_PAGE, os.path.join(cache, "yearly-data.html"),
                         headers={"User-Agent": USER_AGENT})
    with open(page_path, encoding="utf-8", errors="replace") as handle:
        links = yearly_links(handle.read())
    this_year = date.today().year
    years = sorted((y for y in links if y < this_year), reverse=True)[:2]
    latest = {}
    for year in years:
        archive = download(links[year], os.path.join(cache, f"{year}.zip"))
        for row in read_filers(archive):
            file_number = _value(row, "file")
            if not file_number or not _value(row, "union"):
                continue
            if file_number not in latest or _newer(row, latest[file_number]):
                latest[file_number] = row
    can, why = rule("US", None, "US organisation: CAN-SPAM allows email with an opt-out")
    for file_number, row in latest.items():
        yield record(
            SOURCE, file_number, union_name(row), other_name=joined(short_name(row), _value(row, "unit"),
                                                                    sep="; "),
            kind="trade union", category=_tidy(_value(row, "union")), legal_form="labor organization",
            status=joined(f"Filed {_value(row, 'form')}" if _value(row, "form") else "",
                          f"for {_value(row, 'year')}" if _value(row, "year") else "", sep=" "),
            address=joined(_value(row, "street"), _value(row, "street2")), town=_value(row, "city"),
            region=_value(row, "state"), postcode=_value(row, "zip"), country="US",
            phones=_value(row, "phone"), registration_number=f"OLMS file {file_number}",
            can_email=can, rule_reason=why)
