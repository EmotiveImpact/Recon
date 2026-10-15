"""US tax-exempt organisations from the IRS (federal public domain).

Two sources:

1. The Exempt Organizations Business Master File (EO BMF): every organisation
   the IRS recognises as tax-exempt, about 1.9 million. Charities, churches,
   labour unions, trade associations and chambers of commerce, social and
   sports clubs, fraternal societies, veterans' posts, youth groups and alumni
   associations. Name, address, "in care of" name, NTEE activity code and the
   501(c) subsection. No phone, email or website. Monthly.

2. The Form 990-N (e-Postcard) file: small organisations (receipts normally
   under $50,000) that file the e-Postcard instead of a full return. Gives the
   principal officer's name and address, and a website (or now and then an
   email) for some. The file holds one row per filing year, so only each
   organisation's latest filing is kept; terminated organisations and those
   that have not filed for over three years are dropped. The kind is guessed
   from the name, as this file has no activity code.

The full Form 990 e-file XML (which has phone and website for larger
organisations) is not loaded: it comes as many gigabytes of zipped XML and
the IRS index files carry only EIN, name and form type, no contact details.

Email: US organisations may be emailed under CAN-SPAM with an opt-out. Both
files share the EIN, written "EIN 12-3456789", so rows can be matched.
"""

import os
import re
import zipfile
from datetime import date
from types import SimpleNamespace

from . import download, joined, read_csv, record, rule

LICENCE = "US federal government data (public domain)"
CAN_SPAM = "US organisation: CAN-SPAM allows email with an opt-out"

BMF = SimpleNamespace(SOURCE={
    "name": "irs-eo-bmf",
    "title": "IRS Exempt Organizations Business Master File (US non-profits)",
    "country": "US",
    "url": "https://www.irs.gov/charities-non-profits/exempt-organizations-business-master-file-extract-eo-bmf",
    "licence": LICENCE,
    "updated": "monthly",
    "fields": "name, address, in care of name, 501(c) subsection, NTEE activity code, EIN",
})

EPOSTCARD = SimpleNamespace(SOURCE={
    "name": "irs-990n-epostcard",
    "title": "IRS Form 990-N e-Postcard filers (small US non-profits)",
    "country": "US",
    "url": "https://www.irs.gov/charities-non-profits/tax-exempt-organization-search-bulk-data-downloads",
    "licence": LICENCE,
    "updated": "monthly",
    "fields": "name, other names, address, principal officer, website (some), EIN",
})

BMF_FILES = [f"https://www.irs.gov/pub/irs-soi/eo{n}.csv" for n in (1, 2, 3, 4)]
EPOSTCARD_FILE = "https://apps.irs.gov/pub/epostcard/data-download-epostcard.zip"

# NTEE major groups (the letter at the start of the code), in plain words.
NTEE_GROUPS = {
    "A": "arts, culture and humanities", "B": "education", "C": "environment",
    "D": "animal welfare", "E": "health care", "F": "mental health and crisis support",
    "G": "disease and medical charities", "H": "medical research", "I": "crime and legal",
    "J": "employment and jobs", "K": "food, agriculture and nutrition", "L": "housing and shelter",
    "M": "public safety and disaster relief", "N": "sport and recreation",
    "O": "youth development", "P": "human services", "Q": "international affairs",
    "R": "civil rights and advocacy", "S": "community improvement",
    "T": "philanthropy and grant-making", "U": "science and technology",
    "V": "social science", "W": "public and society benefit", "X": "religion",
    "Y": "mutual and membership benefit", "Z": "unknown",
}

# A few finer NTEE codes worth naming because Recon targets them.
NTEE_CODES = {
    "B20": "schools", "B40": "higher education", "B41": "community colleges",
    "B42": "undergraduate colleges", "B43": "universities", "B82": "scholarships",
    "B83": "student societies, fraternities and sororities", "B84": "alumni associations",
    "J40": "labour unions", "N60": "amateur sport", "N63": "amateur sport clubs",
    "N50": "recreation clubs", "O50": "youth development programmes", "O41": "boys' and girls' clubs",
    "O42": "Scouts and Guides", "S41": "chambers of commerce and business leagues",
    "W30": "military and veterans' organisations", "Y40": "fraternal societies",
    "Y42": "domestic fraternal societies",
}

# 501(c) subsections, as kind (for the master table) and a plain label.
SUBSECTIONS = {
    "01": ("federal corporation", "corporation set up by Act of Congress"),
    "02": ("title holding company", "title-holding corporation"),
    "03": ("charity", "501(c)(3) charity"),
    "04": ("social welfare organisation", "501(c)(4) social welfare organisation"),
    "05": ("labour union", "501(c)(5) labour, agricultural or horticultural organisation"),
    "06": ("trade association", "501(c)(6) business league, chamber or trade body"),
    "07": ("social or sports club", "501(c)(7) social and recreation club"),
    "08": ("fraternal society", "501(c)(8) fraternal beneficiary society"),
    "09": ("employee benefit association", "501(c)(9) voluntary employees' benefit association"),
    "10": ("fraternal society", "501(c)(10) domestic fraternal society"),
    "11": ("teachers' retirement fund", "501(c)(11) teachers' retirement fund"),
    "12": ("mutual company", "501(c)(12) local mutual (insurance, water, telephone, electric)"),
    "13": ("cemetery company", "501(c)(13) cemetery company"),
    "14": ("credit union", "501(c)(14) state credit union or mutual reserve fund"),
    "15": ("mutual insurance company", "501(c)(15) small mutual insurance company"),
    "16": ("crop finance corporation", "501(c)(16) crop financing corporation"),
    "17": ("employee benefit trust", "501(c)(17) supplemental unemployment benefit trust"),
    "18": ("pension trust", "501(c)(18) employee-funded pension trust"),
    "19": ("veterans' organisation", "501(c)(19) veterans' organisation"),
    "20": ("legal services organisation", "501(c)(20) group legal services"),
    "21": ("benefit trust", "501(c)(21) black lung benefit trust"),
    "23": ("veterans' organisation", "501(c)(23) veterans' organisation founded before 1880"),
    "25": ("title holding company", "501(c)(25) title-holding company"),
    "26": ("state health insurance pool", "501(c)(26) state high-risk health cover"),
    "27": ("state insurance organisation", "501(c)(27) state workers' compensation"),
    "29": ("health insurance co-operative", "501(c)(29) CO-OP health insurer"),
    "40": ("religious community", "501(d) religious and apostolic association"),
    "50": ("co-operative hospital service", "501(e) co-operative hospital service organisation"),
    "60": ("school co-operative service", "501(f) co-operative service of schools"),
    "70": ("childcare organisation", "501(k) childcare organisation"),
    "71": ("charitable risk pool", "501(n) charitable risk pool"),
    "81": ("tuition programme", "529 qualified state tuition programme"),
    "82": ("ABLE programme", "529A ABLE programme"),
    "92": ("charitable trust", "4947(a)(1) non-exempt charitable trust"),
}

# Finer kinds for 501(c)(5) and (c)(6), from the CLASSIFICATION code.
# The IRS code list says 1 agricultural, 2 horticultural, 3 labour, but many
# unions sit under 1, so a union-like name or NTEE J40 also counts as a union.
CLASS_05 = {"1": "agricultural organisation", "2": "horticultural organisation", "3": "labour union"}
UNION_WORDS = re.compile(r"\b(UNION|WORKERS|EMPLOYEES|LOCAL|BROTHERHOOD|TEAMSTERS|AFL[- ]?CIO|"
                         r"FEDERATION|GUILD|FRATERNAL ORDER OF POLICE|"
                         r"TEACHERS|NURSES|FIREFIGHTERS|DEPUTIES|OFFICERS)\b")
CLASS_06 = {"1": "trade association", "2": "chamber of commerce", "3": "real estate board",
            "4": "board of trade", "5": "sports league"}

# FOUNDATION codes that change what a 501(c)(3) is.
FOUNDATIONS = {"02": "private foundation", "03": "private foundation", "04": "private foundation",
               "10": "church", "11": "school or college", "12": "hospital"}

LEGAL_FORMS = {"1": "Corporation", "2": "Trust", "3": "Co-operative", "4": "Partnership",
               "5": "Association"}

US_AREAS = {"PR", "VI", "GU", "MP", "AS", "FM", "MH", "PW", "AE", "AP", "AA", "DC"}


def ein(value):
    digits = "".join(c for c in value or "" if c.isdigit()).zfill(9)
    return f"{digits[:2]}-{digits[2:]}"


def category(ntee):
    """Plain words for an NTEE code such as 'B84' or 'N63Z'."""
    ntee = (ntee or "").strip().upper()
    if not ntee:
        return ""
    group = NTEE_GROUPS.get(ntee[0], "")
    finer = NTEE_CODES.get(ntee[:3], "")
    return joined(group, finer, sep="; ")


def _student(name):
    name = f" {name.upper()} "
    return any(w in name for w in (" STUDENT ", " STUDENTS ", "STUDENTS ASSOC", "STUDENT ASSOC",
                                   "STUDENT UNION", "STUDENTS UNION", "STUDENT GOVERNMENT"))


def _alumni(name):
    name = f" {name.upper()} "
    return " ALUMNI " in name or " ALUMNAE " in name or " ALUMNUS " in name or " ALUMNI ASS" in name


def kind(name, subsection, ntee, classification="", foundation=""):
    """What sort of organisation this is, in plain words."""
    ntee = (ntee or "").strip().upper()
    if ntee.startswith("B84") or _alumni(name):
        return "alumni association"
    if ntee.startswith("B83") or _student(name):
        return "students' organisation"
    if ntee.startswith("O"):
        return "youth organisation"
    if subsection == "05":
        if ntee.startswith("J40") or UNION_WORDS.search(name.upper()):
            return "labour union"
        return CLASS_05.get((classification or "")[:1], "labour union")
    if subsection == "06":
        return CLASS_06.get((classification or "")[:1], "trade association")
    if subsection == "03" and foundation in FOUNDATIONS:
        return FOUNDATIONS[foundation]
    if subsection in ("03", "04") and ntee.startswith("N"):
        return "sports or recreation club"
    if subsection in ("03", "04") and ntee.startswith("X"):
        return "religious organisation"
    if subsection in ("03", "04") and ntee.startswith("W30"):
        return "veterans' organisation"
    return SUBSECTIONS.get(subsection, ("non-profit", ""))[0]


def _sort_name(value):
    """The IRS "sort name" is sometimes a second name, sometimes only a lodge or
    chapter number; keep it only when it has words in it."""
    return value if re.search(r"[A-Za-z]{3}", value or "") else ""


def _bmf_rows(cache):
    for url in BMF_FILES:
        path = download(url, os.path.join(cache, url.rsplit("/", 1)[1]))
        for row in read_csv(path, encoding="latin-1"):
            state = row["STATE"].strip()
            if state:
                country, town, postcode = "US", row["CITY"], row["ZIP"]
            else:  # Abroad: the IRS puts the country in the city box.
                country, town, postcode = row["CITY"].title(), "", ""
            sub = row["SUBSECTION"].strip()
            label = SUBSECTIONS.get(sub, ("", f"subsection {sub}"))[1]
            can, why = rule(country, None, CAN_SPAM)
            yield record(
                BMF.SOURCE, row["EIN"], row["NAME"], other_name=_sort_name(row["SORT_NAME"]),
                kind=kind(row["NAME"], sub, row["NTEE_CD"], row["CLASSIFICATION"],
                          row["FOUNDATION"].strip()),
                category=joined(category(row["NTEE_CD"]), label, sep="; "),
                legal_form=LEGAL_FORMS.get(row["ORGANIZATION"].strip(), ""),
                status="Tax-exempt", address=row["STREET"], town=town, region=state,
                postcode=postcode, country=country,
                people=row["ICO"].lstrip("% ").strip(),
                registration_number=f"EIN {ein(row['EIN'])}", can_email=can, rule_reason=why)


_URL = re.compile(r"(https?://[^\s|()]+|(?:[\w-]+\.)+[a-z]{2,}(?:/[^\s|()]*)?)", re.I)


_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")

# Email providers people type into the website box by mistake.
WEBMAIL = {"gmail.com", "yahoo.com", "hotmail.com", "aol.com", "outlook.com", "live.com",
           "msn.com", "icloud.com", "comcast.net", "att.net", "verizon.net", "sbcglobal.net",
           "bellsouth.net", "charter.net", "cox.net", "earthlink.net", "me.com", "ymail.com",
           "protonmail.com", "mail.com", "gmx.com", "frontier.com", "windstream.net"}


def _website(value):
    """The first web address in the e-Postcard website box, which sometimes
    holds a firm's name, a sentence or an email address instead."""
    value = _EMAIL.sub(" ", value or "")
    match = _URL.search(value)
    if not match:
        return ""
    host = match.group(1).lower().split("://")[-1].split("/")[0]
    host = host[4:] if host.startswith("www.") else host
    return "" if host in WEBMAIL else match.group(1)


# Name words that show what a small organisation is, checked in this order.
NAME_KINDS = [
    (r"\b(PTA|PTO|PTSA|PARENT TEACHER|PARENTS? (AND|&) TEACHERS?)\b", "parent-teacher association"),
    (r"\bBOOSTERS?\b", "booster club"),
    (r"\b(SCOUTS?|SCOUTING|4-H|LITTLE LEAGUE|YOUTH|BOYS (AND|&) GIRLS CLUB)\b", "youth organisation"),
    (r"\b(VFW|VETERANS|AMERICAN LEGION|AMVETS|DISABLED AMERICAN VETERANS)\b", "veterans' organisation"),
    (r"\bCHAMBER OF COMMERCE\b", "chamber of commerce"),
    (r"\b(LOCAL \d+|LABOR UNION|TRADES COUNCIL|BROTHERHOOD OF|TEAMSTERS|AFL[- ]?CIO)\b", "labour union"),
    (r"\b(LODGE|GRANGE|MASONIC|ELKS|MOOSE|EAGLES|KNIGHTS OF|ODD FELLOWS|SHRINERS)\b", "fraternal society"),
    (r"\b(CHURCH|MINISTRY|MINISTRIES|CHAPEL|PARISH|TEMPLE|MOSQUE|SYNAGOGUE)\b", "religious organisation"),
    (r"\b(SOCCER|FOOTBALL|BASEBALL|SOFTBALL|BASKETBALL|HOCKEY|LACROSSE|VOLLEYBALL|SWIM|"
     r"WRESTLING|RUGBY|TENNIS|GOLF|ATHLETIC|SPORTS?|ROD (AND|&) GUN|GUN CLUB|RIDING|SKI)\b",
     "sports or recreation club"),
    (r"\b(ASSOCIATION OF|SOCIETY OF|INSTITUTE OF)\b.*\b(PROFESSIONALS|ENGINEERS|ACCOUNTANTS|"
     r"MANAGERS|NURSES|REALTORS|CONTRACTORS|PLANNERS|ARCHITECTS)\b", "professional association"),
    (r"\bCLUB\b", "social or sports club"),
]
NAME_KINDS = [(re.compile(pattern), label) for pattern, label in NAME_KINDS]


def kind_from_name(name):
    """A best guess at what a small organisation is, from its name alone."""
    found = kind(name, "", "")
    if found != "non-profit":
        return found
    upper = (name or "").upper()
    for pattern, label in NAME_KINDS:
        if pattern.search(upper):
            return label
    return "non-profit"


def _epostcard_rows(cache):
    path = download(EPOSTCARD_FILE, os.path.join(cache, "data-download-epostcard.zip"))
    latest = {}  # EIN -> (year, raw line): the raw line keeps memory low.
    with zipfile.ZipFile(path) as archive:
        with archive.open(archive.namelist()[0]) as handle:
            for raw in handle:
                parts = raw.split(b"|", 2)
                if len(parts) < 3:
                    continue
                key, year = parts[0], parts[1]
                if key not in latest or year >= latest[key][0]:
                    latest[key] = (year, raw)
    oldest = date.today().year - 3
    for _year, raw in latest.values():
        parts = raw.decode("latin-1").rstrip("\r\n").split("|")
        if len(parts) < 26:
            continue
        if len(parts) > 26:  # A stray pipe inside the website box: keep the ends lined up.
            parts = parts[:7] + ["|".join(parts[7:len(parts) - 18])] + parts[-18:]
        (number, year, name, _small, terminated, _begin, _end, website, officer,
         _o1, _o2, _ocity, _oprov, _ostate, _ozip, _ocountry,
         street1, street2, city, province, state, postcode, country,
         dba1, dba2, dba3) = parts
        # Terminated, or silent for over three years (the IRS then revokes exemption).
        if terminated.strip().upper() == "T" or not year.isdigit() or int(year) < oldest:
            continue
        country = "US" if country.strip() in ("", "US") else country.strip()
        can, why = rule(country, None, CAN_SPAM)
        yield record(
            EPOSTCARD.SOURCE, number, name, other_name=joined(dba1, dba2, dba3, sep="; "),
            kind=kind_from_name(name), category="small non-profit (990-N filer)",
            status=f"Filed 990-N for {year}", address=joined(street1, street2),
            town=city, region=state or province, postcode=postcode, country=country,
            website=_website(website), emails=_EMAIL.findall(website), people=officer.strip(),
            registration_number=f"EIN {ein(number)}", can_email=can, rule_reason=why)


BMF.rows = _bmf_rows
EPOSTCARD.rows = _epostcard_rows

SOURCES = [BMF, EPOSTCARD]
