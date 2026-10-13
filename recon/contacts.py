"""Every way to reach a business, labelled: emails, phones and social links.

Edem asked to see all of it (13 October 2026) so decisions can be made with
the full picture. Seeing is not permission: the contact_rule column still
decides who may be emailed, and phone numbers must be screened against the
TPS and CTPS before anyone rings them (docs/RULES.md).
"""

import json
import os
import re
import time
import urllib.request

from . import patterns, text

# Free email providers: an address here is a person's own mailbox.
FREE_MAIL = {
    "gmail.com", "googlemail.com", "hotmail.com", "hotmail.co.uk", "outlook.com",
    "outlook.co.uk", "live.com", "live.co.uk", "msn.com", "yahoo.com", "yahoo.co.uk",
    "ymail.com", "rocketmail.com", "icloud.com", "me.com", "mac.com", "aol.com", "aol.co.uk",
    "btinternet.com", "btopenworld.com", "sky.com", "talktalk.net", "virginmedia.com",
    "ntlworld.com", "blueyonder.co.uk", "tiscali.co.uk", "protonmail.com", "proton.me",
    "gmx.com", "gmx.co.uk", "mail.com", "zoho.com", "yandex.com", "comcast.net",
    "att.net", "verizon.net", "sbcglobal.net", "bellsouth.net", "cox.net",
}

PERSONAL = "personal"            # A free-mail address such as jo@gmail.com.
SHARED = "shared inbox"          # info@, bookings@ and the like.
NAMED = "named person"           # sarah@ on the business's own domain.
OTHER = "other business domain"  # Someone else's domain, such as a group or agency.

SOCIAL_SITES = ("instagram.com", "facebook.com", "fb.com", "tiktok.com", "x.com",
                "twitter.com", "linkedin.com", "youtube.com", "pinterest.com",
                "pinterest.co.uk", "threads.net", "snapchat.com")
_NOT_A_PROFILE = re.compile(r"/(sharer|share|intent|plugins|dialog|tr)\b|[?&]u=", re.I)


# Stricter checks that an address could be real, after the ideas in
# email-validator (Unlicense); written fresh.
_LOCAL = re.compile(r"^[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]+$")
_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
PLACEHOLDERS = {"name", "your", "yourname", "you", "email", "user", "username", "example",
                "firstname", "firstlast", "first.last", "firstname.lastname", "someone",
                "johndoe", "john.doe", "jane.doe", "test"}
# Throwaway mailboxes, which nobody reads for long. A short list of the most
# common; the full public list is downloaded to data/ (see fetch_lists).
THROWAWAY = {"mailinator.com", "guerrillamail.com", "10minutemail.com", "tempmail.com",
             "temp-mail.org", "yopmail.com", "trashmail.com", "sharklasers.com",
             "getnada.com", "dispostable.com", "maildrop.cc", "throwawaymail.com",
             "fakeinbox.com", "mintemail.com", "mailnesia.com", "tempr.email"}
_THROWAWAY_FILE = os.path.join("data", "disposable_domains.txt")
_FREE_MAIL_FILE = os.path.join("data", "free_email_domains.txt")

# Fuller public lists, downloaded when first needed and kept for a month:
# throwaway domains from disposable-email-domains (CC0) and free mail
# providers from Kiko Beats' free-email-domains (MIT, 32,000 domains such as
# btconnect.com and talk21.com). Without them the short lists above are used.
LIST_URLS = {
    _THROWAWAY_FILE: "https://raw.githubusercontent.com/disposable-email-domains/"
                     "disposable-email-domains/main/disposable_email_blocklist.conf",
    _FREE_MAIL_FILE: "https://raw.githubusercontent.com/Kikobeats/free-email-domains/"
                     "master/domains.json",
}


def fetch_lists(days=30):
    """Download the public domain lists to data/ when missing or old."""
    for path, url in LIST_URLS.items():
        if os.path.exists(path) and time.time() - os.path.getmtime(path) < days * 86400:
            continue
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Recon"})
            with urllib.request.urlopen(request, timeout=60) as response:
                body = response.read().decode("utf-8", "replace")
            found = json.loads(body) if body.lstrip().startswith("[") else body.splitlines()
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path + ".part", "w", encoding="utf-8") as out:
                out.write("\n".join(d.strip().lower() for d in found if d.strip()) + "\n")
            os.replace(path + ".part", path)
        except (OSError, ValueError) as error:
            print(f"  Could not fetch {url} ({error}); using the short built-in list")


def _domain_file(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return {line.strip().lower() for line in handle
                    if line.strip() and not line.startswith("#")}
    except OSError:
        return set()


def _throwaway():
    if not hasattr(_throwaway, "domains"):
        _throwaway.domains = THROWAWAY | _domain_file(_THROWAWAY_FILE)
    return _throwaway.domains


def _free_mail():
    if not hasattr(_free_mail, "domains"):
        _free_mail.domains = FREE_MAIL | _domain_file(_FREE_MAIL_FILE)
    return _free_mail.domains


def valid_email(address):
    """True when an address could really exist and be read."""
    address = (address or "").strip().lower()
    if address.count("@") != 1 or len(address) > 254:
        return False
    local, host = address.split("@")
    if not 0 < len(local) <= 64 or not _LOCAL.match(local):
        return False
    if local.startswith(".") or local.endswith(".") or ".." in local:
        return False
    if local in PLACEHOLDERS:
        return False
    labels = host.split(".")
    if len(labels) < 2 or not all(_LABEL.match(label) for label in labels):
        return False
    tld = labels[-1]
    if not (tld.isalpha() and 2 <= len(tld) <= 24) and not tld.startswith("xn--"):
        return False
    return host not in _throwaway()


def email_label(address, site=""):
    local, _, host = address.lower().partition("@")
    if host in _free_mail():
        return PERSONAL
    if patterns.is_role(local):
        return SHARED
    if site and (host == site or host.endswith("." + site)):
        return NAMED
    return OTHER


def split(value):
    """'a (x); b (y)' -> ['a', 'b']: the items in a labelled list column."""
    return [item.split(" (")[0].strip() for item in (value or "").split(";") if item.strip()]


def add_emails(place, addresses, site=""):
    """Add addresses to all_emails, each with its label, without repeats."""
    known = split(place["all_emails"])
    for address in addresses:
        address = address.strip().lower()
        if valid_email(address) and address not in known:
            known.append(address)
    place["all_emails"] = "; ".join(f"{a} ({email_label(a, site)})" for a in known)


def social_link(url):
    """The tidy profile link, or '' when the URL is not a social profile."""
    host = text.domain(url)
    if not any(host == s or host.endswith("." + s) for s in SOCIAL_SITES):
        return ""
    if _NOT_A_PROFILE.search(url):
        return ""
    url = url if "://" in url else "https://" + url
    return url.split("?")[0].split("#")[0].rstrip("/")


def add_socials(place, links):
    known = place["socials"].split() if place["socials"] else []
    for link in links:
        tidy = social_link(link)
        if tidy and tidy.lower() not in {k.lower() for k in known}:
            known.append(tidy)
    place["socials"] = " ".join(known)


# UK phone numbers, by how they start once written as 0...
MOBILE, LANDLINE, NON_GEO, OTHER_PHONE = "mobile", "landline", "non-geographic", "other"


def uk_phone(raw):
    """(tidy number, kind) for a UK number, or ('', '') if it is not one."""
    digits = re.sub(r"[^\d+]", "", raw or "")
    if digits.startswith("+44"):
        rest = digits[3:]
    elif digits.startswith("0044"):
        rest = digits[4:]
    elif digits.startswith("0") and not digits.startswith("00"):
        rest = digits[1:]
    else:
        return "", ""  # Another country's number, or not a number.
    digits = "0" + rest.lstrip("0")  # '+44 (0)20 ...' has a stray 0.
    if len(digits) not in (10, 11):
        return "", ""
    if digits.startswith("07") and (not digits.startswith(("070", "076"))
                                    or digits.startswith("07624")):
        return f"{digits[:5]} {digits[5:]}", MOBILE
    if digits.startswith("02"):
        return f"{digits[:3]} {digits[3:7]} {digits[7:]}", LANDLINE
    if digits.startswith("01"):
        return f"{digits[:5]} {digits[5:]}", LANDLINE
    if digits.startswith(("03", "08", "09")):
        return f"{digits[:4]} {digits[4:7]} {digits[7:]}", NON_GEO
    return digits, OTHER_PHONE


def add_phones(place, numbers, country):
    """Gather every phone number, tidy and label it, and fill the phone columns."""
    known = split(place["all_phones"]) + ([place["phone"]] if place["phone"] else [])
    labelled = {}
    for raw in known + list(numbers):
        if not raw or not raw.strip():
            continue
        tidy, kind = uk_phone(raw) if country == "GB" else (raw.strip(), "")
        tidy = tidy or raw.strip()
        labelled.setdefault(tidy, kind)
    place["all_phones"] = "; ".join(f"{n} ({k})" if k else n for n, k in labelled.items())
    mobiles = [n for n, k in labelled.items() if k == MOBILE]
    landlines = [n for n, k in labelled.items() if k == LANDLINE]
    place["mobile"] = mobiles[0] if mobiles else ""
    place["landline"] = landlines[0] if landlines else ""
    if labelled and not place["phone"]:
        place["phone"] = next(iter(labelled))
    elif place["phone"] and country == "GB":
        place["phone"] = uk_phone(place["phone"])[0] or place["phone"]
    place["phone_type"] = labelled.get(place["phone"], "")
    # A business reached only on a mobile is often one person working alone.
    place["mobile_only"] = "yes" if mobiles and len(mobiles) == len(labelled) else ""
