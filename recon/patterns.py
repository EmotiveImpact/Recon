"""Learn how a business shapes its email addresses, and apply it to a name.

Most businesses use one pattern for everyone: sarah@, sarah.jones@, sjones@.
Seeing one published address that matches a known person's name is enough to
learn it. This is the main trick the paid email finders use.
"""

import collections
import re
import unicodedata

# Each pattern, written with {first}, {last}, {f} (first initial), {l} (last initial).
PATTERNS = {
    "first": "{first}",
    "first.last": "{first}.{last}",
    "firstlast": "{first}{last}",
    "f.last": "{f}.{last}",
    "flast": "{f}{last}",
    "first_last": "{first}_{last}",
    "first-last": "{first}-{last}",
    "firstl": "{first}{l}",
    "first.l": "{first}.{l}",
    "last": "{last}",
    "last.first": "{last}.{first}",
    "lastfirst": "{last}{first}",
    "lastf": "{last}{f}",
}

# What small businesses most often use, when there is nothing else to go on.
COMMON_ORDER = ["first", "first.last", "firstlast", "f.last", "flast", "firstl"]

# Shared inbox names. An address like these is never one person's.
ROLE_WORDS = {
    "info", "hello", "hi", "contact", "contactus", "bookings", "booking", "book",
    "enquiries", "enquiry", "enquire", "inquiries", "reception", "salon", "studio",
    "admin", "office", "team", "mail", "email", "appointments", "accounts", "sales",
    "support", "help", "clinic", "spa", "shop", "store", "orders", "marketing",
    "press", "jobs", "careers", "noreply", "no-reply", "privacy", "gdpr", "billing",
    "webmaster", "events", "general", "manager", "management", "therapy",
}


def plain(word):
    """Lower-case letters only, accents removed: 'O'Brién-Smith' -> 'obriensmith'."""
    word = unicodedata.normalize("NFKD", word or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", word.lower())


def split_name(name):
    """(first, last) in plain letters from 'Sarah Jane Jones' or 'JONES, Sarah Jane'.

    Returns None when there is no clear first and last name.
    """
    name = re.sub(r"\b(mr|mrs|ms|miss|dr|prof|sir|dame)\b\.?", " ", name or "", flags=re.I)
    if "," in name:  # Companies House writes 'SURNAME, Forenames'.
        last, _, rest = name.partition(",")
        words = rest.split()
        first = words[0] if words else ""
    else:
        words = name.split()
        if len(words) < 2:
            return None
        first, last = words[0], words[-1]
    first, last = plain(first), plain(last)
    return (first, last) if first and last else None


def make(pattern, first, last):
    """The local part (before the @) for one person under one pattern."""
    return PATTERNS[pattern].format(first=first, last=last, f=first[:1], l=last[:1])


def is_role(local):
    return local.lower() in ROLE_WORDS or plain(local) in ROLE_WORDS


def matches(local, people):
    """Every (pattern, person) that would produce this local part."""
    local = local.lower()
    found = []
    for person in people:
        for pattern in PATTERNS:
            if make(pattern, *person) == local:
                found.append((pattern, person))
    return found


def shape(local):
    """A weaker hint from the address alone, such as 'j.smith' -> 'f.last'."""
    if is_role(local):
        return None
    parts = re.split(r"([._-])", local.lower())
    if len(parts) != 3 or not all(p.isalpha() for p in (parts[0], parts[2])):
        return None
    first, mark, last = parts
    if len(last) < 2:
        return None
    if len(first) == 1:
        return "f.last" if mark == "." else None
    return {".": "first.last", "_": "first_last", "-": "first-last"}[mark]


def learn(addresses, people):
    """Work out one domain's pattern from its published addresses.

    Returns (pattern, how) where how is 'matched' (an address matched a known
    person's name), 'shape' (an address looks like a pattern), or ('', '').
    """
    matched = collections.Counter()
    shaped = collections.Counter()
    for address in addresses:
        local = address.partition("@")[0]
        if is_role(local):
            continue
        hits = {pattern for pattern, _ in matches(local, people)}
        for pattern in hits:
            matched[pattern] += 1
        hint = shape(local)
        if hint and not hits:
            shaped[hint] += 1
    for counts, how in ((matched, "matched"), (shaped, "shape")):
        if counts:
            best = max(counts.items(), key=lambda item: (item[1], -_rank(item[0])))
            return best[0], how
    return "", ""


def _rank(pattern):
    return COMMON_ORDER.index(pattern) if pattern in COMMON_ORDER else len(COMMON_ORDER)


def usual_order(seen=None):
    """Patterns to try when a domain's own is unknown: those learned elsewhere
    in this run first (most often seen first), then the usual small-business order."""
    seen = seen or collections.Counter()
    ordered = [p for p, _ in sorted(seen.items(), key=lambda item: (-item[1], _rank(item[0])))]
    return ordered + [p for p in COMMON_ORDER if p not in ordered]


def from_hunter(pattern):
    """Turn Hunter's '{first}.{last}' style into one of ours, or ''."""
    sample = ("alexandra", "smithson")
    try:
        local = pattern.format(first=sample[0], last=sample[1], f="a", l="s")
    except (KeyError, IndexError, ValueError):
        return ""
    for name in PATTERNS:
        if make(name, *sample) == local:
            return name
    return ""
