"""Open registers kept by regulators and councils, as extra places.

A register lists every licensed business of one kind. The Care Quality
Commission's directory has every dentist, GP, clinic and care home in
England, with its phone, website and the operator's legal name; some councils
publish their massage, nail and tattoo ("special treatment") licences. Use
only registers published under an open licence, such as the Open Government
Licence, and name them in a target list:

    "registers": [
        {"preset": "cqc", "sector": "Dentists", "kinds": ["Dentist"]},
        {"name": "camden-special-treatments", "url": "https://example.org/licences.csv",
         "licence": "Open Government Licence", "sector": "Beauty and wellness",
         "columns": {"name": "Premises name", "address": "Address", "postcode": "Postcode"}}
    ]

Columns that can be named: name, address, town, postcode, phone, website,
legal_name, kind and id. "kinds" keeps only rows whose kind column contains
one of the words given.

Professional registers of individual practitioners (HCPC, GOsC, GCC and the
like) are not registers of businesses and are never used. A register's
operator is kept (as legal_name) only when it is an organisation such as a
limited company: a sole practitioner's name is personal data.
"""

import csv
import io
import os
import re
import urllib.request

from . import contacts, geo, osm, places, text

KEEP_DAYS = 30

PRESETS = {
    "cqc": {
        "name": "cqc",
        "page": "https://www.cqc.org.uk/about-us/transparency/using-cqc-data",
        "link": r"https://www\.cqc\.org\.uk/[^\"']+CQC_directory\.csv",
        "licence": "Open Government Licence (Care Quality Commission)",
        "columns": {"name": "Name", "address": "Address", "postcode": "Postcode",
                    "phone": "Phone number", "website": "Service's website (if available)",
                    "kind": "Service types", "legal_name": "Provider name",
                    "id": "CQC Location ID (for office use only)"},
    },
}

_ORGANISATION = re.compile(r"\b(limited|ltd|llp|plc|cic|community interest company|nhs|trust|"
                           r"foundation|council|university)\b", re.I)


def _get(url):
    request = urllib.request.Request(url, headers={"User-Agent": osm.USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read().decode("utf-8-sig", "replace")


def _file(register, folder):
    """The register's CSV, downloaded when missing or a month old."""
    path = os.path.join(folder, f"{register['name']}.csv")
    if osm._fresh(path, KEEP_DAYS):
        return path
    url = register.get("url")
    if not url and register.get("page"):
        found = re.search(register["link"], _get(register["page"]))
        if not found:
            raise OSError(f"no download link found on {register['page']}")
        url = found.group(0)
    os.makedirs(folder, exist_ok=True)
    print(f"  Downloading {url}")
    osm._download(url, path)
    return path


def _rows(path, columns):
    """The register's rows as dicts, skipping any notes above the header."""
    with open(path, encoding="utf-8-sig", errors="replace") as handle:
        lines = list(csv.reader(io.StringIO(handle.read())))
    wanted = set(columns.values())
    for start, line in enumerate(lines):
        if wanted & {cell.strip() for cell in line}:
            header = [cell.strip() for cell in line]
            break
    else:
        return []
    return [dict(zip(header, line)) for line in lines[start + 1:] if any(line)]


def _phone(raw):
    digits = re.sub(r"\D", "", raw or "")
    return "0" + digits if len(digits) == 10 and not digits.startswith("0") else raw


def _website(raw):
    raw = (raw or "").strip()
    return "" if not raw else raw if "://" in raw else "https://" + raw


def read(target, register, path, positions):
    """Places from one register file, inside the target's box."""
    register = {**PRESETS.get(register.get("preset"), {}), **register}
    columns = register["columns"]
    kinds = [k.lower() for k in register.get("kinds", [])]
    west, south, east, north = target.box
    found = []
    for row in _rows(path, columns):
        value = lambda field: (row.get(columns.get(field, ""), "") or "").strip()
        kind = value("kind")
        if kinds and not any(k in kind.lower() for k in kinds):
            continue
        postcode = text.postcode(value("postcode"), target.country)
        where = positions.find(postcode) if postcode else None
        if not where or not (south <= where[0] <= north and west <= where[1] <= east):
            continue
        address = value("address")
        legal = value("legal_name")
        place = places.blank(
            name=value("name"), sector=register.get("sector", ""), category=kind,
            address=address, town=value("town") or address.split(",")[-1].strip(),
            postcode=postcode, lat=round(where[0], 6), lon=round(where[1], 6),
            website=_website(value("website")), source=register["name"],
            source_id=value("id") or f"{value('name')}|{postcode}",
            legal_name=legal if _ORGANISATION.search(legal) else "")
        if value("phone"):
            contacts.add_phones(place, [_phone(value("phone"))], target.country)
        found.append(place)
    return found


def fetch(target, folder=os.path.join("data", "registers"), postcodes=None):
    """Places from every register the target names. Needs postcode positions
    (geo.py) to keep only the rows inside the target's box."""
    if not target.registers:
        return []
    path = postcodes or geo.postcode_file()
    if not path:
        print("  Registers need the postcode file to place each row; skipping them")
        return []
    files = []  # (register, its CSV file)
    for register in target.registers:
        register = {**PRESETS.get(register.get("preset"), {}), **register}
        if "name" not in register or "columns" not in register:
            print(f"  A register needs a name and columns, or a known preset: {register}")
            continue
        try:
            files.append((register, _file(register, folder)))
        except OSError as error:
            print(f"  Could not get the {register['name']} register ({error}); skipping it")
    wanted = set()
    for register, csv_path in files:
        code = register["columns"].get("postcode", "")
        wanted |= {text.postcode(row.get(code, ""), target.country)
                   for row in _rows(csv_path, register["columns"])}
    positions = geo.Postcodes(path, wanted)
    found = []
    for register, csv_path in files:
        rows = read(target, register, csv_path, positions)
        print(f"  {len(rows):,} places from the {register['name']} register")
        found += rows
    return found
