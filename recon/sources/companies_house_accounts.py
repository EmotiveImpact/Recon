"""Companies House free accounts data (the accounts companies filed online).

Most small UK companies file their yearly accounts as tagged web pages (iXBRL),
and Companies House publishes every one filed in a month as a free download.
From each set of accounts this loader reads four things: the company's name,
the average number of staff during the year, the turnover when the company
gave it (most small companies don't have to), and the name of the director who
signed the accounts. No addresses or contact details: the record joins the
company's other entries in the master table on its company number.

Only the newest monthly archive is used (about 3 GB zipped, 380,000 sets of
accounts, roughly a tenth of all companies). Each file is read straight out of
the zip, never unpacked. A company that filed twice in the month keeps its
newest accounts. Community interest companies' accounts come as a small zip
inside the archive and are read the same way.

Companies House publishes the archive free of charge for anyone to reuse as
public register data. The directors are named people, so their names count as
personal data under UK GDPR: use them to address a letter or email to the right
person at a company, not to market to them as individuals.
"""

import glob
import html
import io
import itertools
import os
import re
import urllib.request
import zipfile

from . import USER_AGENT, download, record, rule
from .companies_house_psc import fetched_copy

SOURCE = {
    "name": "companies-house-accounts",
    "title": "Companies House accounts data",
    "country": "GB",
    "url": "https://download.companieshouse.gov.uk/en_monthlyaccountsdata.html",
    "licence": "Companies House public register data, free to reuse (directors' names are personal data)",
    "updated": "monthly",
    "fields": "company name and number, average staff, turnover, director who signed the accounts",
    "enrich_only": True,  # Added to companies found elsewhere, never on its own.
}

_LINK = re.compile(r'href="(Accounts_Monthly_Data-([A-Za-z]+)(\d{4})\.zip)"')
_MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august",
           "september", "october", "november", "december"]

# File names look like Prod224_2609_00000371_20251231.html: the company
# number, then the date of the balance sheet.
_FILE = re.compile(r"_([A-Z0-9]{8})_(\d{8})(?:_[A-Z]+)?\.(html|xhtml|xml|zip)$", re.I)

WANTED = ("AverageNumberEmployeesDuringPeriod", "TurnoverRevenue", "Turnover",
          "DirectorSigningFinancialStatements", "NameEntityOfficer",
          "EntityCurrentLegalOrRegisteredName")
# A tagged fact in iXBRL (<ix:nonFraction name="uk-core:Turnover" ...>) or in
# plain XBRL (<uk-core:Turnover contextRef=...>).
_IX_FACT = re.compile(
    r"<ix:(nonFraction|nonNumeric)\b([^>]*?\bname=\"[\w.-]+:(%s)\"[^>]*?)(?:/>|>(.*?)</ix:\1>)"
    % "|".join(WANTED), re.S)
_XML_FACT = re.compile(r"<([\w.-]+):(%s)\b([^>]*?)(?:/>|>(.*?)</\1:\2>)" % "|".join(WANTED), re.S)
_CONTEXT = re.compile(r"<(?:[\w-]+:)?context\b[^>]*\bid=\"([^\"]+)\"(.*?)</(?:[\w-]+:)?context>", re.S)
_DATE = re.compile(r"<(?:[\w-]+:)?(?:endDate|instant)>\s*([\d-]+)\s*<")
_ATTR = re.compile(r"([\w:-]+)=\"([^\"]*)\"")
_TAGS = re.compile(r"<[^>]+>")


def latest_zip(cache):
    """The newest monthly archive: one already fetched into the incoming
    folder, else one in the cache, else downloaded."""
    month = lambda path: _month_key(os.path.basename(path))  # noqa: E731
    found = fetched_copy(SOURCE["name"], "Accounts_Monthly_Data-*.zip", key=month)
    if found:
        return found
    found = glob.glob(os.path.join(cache, "Accounts_Monthly_Data-*.zip"))
    if found:
        return max(found, key=lambda path: _month_key(os.path.basename(path)))
    request = urllib.request.Request(SOURCE["url"], headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        links = _LINK.findall(response.read().decode("utf-8", "replace"))
    if not links:
        raise RuntimeError("No monthly accounts archive listed on the Companies House download page")
    name = max(links, key=lambda link: _month_key(link[0]))[0]
    return download("https://download.companieshouse.gov.uk/" + name, os.path.join(cache, name))


def _month_key(name):
    found = _LINK.search(f'href="{name}"')
    if not found or found.group(2).lower() not in _MONTHS:
        return (0, 0)
    return (int(found.group(3)), _MONTHS.index(found.group(2).lower()))


def _text(value):
    return " ".join(html.unescape(_TAGS.sub(" ", value or "")).split())


def _number(text, attrs):
    """The value of a numeric fact, allowing for scale, sign and dashes
    that stand for nought."""
    digits = re.sub(r"[^\d.]", "", text.replace(",", ""))
    if not digits:
        return 0.0 if text.strip() in ("-", "–", "nil", "") else None
    try:
        value = float(digits) * 10 ** int(attrs.get("scale") or 0)
    except ValueError:
        return None
    return -value if attrs.get("sign") == "-" else value


def facts(document):
    """The wanted facts of one set of accounts: {name: [(context, attrs, text)]},
    plus the contexts as {id: (period end, has a dimension)}."""
    found = {}
    matches = [(m.group(3), m.group(2), m.group(4)) for m in _IX_FACT.finditer(document)]
    if not matches:
        matches = [(m.group(2), m.group(3), m.group(4)) for m in _XML_FACT.finditer(document)]
    for name, attributes, value in matches:
        attrs = dict(_ATTR.findall(attributes))
        found.setdefault(name, []).append((attrs.get("contextRef", ""), attrs, _text(value)))
    contexts = {}
    for m in _CONTEXT.finditer(document):
        dates = _DATE.findall(m.group(2))
        contexts[m.group(1)] = (max(dates) if dates else "", "segment" in m.group(2).lower()
                                or "scenario" in m.group(2).lower())
    return found, contexts


def _current(values, contexts):
    """The figure for the latest period, ignoring breakdowns by dimension."""
    best = None
    for context, attrs, text in values:
        end, split = contexts.get(context, ("", False))
        number = _number(text, attrs)
        if split or number is None:
            continue
        if best is None or end > best[0]:
            best = (end, number)
    return best[1] if best else None


def _person(name):
    name = " ".join((name or "").split())
    if name.isupper():
        name = name.title()
    return "" if name.lower() in ("", "vacant", "director", "n/a") else name


def signer(found):
    """The name of the director who signed the accounts."""
    officers = {context: text for context, _, text in found.get("NameEntityOfficer", [])}
    for context, _, text in found.get("DirectorSigningFinancialStatements", []):
        name = _person(officers.get(context) or text)
        if name:
            return name
    return ""


def money(value):
    """£1.2m, £350k or £800."""
    value = abs(value)
    if value >= 1_000_000_000:
        return f"£{value / 1e9:.1f}bn".replace(".0bn", "bn")
    if value >= 1_000_000:
        return f"£{value / 1e6:.1f}m".replace(".0m", "m")
    if value >= 1000:
        return f"£{value / 1000:.0f}k"
    return f"£{value:.0f}"


def summary(document):
    """(name, staff, turnover, signer) from one set of accounts."""
    found, contexts = facts(document)
    names = [text for _, _, text in found.get("EntityCurrentLegalOrRegisteredName", []) if text]
    staff = _current(found.get("AverageNumberEmployeesDuringPeriod", []), contexts)
    turnover = _current(found.get("TurnoverRevenue", []) or found.get("Turnover", []), contexts)
    return (names[0] if names else ""), staff, turnover, signer(found)


def to_record(company, name, staff, turnover, director, period=""):
    words = []
    if staff is not None:
        staff = round(staff)
        words.append("no staff" if staff == 0 else "1 member of staff" if staff == 1
                     else f"about {staff:,} staff")
    if turnover:
        words.append(f"turnover {money(turnover)}")
    can, why = rule("GB", True, "company on Companies House: a corporate body under PECR")
    return record(SOURCE, company, name, kind="company", category="; ".join(words), country="GB",
                  people=f"{director} (director who signed the accounts)" if director else "",
                  registration_number=company, company_number=company,
                  status=f"accounts to {period[:4]}-{period[4:6]}-{period[6:]}" if period else "",
                  can_email=can, rule_reason=why)


def _documents(archive, info):
    """The text of the accounts in one archive entry (a community interest
    company's accounts come as a zip holding the accounts and a CIC report)."""
    data = archive.read(info)
    if not info.filename.lower().endswith(".zip"):
        yield data.decode("utf-8", "replace")
        return
    with zipfile.ZipFile(io.BytesIO(data)) as inner:
        for name in inner.namelist():
            lowered = name.lower()
            if lowered.endswith((".html", ".xhtml", ".xml")) and "cic34" not in lowered:
                yield inner.read(name).decode("utf-8", "replace")


def rows(cache):
    path = latest_zip(cache)
    with zipfile.ZipFile(path) as archive:
        entries = []
        for info in archive.infolist():
            found = _FILE.search(info.filename)
            if found:
                entries.append((found.group(1).upper(), found.group(2), info))
        entries.sort(key=lambda entry: (entry[0], entry[1]))
        for company, group in itertools.groupby(entries, key=lambda entry: entry[0]):
            # Newest accounts first; older ones only fill gaps.
            for _, period, info in reversed(list(group)):
                name, staff, turnover, director = "", None, None, ""
                for document in _documents(archive, info):
                    n, s, t, d = summary(document)
                    name, director = name or n, director or d
                    staff = staff if staff is not None else s
                    turnover = turnover if turnover is not None else t
                yield to_record(company, name, staff, turnover, director, period)
                break
