"""Approved premises for civil marriages and civil partnerships (General
Register Office, Open Government Licence).

Every venue in England and Wales licensed by its council for civil
weddings and partnerships: hotels, country houses, barns, function rooms,
museums and council buildings, with address, phone and licence expiry date.
No emails or websites: Recon finds them later. The list is a spreadsheet
(OpenDocument .ods); the current file is found on the GOV.UK page and read
with the standard library, since an .ods file is a zip of XML.
"""

import os
import re
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from datetime import date, datetime

from . import USER_AGENT, corporate_name, download, record, rule
from .. import text

SOURCE = {
    "name": "gro-marriage-venues",
    "title": "Civil marriage and civil partnership approved premises (England and Wales)",
    "country": "GB",
    "url": "https://www.gov.uk/government/publications/civil-marriages-and-partnerships-approved-premises-list",
    "licence": "Open Government Licence v3.0",
    "updated": "irregularly, a few times a year",
    "fields": "venue name, address, phone, licence expiry date",
}

_ODS = re.compile(r'href="(https://assets\.publishing\.service\.gov\.uk/[^"]+\.ods)"')
_TABLE = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
_TEXT = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"


def latest_ods():
    request = urllib.request.Request(SOURCE["url"], headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        page = response.read().decode("utf-8", "replace")
    links = _ODS.findall(page)
    if not links:
        raise RuntimeError("No .ods file listed on the approved premises page")
    return links[0]


def ods_rows(path):
    """Each row of the first sheet of an .ods file, as a list of cell texts."""
    with zipfile.ZipFile(path) as archive, archive.open("content.xml") as content:
        for _, element in ET.iterparse(content):
            if element.tag != _TABLE + "table-row":
                continue
            cells = []
            for cell in element:
                if cell.tag not in (_TABLE + "table-cell", _TABLE + "covered-table-cell"):
                    continue
                value = "\n".join("".join(p.itertext()) for p in cell.iter(_TEXT + "p"))
                # Empty cells are stored once with a repeat count; cap it.
                repeat = int(cell.get(_TABLE + "number-columns-repeated", "1"))
                cells.extend([value] * min(repeat, 20))
            element.clear()
            yield cells


def _expiry(value):
    try:
        return datetime.strptime(value.strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


def _status(expiry, today):
    """The list is only republished now and then, so a past expiry date
    usually means a renewal not yet shown, not a closed venue: keep it and say so."""
    if not expiry:
        return "approved"
    if expiry < today:
        return f"approval ran to {expiry.isoformat()}, renewal not shown in this list"
    return f"approved until {expiry.isoformat()}"


def rows(cache):
    url = latest_ods()
    folder = url.rstrip("/").split("/")[-2]
    path = download(url, os.path.join(cache, f"{folder}-{os.path.basename(url)}"))
    header = None
    today = date.today()
    for cells in ods_rows(path):
        if header is None:
            if "Name" in cells and "Address" in cells:
                header = cells
            continue
        row = dict(zip(header, cells))
        number, name = row.get("No.", "").strip(), row.get("Name", "").strip()
        if not number or not name:
            continue
        expiry = _expiry(row.get("Expiry Date", ""))
        address = " ".join(row.get("Address", "").split()).strip(" ,")
        is_corp = corporate_name(name)
        can, why = rule("GB", is_corp, "venue named as a company" if is_corp
                        else "venue not shown to be incorporated: post only")
        yield record(
            SOURCE, number, name, kind="venue", category="approved wedding venue",
            status=_status(expiry, today),
            address=address, postcode=text.postcode(address), country="GB",
            phones=row.get("Telephone", ""), registration_number=f"GRO premises {number}",
            can_email=can, rule_reason=why, source_url=url)
