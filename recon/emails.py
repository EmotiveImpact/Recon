"""Find the contact email a business publishes on its own website.

Polite by design: it reads robots.txt, fetches at most a few pages per site,
identifies itself, and never visits booking platforms or social sites.
Results are cached, so a stopped run carries on where it left off.
"""

import html
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from . import text

USER_AGENT = "Mozilla/5.0 (compatible; recon/0.1; in-house research)"
MAX_BYTES = 1_000_000
MAX_EXTRA_PAGES = 3
TIMEOUT = 12

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,24}")
_LINK = re.compile(r"""<a\b[^>]*href\s*=\s*["']([^"'#]+)["'][^>]*>(.*?)</a>""", re.I | re.S)
_CONTACTISH = re.compile(r"contact|about|get-in-touch|find-us|visit|book|enquir", re.I)
_JUNK_DOMAINS = (
    "example.com", "domain.com", "email.com", "yourdomain", "sentry.io", "wixpress.com",
    "sentry-next.wixpress.com", "godaddy.com", "squarespace.com", "wordpress.com",
    "mysite.com", "test.com",
)
_JUNK_ENDINGS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".css", ".js")
_PREFERRED = ("info", "hello", "contact", "bookings", "booking", "enquiries", "enquiry",
              "reception", "salon", "studio", "admin", "office")


def _fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        if "html" not in (response.headers.get("Content-Type") or "html"):
            return "", response.geturl()
        body = response.read(MAX_BYTES)
        charset = response.headers.get_content_charset() or "utf-8"
        return body.decode(charset, errors="replace"), response.geturl()


def _robots(base):
    parser = urllib.robotparser.RobotFileParser()
    try:
        text_, _ = _fetch(urllib.parse.urljoin(base, "/robots.txt"))
        parser.parse(text_.splitlines())
    except Exception:
        parser.parse([])  # No robots file means no stated limits.
    return parser


def clean_candidates(page):
    """Every plausible email on a page, in the order it appears."""
    page = html.unescape(page)
    found = []
    for raw in _EMAIL.findall(page.replace("%40", "@")):
        email = raw.strip(".").lower()
        if email.endswith(_JUNK_ENDINGS):
            continue
        if any(junk in email.split("@")[1] for junk in _JUNK_DOMAINS):
            continue
        if email not in found:
            found.append(email)
    return found


def best_email(candidates, site_domain):
    """Prefer an address on the studio's own domain, then a shared inbox name."""
    if not candidates:
        return ""

    def score(email):
        local, _, host = email.partition("@")
        same = host == site_domain or host.endswith("." + site_domain)
        role = local in _PREFERRED
        return (0 if same else 1, 0 if role else 1, candidates.index(email))

    return sorted(candidates, key=score)[0]


def contact_links(page, base):
    """Links on the same site that look like a contact or about page."""
    host = text.domain(base)
    links = []
    for href, label in _LINK.findall(page):
        if href.startswith("mailto:"):
            continue
        url = urllib.parse.urljoin(base, href.strip())
        if text.domain(url) != host:
            continue
        if _CONTACTISH.search(href) or _CONTACTISH.search(re.sub("<[^>]+>", "", label)):
            if url not in links:
                links.append(url)
    return links[:MAX_EXTRA_PAGES]


def find_email(website):
    """Return (email, page_it_was_found_on) for one website, or ('', reason)."""
    if not text.own_website(website):
        return "", "not the business's own site"
    start = website if "://" in website else "https://" + website
    try:
        robots = _robots(start)
        if not robots.can_fetch(USER_AGENT, start):
            return "", "site asks robots not to visit"
        page, final_url = _fetch(start)
        site = text.domain(final_url)
        candidates = clean_candidates(page)
        found_on = {e: final_url for e in candidates}
        if not any(e.endswith("@" + site) for e in candidates):
            for link in contact_links(page, final_url):
                if not robots.can_fetch(USER_AGENT, link):
                    continue
                time.sleep(1)  # One page a second per site.
                more, _ = _fetch(link)
                for email in clean_candidates(more):
                    if email not in found_on:
                        candidates.append(email)
                        found_on[email] = link
        email = best_email(candidates, site)
        return (email, found_on[email]) if email else ("", "no email on the site")
    except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError) as error:
        return "", f"could not open site ({type(error).__name__})"
    except Exception as error:  # A broken site must never stop the whole run.
        return "", f"could not read site ({type(error).__name__})"


def _load_cache(path):
    cache = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                    cache[row["domain"]] = row
                except (json.JSONDecodeError, KeyError):
                    continue  # Skip a half-written last line.
    return cache


def fill(places, cache_path, everyone=False, workers=8):
    """Look up emails for places with their own website.

    By default only places we may email are looked up: collecting addresses
    we cannot lawfully use is pointless and goes against data minimisation.
    """
    cache = _load_cache(cache_path)
    todo = {}
    for place in places:
        if place["email"] or not place["website"]:
            continue
        if not everyone and place["contact_rule"] != "can email":
            continue
        site = text.domain(place["website"])
        if site in cache:
            place["email"] = cache[site]["email"]
            place["email_found_on"] = cache[site]["found_on"]
        else:
            todo.setdefault(site, []).append(place)

    print(f"  {len(todo)} websites to visit ({len(cache)} already visited)")
    os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)
    done = 0
    with open(cache_path, "a", encoding="utf-8") as log, \
            ThreadPoolExecutor(max_workers=workers) as pool:
        jobs = {pool.submit(find_email, group[0]["website"]): site
                for site, group in todo.items()}
        for job in as_completed(jobs):
            site = jobs[job]
            email, found_on = job.result()
            log.write(json.dumps({
                "domain": site, "email": email, "found_on": found_on,
                "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }) + "\n")
            log.flush()
            for place in todo[site]:
                place["email"] = email
                place["email_found_on"] = found_on
            done += 1
            if done % 100 == 0:
                print(f"  {done} of {len(todo)} websites visited")
    return len(todo)
