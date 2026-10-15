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

from . import contacts, text

USER_AGENT = "Mozilla/5.0 (compatible; recon/0.1; in-house research)"
MAX_BYTES = 1_000_000
MAX_EXTRA_PAGES = 3
TIMEOUT = 12

# Runs are bounded (a local part is at most 64 characters, a domain 253) so a
# page holding a long run of letters, such as an inline image, is read in
# moments rather than hours.
_EMAIL = re.compile(r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,24}")
_JSON_LD = re.compile(r"""<script[^>]+type\s*=\s*["']application/ld\+json["'][^>]*>(.*?)</script>""",
                      re.I | re.S)
_MICRODATA = re.compile(
    r"""itemprop\s*=\s*["'](email|telephone)["'][^>]*?(?:content\s*=\s*["']([^"']+)["'][^>]*>|>([^<]+)<)""",
    re.I)
_LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.I)
_HREF = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.I)
_LINK = re.compile(r"""<a\b[^>]*href\s*=\s*["']([^"'#]+)["'][^>]*>(.*?)</a>""", re.I | re.S)
_CONTACTISH = re.compile(r"contact|about|get-in-touch|find-us|visit|book|enquir|team|meet|staff",
                         re.I)
_CONTACT_FIRST = re.compile(r"contact|enquir|get-in-touch", re.I)
_FALLBACK_PAGES = ("/contact", "/contact-us")
# Addresses hidden from robots: Cloudflare's scrambled ones, and "info [at] x [dot] com".
_CLOUDFLARE = re.compile(r"""(?:data-cfemail=["']|/cdn-cgi/l/email-protection#)([0-9a-fA-F]{6,})""")
_SPELT_OUT = re.compile(
    r"(?<![A-Za-z0-9._%+-])([A-Za-z0-9._%+-]{1,64})\s*[\[({]\s*at\s*[\])}]\s*"
    r"([A-Za-z0-9-]{1,63}(?:\s*(?:[\[({]\s*dot\s*[\])}]|\.)\s*[A-Za-z0-9-]{1,63}){1,8})", re.I)
_SPELT_DOT = re.compile(r"\s*(?:[\[({]\s*dot\s*[\])}]|\.)\s*", re.I)
_JUNK_DOMAINS = (
    "example.com", "domain.com", "email.com", "yourdomain", "sentry.io", "wixpress.com",
    "sentry-next.wixpress.com", "godaddy.com", "squarespace.com", "wordpress.com",
    "mysite.com", "test.com",
)
_JUNK_ENDINGS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".css", ".js")
_PREFERRED = ("info", "hello", "contact", "bookings", "booking", "enquiries", "enquiry",
              "reception", "salon", "studio", "admin", "office")


def _fetch(url, kind="html"):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        if kind not in (response.headers.get("Content-Type") or kind):
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


def cloudflare(scrambled):
    """Unscramble an address hidden by Cloudflare's email protection."""
    data = bytes.fromhex(scrambled)
    return bytes(b ^ data[0] for b in data[1:]).decode("utf-8", "replace")


def _unhide(page):
    """Extra text holding the addresses a page hides from robots."""
    found = []
    for scrambled in _CLOUDFLARE.findall(page):
        try:
            found.append(cloudflare(scrambled))
        except ValueError:
            continue
    for local, rest in _SPELT_OUT.findall(page):
        found.append(local + "@" + _SPELT_DOT.sub(".", rest))
    return " ".join(found)


def clean_candidates(page):
    """Every plausible email on a page, in the order it appears."""
    page = html.unescape(page)
    page = page + " " + _unhide(page)
    found = []
    for raw in _EMAIL.findall(page.replace("%40", "@")):
        email = raw.strip(".").lower()
        if email.endswith(_JUNK_ENDINGS):
            continue
        if any(junk in email.split("@")[1] for junk in _JUNK_DOMAINS):
            continue
        if not contacts.valid_email(email) or contacts.system_email(email):
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
    # Contact pages first, then about and team pages.
    links.sort(key=lambda url: 0 if _CONTACT_FIRST.search(url) else 1)
    return links[:MAX_EXTRA_PAGES]


def structured(page):
    """Business details a page states for search engines, as (emails, phones,
    social links): schema.org JSON-LD and microdata. After the ideas in
    extruct (BSD); written fresh, no code copied."""
    emails, phones, socials = [], [], []

    def walk(item):
        if isinstance(item, list):
            for value in item:
                walk(value)
        elif isinstance(item, dict):
            for key, value in item.items():
                if key == "email" and isinstance(value, str):
                    emails.append(value.replace("mailto:", "").strip())
                elif key == "telephone" and isinstance(value, str):
                    phones.append(value)
                elif key == "sameAs":
                    socials.extend(v for v in ([value] if isinstance(value, str) else value)
                                   if isinstance(v, str))
                else:
                    walk(value)

    for block in _JSON_LD.findall(page):
        try:
            walk(json.loads(html.unescape(block).strip()))
        except (json.JSONDecodeError, RecursionError):
            continue  # Broken markup is common; skip it.
    for prop, content, inner in _MICRODATA.findall(page):
        value = html.unescape(content or inner).strip()
        (emails if prop.lower() == "email" else phones).append(value.replace("mailto:", ""))
    return emails, phones, socials


def phones_and_socials(page):
    """Phone numbers from tel: links and structured data, and links to social profiles."""
    _, phones, socials = structured(page)
    for href in _HREF.findall(page):
        href = html.unescape(href).strip()
        if href.lower().startswith("tel:"):
            phones.append(urllib.parse.unquote(href[4:]))
        elif contacts.social_link(href):
            socials.append(href)
    socials = [s for s in socials if contacts.social_link(s)]
    return list(dict.fromkeys(p.strip() for p in phones if p.strip())), list(dict.fromkeys(socials))


def sitemap_links(robots, base):
    """Contact-looking pages listed in the site map, for sites whose pages
    don't link to them (common with menus drawn by JavaScript). After the
    ideas in trafilatura and courlan (Apache 2.0); written fresh."""
    maps = list(getattr(robots, "site_maps", lambda: None)() or [])[:1] or [
        urllib.parse.urljoin(base, "/sitemap.xml")]
    host = text.domain(base)
    if not robots.can_fetch(USER_AGENT, maps[0]):
        return []
    time.sleep(1)  # One page a second per site.
    try:
        listing, _ = _fetch(maps[0], kind="xml")
    except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError):
        return []
    urls = [html.unescape(u).strip() for u in _LOC.findall(listing)]
    if "<sitemapindex" in listing:  # A list of site maps: open the one for pages.
        pages = [u for u in urls if re.search(r"page", u, re.I)] or urls[:1]
        if not pages or not robots.can_fetch(USER_AGENT, pages[0]):
            return []
        time.sleep(1)
        try:
            listing, _ = _fetch(pages[0], kind="xml")
        except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError):
            return []
        urls = [html.unescape(u).strip() for u in _LOC.findall(listing)]
    found = [u for u in urls if text.domain(u) == host
             and _CONTACTISH.search(urllib.parse.urlparse(u).path)]
    found.sort(key=lambda url: 0 if _CONTACT_FIRST.search(url) else 1)
    return found[:MAX_EXTRA_PAGES]


def crawl(website, extras=None):
    """Every address on a business's own site: ({email: page it was on}, note).

    Reads the homepage, then up to three same-site pages that look like
    contact, about or team pages: linked from the homepage, or else listed in
    the site map, or else /contact. Phone
    numbers and social links found on the way go into extras, if given.
    """
    extras = {} if extras is None else extras
    extras.setdefault("phones", [])
    extras.setdefault("socials", [])

    def read(page, url):
        listed, _, _ = structured(page)
        for email in clean_candidates(page + " " + " ".join(listed)):
            found_on.setdefault(email, url)
        phones, socials = phones_and_socials(page)
        extras["phones"] += [p for p in phones if p not in extras["phones"]]
        extras["socials"] += [s for s in socials if s not in extras["socials"]]

    if not text.own_website(website):
        return {}, "not the business's own site"
    start = website if "://" in website else "https://" + website
    found_on = {}
    try:
        robots = _robots(start)
        if not robots.can_fetch(USER_AGENT, start):
            return {}, "site asks robots not to visit"
        page, final_url = _fetch(start)
        read(page, final_url)
        links = contact_links(page, final_url) or sitemap_links(robots, final_url) or [
            urllib.parse.urljoin(final_url, path) for path in _FALLBACK_PAGES]
        for link in links[:MAX_EXTRA_PAGES]:
            if not robots.can_fetch(USER_AGENT, link):
                continue
            time.sleep(1)  # One page a second per site.
            try:
                more, _ = _fetch(link)
            except urllib.error.HTTPError:
                continue  # A missing page is no reason to give up on the site.
            read(more, link)
        return found_on, "" if found_on else "no email on the site"
    except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError) as error:
        return found_on, f"could not open site ({type(error).__name__})"
    except Exception as error:  # A broken site must never stop the whole run.
        return found_on, f"could not read site ({type(error).__name__})"


def find_email(website):
    """Return (email, page_it_was_found_on) for one website, or ('', reason)."""
    found_on, note = crawl(website)
    email = best_email(list(found_on), text.domain(website))
    return (email, found_on[email]) if email else ("", note)


def _load_cache(path):
    cache = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                    if "candidates" not in row:  # Written before all addresses were kept.
                        row["candidates"] = {row["email"]: row["found_on"]} if row["email"] else {}
                    row.setdefault("phones", [])
                    row.setdefault("socials", [])
                    cache[row["domain"]] = row
                except (json.JSONDecodeError, KeyError):
                    continue  # Skip a half-written last line.
    return cache


def load(cache_path):
    """Every address found so far, by site: {domain: {email: page}}."""
    return {site: row["candidates"] for site, row in _load_cache(cache_path).items()}


def _use(place, row, country):
    """Add what a site gave to a place: every address, phone and social link,
    and its best address if the place has none yet."""
    contacts.add_emails(place, row["candidates"], row["domain"])
    contacts.add_phones(place, row["phones"], country)
    contacts.add_socials(place, row["socials"])
    if place["email"]:
        return
    email = best_email(list(row["candidates"]), row["domain"])
    place["email"] = email
    place["email_found_on"] = row["candidates"][email] if email else row["found_on"]


def fill(places, cache_path, everyone=True, workers=8, country="GB"):
    """Read every business's own website, keeping every address found.

    Edem chose (13 October 2026) to see every address, so by default all
    sites are read; the contact_rule column still decides who may be
    emailed. everyone=False reads only the sites of places we may email.
    """
    cache = _load_cache(cache_path)
    todo = {}
    for place in places:
        if not text.own_website(place["website"]):
            continue
        if not everyone and place["contact_rule"] != "can email":
            continue
        site = text.domain(place["website"])
        if site in cache:
            _use(place, cache[site], country)
        else:
            todo.setdefault(site, []).append(place)

    print(f"  {len(todo)} websites to visit ({len(cache)} already visited)")
    os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)
    done = 0
    with open(cache_path, "a", encoding="utf-8") as log, \
            ThreadPoolExecutor(max_workers=workers) as pool:
        extras = {site: {} for site in todo}
        jobs = {pool.submit(crawl, group[0]["website"], extras[site]): site
                for site, group in todo.items()}
        for job in as_completed(jobs):
            site = jobs[job]
            found_on, note = job.result()
            email = best_email(list(found_on), site)
            row = {
                "domain": site, "email": email,
                "found_on": found_on[email] if email else note, "candidates": found_on,
                "phones": extras[site].get("phones", []),
                "socials": extras[site].get("socials", []),
                "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            log.write(json.dumps(row) + "\n")
            log.flush()
            for place in todo[site]:
                _use(place, row, country)
            done += 1
            if done % 100 == 0:
                print(f"  {done} of {len(todo)} websites visited")
    return len(todo)
