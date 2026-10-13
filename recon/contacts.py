"""Every way to reach a business, labelled: emails, phones and social links.

Edem asked to see all of it (13 October 2026) so decisions can be made with
the full picture. Seeing is not permission: the contact_rule column still
decides who may be emailed, and phone numbers must be screened against the
TPS and CTPS before anyone rings them (docs/RULES.md).
"""

import re

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


def email_label(address, site=""):
    local, _, host = address.lower().partition("@")
    if host in FREE_MAIL:
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
        if address and "@" in address and address not in known:
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
