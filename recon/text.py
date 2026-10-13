"""Small helpers for comparing business names, postcodes and websites."""

import re
from urllib.parse import urlparse

_UK_POSTCODE = re.compile(r"\b([A-Z]{1,2}[0-9][A-Z0-9]?)\s*([0-9][A-Z]{2})\b")
_US_ZIP = re.compile(r"\b([0-9]{5})(?:-[0-9]{4})?\b")
_COMPANY_WORDS = {
    "ltd", "limited", "llp", "plc", "the", "and", "co", "company", "uk",
    "t/a", "ta", "trading", "as",
}

# Websites that are a booking platform or social profile rather than the
# studio's own site. Their terms forbid harvesting, so we never crawl them.
NOT_OWN_SITE = (
    "facebook.com", "instagram.com", "tiktok.com", "twitter.com", "x.com",
    "linkedin.com", "fresha.com", "treatwell.co.uk", "booksy.com", "setmore.com",
    "timely.com", "gettimely.com", "phorest.com", "vagaro.com", "squareup.com",
    "square.site", "linktr.ee", "google.com", "goo.gl", "yell.com", "wa.me",
)


def postcode(text, country="GB"):
    """Tidy a postcode: 'sw1a1aa' -> 'SW1A 1AA' in the UK, five-digit ZIP in the US."""
    if not text:
        return ""
    if country == "GB":
        match = _UK_POSTCODE.search(text.upper())
        return f"{match.group(1)} {match.group(2)}" if match else ""
    if country == "US":
        match = _US_ZIP.search(text)
        return match.group(1) if match else ""
    return text.strip().upper()


def postcode_district(code):
    """'SW1A 1AA' -> 'SW1A'; a US ZIP stays as it is."""
    return code.split(" ")[0] if code else ""


def name_key(name):
    """A loose key for matching the same business across sources."""
    if not name:
        return ""
    text = name.lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9/ ]+", " ", text)
    words = [w for w in text.split() if w not in _COMPANY_WORDS]
    return " ".join(words)


def domain(url):
    """'https://www.Example.co.uk/contact' -> 'example.co.uk'."""
    if not url:
        return ""
    if "://" not in url:
        url = "https://" + url
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def own_website(url):
    """True when the URL looks like the studio's own site."""
    host = domain(url)
    if not host or "." not in host:
        return False
    return not any(host == bad or host.endswith("." + bad) for bad in NOT_OWN_SITE)
