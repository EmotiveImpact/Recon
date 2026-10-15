"""Office for Students Register of English higher education providers (OGL v3).

Every university, college and private provider registered with the OfS in
England (about 430), with its legal and trading names, UKPRN, address,
website and, for most, a public enquiries email. The register is a live
spreadsheet: one sheet of registered providers, then sheets of removed and
suspended ones. Providers whose registration is currently suspended are left
out.
"""

import os
import re
import zipfile
import xml.etree.ElementTree as ET

from . import corporate_name, download, joined, record, rule, text

SOURCE = {
    "name": "ofs-register",
    "title": "Office for Students Register of higher education providers (England)",
    "country": "GB",
    "url": "https://www.officeforstudents.org.uk/for-providers/the-ofs-register/",
    "licence": "Open Government Licence v3.0",
    "updated": "continually",
    "fields": "legal and trading names, UKPRN, address, email, website, charity status, "
              "registration category, degree awarding powers, university title",
}

DOWNLOAD = "https://register-api.officeforstudents.org.uk/api/Download/"

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def _column(ref):
    """'BQ4' -> 68 (0-based column number)."""
    number = 0
    for letter in re.match(r"[A-Z]+", ref).group():
        number = number * 26 + ord(letter) - 64
    return number - 1


def xlsx_sheets(path):
    """{sheet name: list of rows (lists of text)} from an .xlsx file, using
    only the standard library."""
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            for item in ET.parse(z.open("xl/sharedStrings.xml")).getroot():
                shared.append("".join(t.text or "" for t in item.iter(_NS + "t")))
        targets = {}
        for rel in ET.parse(z.open("xl/_rels/workbook.xml.rels")).getroot():
            targets[rel.get("Id")] = rel.get("Target").lstrip("/")
        sheets = {}
        for sheet in ET.parse(z.open("xl/workbook.xml")).getroot().iter(_NS + "sheet"):
            target = targets[sheet.get(_REL)]
            target = target if target.startswith("xl/") else "xl/" + target
            table = []
            for row in ET.parse(z.open(target)).getroot().iter(_NS + "row"):
                values = {}
                for cell in row.iter(_NS + "c"):
                    kind, value = cell.get("t"), cell.find(_NS + "v")
                    if kind == "s" and value is not None:
                        found = shared[int(value.text)]
                    elif kind == "inlineStr":
                        found = "".join(t.text or "" for t in cell.iter(_NS + "t"))
                    else:
                        found = value.text if value is not None else ""
                    values[_column(cell.get("r"))] = found or ""
                width = max(values, default=-1) + 1
                table.append([values.get(i, "") for i in range(width)])
            sheets[sheet.get("name")] = table
    return sheets


def _clean(name):
    return " ".join(name.replace("’", "'").replace("‘", "'").split()).lower()


def table(rows, first_heading):
    """Rows as dicts, starting under the heading row whose first cell matches."""
    for start, row in enumerate(rows):
        if row and _clean(row[0]) == first_heading:
            headings = [_clean(h) for h in row]
            for values in rows[start + 1:]:
                if any(v.strip() for v in values):
                    yield dict(zip(headings, values + [""] * (len(headings) - len(values))))
            return


def _value(row, key):
    value = " ".join((row.get(key) or "").split())
    return "" if value.lower() in ("not applicable", "none", "n/a") else value


def suspended(sheets):
    ukprns = set()
    for name, rows in sheets.items():
        if "suspension" not in name.lower():
            continue
        for row in table(rows, "provider's legal name"):
            active = row.get("active suspension of registration", "").strip().lower()
            if active.startswith("yes") or not row.get("suspension end date", "").strip():
                ukprns.add(_value(row, "provider's ukprn"))
    return ukprns


def rows(cache):
    path = download(DOWNLOAD, os.path.join(cache, "ofs-register.xlsx"))
    sheets = xlsx_sheets(path)
    register = sheets.get("Register") or next(iter(sheets.values()))
    held_back = suspended(sheets)
    for row in table(register, "provider's legal name"):
        name = _value(row, "provider's legal name")
        ukprn = _value(row, "provider's ukprn")
        if not name or not ukprn or ukprn in held_back:
            continue
        university = _value(row, "does the provider have the right to use 'university' in its title?")
        how = _value(row, "how did the provider gain the right to use 'university' in its title?")
        charity = _value(row, "is the provider an exempt or registered charity?")
        # Universities, colleges and the private providers on the register are
        # chartered, statutory or registered corporations. A provider is post
        # only only if its name shows it is a sole trader; a college called
        # "Partnership", such as TEC Partnership, is still a corporation.
        plainly_not = re.search(r"\b(sole trader|t/a|trading as)\b", name, re.I) \
            and not corporate_name(name)
        can, why = rule("GB", not plainly_not,
                        "higher education provider: a corporate body under PECR" if not plainly_not
                        else "provider looks like a sole trader: post only")
        lines = [line.strip() for line in
                 (row.get("provider's contact address") or "").splitlines() if line.strip()]
        if lines and lines[-1].lower() in ("united kingdom", "uk", "england"):
            lines = lines[:-1]
        postcode = text.postcode(lines[-1], "GB") if lines else ""
        if postcode:
            lines = lines[:-1]
        trading = [n.strip() for n in re.split(r"[\n;]", row.get("provider's trading name(s)") or "")]
        trading = [n for n in trading if n and n.lower() not in ("not applicable", "none")]
        yield record(
            SOURCE, ukprn, name, other_name=trading,
            kind="university" if university.lower().startswith("yes") else "higher education provider",
            category=joined(_value(row, "category in which the provider is registered"),
                            _value(row, "highest level of degree awarding powers held") and
                            "degree awarding powers: " + _value(row, "highest level of degree awarding powers held"),
                            how and "university title: " + how, sep="; "),
            legal_form=joined(how, f"charity: {charity}" if charity else "", sep="; "),
            status="registered", address=joined(*lines[:-1]), town=lines[-1] if lines else "",
            postcode=postcode, country="GB", website=_value(row, "provider's website"),
            emails=_value(row, "provider's email address"),
            registration_number=f"UKPRN {ukprn}", can_email=can, rule_reason=why)
