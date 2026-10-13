"""Certification Officer's lists of trade unions and employers' associations
(Great Britain, Open Government Licence v3.0).

About 125 listed trade unions and 35 listed employers' associations. The lists
on GOV.UK give only names, but each body files a yearly return (form AR21 for
unions, AR27 for employers' associations) published as a PDF, and its first
page gives the head office address, website, general secretary, telephone
number and a contact email. We read that first page with pdftotext.

Most of these bodies are unincorporated associations, so they are "post only"
under PECR. Special register bodies (incorporated professional bodies such as
the British Medical Association) and bodies whose name ends in Ltd or Limited
are companies and may be emailed.

This module covers two lists, so it exposes SOURCES rather than SOURCE/rows.
"""

import html
import os
import re
import shutil
import subprocess
import types

from . import corporate_name, download, joined, record, rule

GOVUK = "https://www.gov.uk"
LICENCE = "Open Government Licence v3.0"

UNIONS_SOURCE = {
    "name": "certification-officer-unions",
    "title": "Certification Officer: list of trade unions (Great Britain)",
    "country": "GB",
    "url": GOVUK + "/government/publications/official-list-of-trade-unions/current-trade-unions",
    "licence": LICENCE,
    "updated": "as unions are listed or removed; returns yearly",
    "fields": "name, independence, head office address, website, general secretary, phone, email",
}

EMPLOYERS_SOURCE = {
    "name": "certification-officer-employers",
    "title": "Certification Officer: list of employers' associations (Great Britain)",
    "country": "GB",
    "url": GOVUK + "/government/publications/official-list-of-employers-associations/"
                   "current-employers-associations",
    "licence": LICENCE,
    "updated": "as associations are listed or removed; returns yearly",
    "fields": "name, head office address, website, chief officer, phone, email",
}

# Special register bodies: incorporated (by Royal Charter or under the
# Companies Acts) before 1971 and treated as trade unions. The Certification
# Officer's annual report names them; the GOV.UK list does not, so we keep the
# names here. Matched loosely on the start of the name.
SPECIAL_REGISTER = (
    "british association of occupational therapists", "british dental association",
    "british dietetic association", "british medical association",
    "british orthoptic society", "chartered society of physiotherapy",
    "royal college of midwives", "royal college of nursing", "royal college of podiatry",
    "society of radiographers",
)


def _clean(value):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", value or "")).split())


def entries(page):
    """(name, independent, link) for each body on a GOV.UK list page."""
    start = page.find('class="govspeak"')
    end = page.find("</main>", start)
    body = page[start:end] if start >= 0 else page
    for para in re.findall(r"<p>(.*?)</p>", body, re.S):
        link = re.search(r'<a href="([^"]+)"', para)
        name = _clean(para)
        if not link or "/government/collections/" not in link.group(1):
            continue
        independent = name.startswith("*")
        yield name.lstrip("*").strip(), independent, link.group(1)


def _absolute(link):
    return link if link.startswith("http") else GOVUK + link


def _read(path):
    with open(path, encoding="utf-8", errors="replace") as handle:
        return handle.read()


def returns(collection, cache, slug, tries=3):
    """(path, link) of the newest few annual return PDFs for a body, newest
    first. Older ones are a fallback for when the newest is a scan."""
    page = _read(download(_absolute(collection), os.path.join(cache, "bodies", slug + ".html")))
    found = re.search(r'href="([^"]*/government/publications/[^"]*annual-return[^"]*)"', page)
    if not found:
        return
    listing = _read(download(_absolute(found.group(1)), os.path.join(cache, "bodies", slug + "-ar.html")))
    pdfs = re.findall(r'href="(https://assets\.publishing\.service\.gov\.uk/[^"]+\.pdf)"', listing)
    for number, link in enumerate(dict.fromkeys(pdfs)):
        if number >= tries:
            return
        try:
            yield download(link, os.path.join(cache, "returns", f"{slug}-{number}.pdf")), link
        except OSError:
            continue


def best_return(collection, cache, slug):
    """Details from the newest return whose first page has readable text,
    and the link to that return."""
    for path, link in returns(collection, cache, slug):
        details = parse_return(first_page(path))
        if details["address"] or details["postcode"] or details["website"]:
            return details, link
    return parse_return(""), None


def first_page(pdf):
    """Text of the first two pages, keeping the layout, or "" when the PDF
    is a scan or pdftotext is missing."""
    if not shutil.which("pdftotext"):
        return ""
    try:
        done = subprocess.run(["pdftotext", "-layout", "-l", "2", pdf, "-"],
                              capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return done.stdout.decode("utf-8", "replace")


LABELS = re.compile(r"^(name of|year ended|list no|head or main|website|has the address|"
                    r"general secretary|chief executive|secretary|telephone|contact name|"
                    r"the completion|e-?mail|please|any difficulties|officer as|you should|"
                    r"returns@|p\d|form ar|docusign|annual return|trade union and)", re.I)


def parse_return(text):
    """Head office address, postcode, website, general secretary, phones and
    email from the first page of an AR21 or AR27 return."""
    found = {"address": [], "postcode": "", "website": "", "people": "", "phones": [], "emails": []}
    in_address = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = re.split(r"\s{2,}", line, maxsplit=1)
        label, value = (parts[0], parts[1].strip()) if len(parts) == 2 else (parts[0], "")
        label_l = label.lower()
        if label_l.startswith("postcode"):
            found["postcode"] = joined(label[8:].strip(" :"), value, sep=" ")
            in_address = False
            continue
        if label_l.startswith("head or main office"):
            in_address = True
            if value:
                found["address"].append(value)
            continue
        if in_address:
            if LABELS.match(line):
                in_address = False
            elif raw.startswith(" " * 20):  # A continuation line, value column only.
                found["address"].append(line)
                continue
            else:
                in_address = False
        if label_l.startswith("website") and value and not found["website"]:
            if re.search(r"[a-z0-9-]+\.[a-z]{2,}", value, re.I) and "n/a" not in value.lower():
                found["website"] = value.split()[0]
        elif re.match(r"(general secretary|chief executive|secretary)\b", label_l) and value:
            person = re.sub(r"\s*\(.*?\)\s*", " ", value).strip()
            if not found["people"] and re.search(r"[a-z]{2}", person, re.I) and not re.match(
                    r"(n/?a|none|vacant|tbc)\b", person, re.I):
                found["people"] = f"{person.title() if person.isupper() else person} ({label.strip(': ')})"
        elif label_l.startswith("telephone") and value:
            found["phones"].append(value)
        elif label_l.startswith("e-mail") or label_l.startswith("email"):
            found["emails"].extend(re.findall(r"[\w.+'-]+@[\w-]+(?:\.[\w-]+)+", value))
        if "certoffice.org" in line or "0330 109 3602" in line:
            break  # The rest of the page is the Certification Officer's own details.
    return found


def _split_address(lines, name):
    """Drop a repeat of the body's own name, then take the last line as the town."""
    lines = [l for l in lines if l.strip(" ,").lower() != name.lower()]
    lines = [l.strip(" ,") for l in lines if l.strip(" ,")]
    if not lines:
        return "", ""
    if len(lines) == 1:
        return lines[0], ""
    return joined(*lines[:-1]), lines[-1]


def special_register(name):
    lowered = name.lower()
    return any(lowered.startswith(prefix) for prefix in SPECIAL_REGISTER)


def _rows(source, kind, cache):
    page = _read(download(source["url"], os.path.join(cache, source["name"] + ".html")))
    for name, independent, link in entries(page):
        slug = re.sub(r"-(information-held-by|annual-returns-to)-the-certification-officer$", "",
                      link.rstrip("/").rsplit("/", 1)[-1])
        details, return_link = best_return(link, cache, slug)
        address, town = _split_address(details["address"], name)
        if special_register(name):
            legal_form = "special register body"
            can, why = rule("GB", True, "special register body: an incorporated body under PECR")
        elif corporate_name(name):
            legal_form = "company"
            can, why = rule("GB", True, "incorporated company: a corporate body under PECR")
        else:
            legal_form = "unincorporated association"
            can, why = rule("GB", False, "unincorporated association: post only under PECR")
        status = "Listed" + ("; certificate of independence" if independent else "")
        yield record(
            source, slug, name, kind=kind, legal_form=legal_form, status=status,
            address=address, town=town, postcode=details["postcode"], country="GB",
            website=details["website"], emails=details["emails"], phones=details["phones"],
            people=details["people"], can_email=can, rule_reason=why,
            source_url=return_link or _absolute(link))


def union_rows(cache):
    yield from _rows(UNIONS_SOURCE, "trade union", cache)


def employer_rows(cache):
    yield from _rows(EMPLOYERS_SOURCE, "employers' association", cache)


SOURCES = [
    types.SimpleNamespace(SOURCE=UNIONS_SOURCE, rows=union_rows),
    types.SimpleNamespace(SOURCE=EMPLOYERS_SOURCE, rows=employer_rows),
]
