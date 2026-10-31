"""The small CRM inside Recon: saved lists, today's calls, a status and notes
for each business, and one do-not-contact list shared by everything.

What it is for, in Edem's words (the platform plan, 14 October 2026): make a
list from the map or Find, get ten calls a day from it, log each call in two
taps, see who has been contacted, and never see anyone who asked us to stop.

Everything lives in one SQLite file, data/crm.sqlite, which comes with Python
and is never committed (data/ is ignored). A business is known by the id the
master database gives it (`group_id`), or `trade:<company number or name and
postcode>` for a row from the trade lists, so the same business saved from two
searches is one business here. Each saved business keeps a copy of what Recon
knew about it (name, phone, email, address, rule) so a list still reads when
the shared folder is away.

Recon finds; it does not send or dial. The calling hook-up is in calling.py
and only runs when Edem has signed up and set the keys.
"""

import argparse
import csv
import datetime as dt
import json
import os
import re
import sqlite3
import threading

# What happened on a call, in the order the buttons show, and the status each
# one leaves the business in.
OUTCOMES = {
    "no answer": "no answer",
    "voicemail": "no answer",
    "call back": "call back",
    "spoke": "spoke",
    "interested": "interested",
    "not interested": "not interested",
    "customer": "customer",
    "do not contact": "do not contact",
    "note": None,  # A note alone leaves the status as it was.
}
STATUSES = ["new", "no answer", "call back", "spoke", "interested", "not interested",
            "customer", "do not contact"]
# Nobody in these states is offered for a call again.
FINISHED = ("not interested", "customer", "do not contact")
# How long a TPS/CTPS check stays good for (the law says within 28 days).
SCREENING_DAYS = 28
# The columns a saved business carries.
FIELDS = ("name", "kind", "address", "town", "postcode", "phone", "mobile", "email",
          "website", "rule", "sources", "country", "lat", "lon")

SCHEMA = """
CREATE TABLE IF NOT EXISTS lists (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, project TEXT DEFAULT '', notes TEXT DEFAULT '',
    query TEXT DEFAULT '{}', created TEXT NOT NULL, updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS businesses (
    id TEXT PRIMARY KEY, name TEXT, kind TEXT, address TEXT, town TEXT, postcode TEXT,
    phone TEXT, mobile TEXT, email TEXT, website TEXT, rule TEXT, sources TEXT, country TEXT,
    lat TEXT, lon TEXT, updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS list_items (
    list_id INTEGER NOT NULL REFERENCES lists(id) ON DELETE CASCADE,
    business TEXT NOT NULL REFERENCES businesses(id), added TEXT NOT NULL,
    PRIMARY KEY (list_id, business));
CREATE TABLE IF NOT EXISTS contacts (
    business TEXT PRIMARY KEY REFERENCES businesses(id), status TEXT NOT NULL DEFAULT 'new',
    note TEXT DEFAULT '', call_back TEXT, updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS activities (
    id INTEGER PRIMARY KEY, business TEXT NOT NULL REFERENCES businesses(id), at TEXT NOT NULL,
    kind TEXT NOT NULL, outcome TEXT DEFAULT '', note TEXT DEFAULT '', seconds INTEGER,
    recording TEXT DEFAULT '', call_id TEXT DEFAULT '');
CREATE INDEX IF NOT EXISTS activities_business ON activities(business, at);
CREATE TABLE IF NOT EXISTS do_not_contact (
    id INTEGER PRIMARY KEY, business TEXT DEFAULT '', phone TEXT DEFAULT '', email TEXT DEFAULT '',
    name TEXT DEFAULT '', reason TEXT DEFAULT '', at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS dnc_phone ON do_not_contact(phone);
CREATE INDEX IF NOT EXISTS dnc_email ON do_not_contact(email);
CREATE TABLE IF NOT EXISTS niches (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, country TEXT DEFAULT 'uk',
    query TEXT NOT NULL, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS screening (
    phone TEXT PRIMARY KEY, result TEXT NOT NULL, checked TEXT NOT NULL, source TEXT DEFAULT '');
"""


def now():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today():
    return dt.date.today().isoformat()


def normalise_phone(number, country="GB"):
    """A phone number as it is dialled internationally, '+' and digits only,
    or '' when it isn't one. UK: 01273 123456 -> +441273123456."""
    text = str(number or "").strip()
    if not text:
        return ""
    text = re.sub(r"\(0\)", "", text)
    text = text.split(";")[0].split(",")[0].strip()  # The first of several.
    if text.startswith("00"):
        text = "+" + text[2:]
    digits = re.sub(r"\D", "", text)
    if not digits:
        return ""
    if text.startswith("+"):
        return "+" + digits if 7 <= len(digits) <= 15 else ""
    country = (country or "GB").upper()
    if country in ("GB", "UK"):
        if digits.startswith("44") and len(digits) >= 12:
            return "+" + digits
        if digits.startswith("0") and len(digits) in (10, 11):
            return "+44" + digits[1:]
        return ""
    if country == "US":
        if len(digits) == 10:
            return "+1" + digits
        if len(digits) == 11 and digits.startswith("1"):
            return "+" + digits
        return ""
    return "+" + digits if 7 <= len(digits) <= 15 else ""


def is_mobile(e164):
    """UK mobiles start +447; US numbers can't be told apart."""
    return e164.startswith("+447")


def business_id(row):
    """The id a search row is saved under: the master database's group_id, or
    for a trade-list row the company number, or the name and postcode."""
    if row.get("id"):
        return str(row["id"])
    if row.get("group_id"):
        return str(row["group_id"])
    if row.get("company_number"):
        return "trade:" + str(row["company_number"]).strip()
    name = re.sub(r"\s+", " ", str(row.get("name", "")).strip().lower())
    postcode = re.sub(r"\s+", "", str(row.get("postcode", "")).upper())
    if not name:
        raise ValueError("A business needs a name")
    return f"trade:{name}|{postcode}"


def first(value):
    """'a; b; c' -> 'a'. Recon joins several values with semicolons."""
    return str(value or "").split(";")[0].strip()


def snapshot(row):
    """What a search row (master database or trade list) says about a business,
    in the CRM's own columns."""
    phones = [p.strip() for p in str(row.get("phones", "") or "").split(";") if p.strip()]
    phone = row.get("phone") or (phones[0] if phones else "")
    mobile = row.get("mobile") or ""
    if not mobile:
        for p in phones:
            if is_mobile(normalise_phone(p, row.get("country") or "GB")):
                mobile = p
                break
    return {
        "name": str(row.get("name", "")).strip(),
        "kind": first(row.get("kind") or row.get("what") or row.get("trade") or ""),
        "address": str(row.get("address", "") or ""),
        "town": str(row.get("town", "") or ""),
        "postcode": str(row.get("postcode", "") or ""),
        "phone": str(phone or ""),
        "mobile": str(mobile or ""),
        "email": first(row.get("email") or row.get("emails") or ""),
        "website": first(row.get("website") or ""),
        "rule": str(row.get("rule") or row.get("can_email") or row.get("contact_rule") or ""),
        "sources": str(row.get("sources", "") or ""),
        "country": str(row.get("country") or ("US" if str(row.get("group", "")) == "us" else "GB")),
        "lat": str(row.get("lat", "") or ""),
        "lon": str(row.get("lon", "") or ""),
    }


class CRM:
    def __init__(self, path):
        self.path = path
        self.lock = threading.RLock()
        if path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(SCHEMA)

    # Helpers ----------------------------------------------------------------

    def _rows(self, sql, params=()):
        with self.lock:
            return [dict(r) for r in self.db.execute(sql, params).fetchall()]

    def _one(self, sql, params=()):
        rows = self._rows(sql, params)
        return rows[0] if rows else None

    # Lists ------------------------------------------------------------------

    def lists(self):
        """Every saved list with how many businesses it holds and how many
        have been contacted."""
        return self._rows("""
            SELECT l.*, count(i.business) AS businesses,
                   count(c.business) FILTER (WHERE c.status <> 'new') AS contacted,
                   count(b.id) FILTER (WHERE b.phone <> '' OR b.mobile <> '') AS with_phone,
                   count(b.id) FILTER (WHERE b.rule = 'can email') AS may_email
            FROM lists l LEFT JOIN list_items i ON i.list_id = l.id
            LEFT JOIN businesses b ON b.id = i.business
            LEFT JOIN contacts c ON c.business = i.business
            GROUP BY l.id ORDER BY l.updated DESC""")

    def create_list(self, name, project="", notes="", query=None):
        name = str(name or "").strip()
        if not name:
            raise ValueError("A list needs a name")
        stamp = now()
        with self.lock, self.db:
            cursor = self.db.execute(
                "INSERT INTO lists (name, project, notes, query, created, updated) VALUES (?,?,?,?,?,?)",
                (name, str(project or "").strip(), str(notes or "").strip(),
                 json.dumps(query or {}), stamp, stamp))
            return cursor.lastrowid

    def get_list(self, list_id):
        found = self._one("SELECT * FROM lists WHERE id = ?", (int(list_id),))
        if not found:
            raise LookupError(f"No list number {list_id}")
        found["query"] = json.loads(found["query"] or "{}")
        found["items"] = self._rows("""
            SELECT b.*, i.added, coalesce(c.status, 'new') AS status, coalesce(c.note, '') AS note,
                   c.call_back, c.updated AS status_updated
            FROM list_items i JOIN businesses b ON b.id = i.business
            LEFT JOIN contacts c ON c.business = b.id
            WHERE i.list_id = ? ORDER BY i.added, b.name""", (int(list_id),))
        for item in found["items"]:  # Numbers are compared as dialled, so this is done here.
            item["blocked"] = self.is_blocked(item)
        return found

    def update_list(self, list_id, name=None, project=None, notes=None):
        self.get_list(list_id)
        fields, params = [], []
        for key, value in (("name", name), ("project", project), ("notes", notes)):
            if value is not None:
                if key == "name" and not str(value).strip():
                    raise ValueError("A list needs a name")
                fields.append(f"{key} = ?")
                params.append(str(value).strip())
        fields.append("updated = ?")
        params += [now(), int(list_id)]
        with self.lock, self.db:
            self.db.execute(f"UPDATE lists SET {', '.join(fields)} WHERE id = ?", params)

    def delete_list(self, list_id):
        self.get_list(list_id)
        with self.lock, self.db:
            self.db.execute("DELETE FROM list_items WHERE list_id = ?", (int(list_id),))
            self.db.execute("DELETE FROM lists WHERE id = ?", (int(list_id),))

    def save_business(self, row):
        """Remember a business (or refresh what we know), and return its id."""
        bid = business_id(row)
        data = snapshot(row)
        # A blank in the new row never wipes what an earlier search knew.
        keep = ", ".join(f"{f} = CASE WHEN excluded.{f} <> '' THEN excluded.{f} ELSE businesses.{f} END"
                         for f in FIELDS)
        with self.lock, self.db:
            self.db.execute(f"""
                INSERT INTO businesses (id, {', '.join(FIELDS)}, updated)
                VALUES (?, {', '.join('?' for _ in FIELDS)}, ?)
                ON CONFLICT (id) DO UPDATE SET {keep}, updated = excluded.updated""",
                (bid, *[data[f] for f in FIELDS], now()))
        return bid

    def add_items(self, list_id, rows):
        """Add businesses (search rows) to a list; returns how many were new."""
        self.get_list(list_id)
        added = 0
        stamp = now()
        for row in rows:
            bid = self.save_business(row)
            with self.lock, self.db:
                cursor = self.db.execute(
                    "INSERT OR IGNORE INTO list_items (list_id, business, added) VALUES (?,?,?)",
                    (int(list_id), bid, stamp))
                added += cursor.rowcount
        with self.lock, self.db:
            self.db.execute("UPDATE lists SET updated = ? WHERE id = ?", (stamp, int(list_id)))
        return added

    def remove_item(self, list_id, business):
        with self.lock, self.db:
            self.db.execute("DELETE FROM list_items WHERE list_id = ? AND business = ?",
                            (int(list_id), business))

    def export_list(self, list_id, path):
        """The list as a spreadsheet, with each business's status and notes."""
        found = self.get_list(list_id)
        columns = [*FIELDS, "status", "note", "call_back", "blocked", "added"]
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            for item in found["items"]:
                item["blocked"] = "yes" if item["blocked"] else ""
                writer.writerow({k: ("" if item.get(k) is None else item.get(k)) for k in columns})
        return len(found["items"])

    # Each business: status, notes and history ---------------------------------

    def business(self, bid):
        found = self._one("""
            SELECT b.*, coalesce(c.status, 'new') AS status, coalesce(c.note, '') AS note,
                   c.call_back, c.updated AS status_updated
            FROM businesses b LEFT JOIN contacts c ON c.business = b.id WHERE b.id = ?""", (bid,))
        if not found:
            raise LookupError("Recon hasn't saved that business yet")
        found["blocked"] = self.is_blocked(found)
        found["history"] = self._rows(
            "SELECT * FROM activities WHERE business = ? ORDER BY at DESC, id DESC", (bid,))
        found["lists"] = self._rows("""SELECT l.id, l.name FROM list_items i JOIN lists l ON l.id = i.list_id
                                       WHERE i.business = ? ORDER BY l.name""", (bid,))
        found["screening"] = self.screening_of(found)
        return found

    def log(self, bid, outcome, note="", call_back=None, seconds=None, recording="", call_id="",
            kind=None):
        """Record what happened (a call outcome or a note) and move the status on."""
        outcome = str(outcome or "note").strip().lower()
        if outcome not in OUTCOMES:
            raise ValueError("Choose one of: " + ", ".join(OUTCOMES))
        if call_back:
            try:
                dt.date.fromisoformat(str(call_back))
            except ValueError:
                raise ValueError("A call-back date looks like 2026-11-03") from None
        if outcome == "call back" and not call_back:
            raise ValueError("Pick a day to call back")
        existing = self._one("SELECT id FROM businesses WHERE id = ?", (bid,))
        if not existing:
            raise LookupError("Recon hasn't saved that business yet")
        note = str(note or "").strip()
        kind = kind or ("note" if outcome == "note" else "call")
        stamp = now()
        status = OUTCOMES[outcome]
        with self.lock, self.db:
            self.db.execute("""INSERT INTO activities (business, at, kind, outcome, note, seconds, recording, call_id)
                               VALUES (?,?,?,?,?,?,?,?)""",
                            (bid, stamp, kind, "" if outcome == "note" else outcome, note, seconds,
                             recording or "", call_id or ""))
            current = self._one("SELECT * FROM contacts WHERE business = ?", (bid,))
            new_status = status or (current["status"] if current else "new")
            new_note = current["note"] if current else ""
            if kind == "call" and outcome == "note":
                pass  # What the phone system reports is history, not Edem's note.
            elif outcome == "note" and new_note and note:
                new_note = new_note + "\n" + note
            elif note:
                new_note = note
            new_call_back = call_back if outcome == "call back" else (
                None if status else (current["call_back"] if current else None))
            self.db.execute("""INSERT INTO contacts (business, status, note, call_back, updated) VALUES (?,?,?,?,?)
                               ON CONFLICT (business) DO UPDATE SET status = excluded.status,
                               note = excluded.note, call_back = excluded.call_back, updated = excluded.updated""",
                            (bid, new_status, new_note, new_call_back, stamp))
        if outcome == "do not contact":
            self.block(business=bid, reason=note or "asked on a call")
        return self.business(bid)

    # Do not contact -----------------------------------------------------------

    def block(self, business="", phone="", email="", name="", reason=""):
        """Add to the one do-not-contact list. A business id blocks it everywhere;
        a phone or email blocks any business carrying it."""
        phone = normalise_phone(phone) if phone else ""
        email = str(email or "").strip().lower()
        if business:
            found = self._one("SELECT * FROM businesses WHERE id = ?", (business,))
            if found:
                name = name or found["name"]
                phone = phone or normalise_phone(found["phone"] or found["mobile"], found["country"])
                email = email or (found["email"] or "").lower()
        if not (business or phone or email):
            raise ValueError("Give a business, a phone number or an email address")
        with self.lock, self.db:
            self.db.execute("""INSERT INTO do_not_contact (business, phone, email, name, reason, at)
                               VALUES (?,?,?,?,?,?)""",
                            (business, phone, email, str(name or ""), str(reason or ""), now()))
            if business:
                self.db.execute("""INSERT INTO contacts (business, status, note, call_back, updated)
                                   VALUES (?, 'do not contact', '', NULL, ?)
                                   ON CONFLICT (business) DO UPDATE SET status = 'do not contact',
                                   call_back = NULL, updated = excluded.updated""", (business, now()))

    def unblock(self, entry_id):
        with self.lock, self.db:
            self.db.execute("DELETE FROM do_not_contact WHERE id = ?", (int(entry_id),))

    def blocked(self):
        return self._rows("SELECT * FROM do_not_contact ORDER BY at DESC")

    def is_blocked(self, found):
        phones = [normalise_phone(found.get(k), found.get("country")) for k in ("phone", "mobile")]
        phones = [p for p in phones if p]
        email = (found.get("email") or "").lower()
        return bool(self._one("""SELECT 1 FROM do_not_contact WHERE business = ?
                                 OR (phone <> '' AND phone IN (?, ?)) OR (email <> '' AND email = ?)""",
                              (found.get("id", ""), *(phones + ["", ""])[:2], email)))

    # Screening against the TPS and CTPS ---------------------------------------

    def record_screening(self, rows, source="", checked=None):
        """Save the results of a TPS/CTPS check: rows of {phone, result}, where
        result is 'clear', 'tps' or 'ctps'. Returns how many were saved."""
        checked = checked or today()
        saved = 0
        with self.lock, self.db:
            for row in rows:
                phone = normalise_phone(row.get("phone") or row.get("number"))
                result = str(row.get("result", "")).strip().lower()
                result = {"ok": "clear", "clear": "clear", "not listed": "clear", "no": "clear",
                          "tps": "tps", "ctps": "ctps", "listed": "tps", "yes": "tps"}.get(result)
                if not phone or not result:
                    continue
                self.db.execute("""INSERT INTO screening (phone, result, checked, source) VALUES (?,?,?,?)
                                   ON CONFLICT (phone) DO UPDATE SET result = excluded.result,
                                   checked = excluded.checked, source = excluded.source""",
                                (phone, result, checked, source))
                saved += 1
        return saved

    def screening_of(self, found):
        """'clear', 'tps', 'ctps', 'stale' (checked over 28 days ago), 'unknown'
        (never checked) or 'no phone' for a saved business."""
        number = normalise_phone(found.get("phone") or found.get("mobile"), found.get("country"))
        if not number:
            return "no phone"
        row = self._one("SELECT result, checked FROM screening WHERE phone = ?", (number,))
        if not row:
            return "unknown"
        age = (dt.date.today() - dt.date.fromisoformat(row["checked"])).days
        if age > SCREENING_DAYS:
            return "stale"
        return row["result"]

    def unscreened(self, list_id=None):
        """Numbers that need a TPS/CTPS check before they can be called."""
        where = "" if list_id is None else " WHERE b.id IN (SELECT business FROM list_items WHERE list_id = ?)"
        rows = self._rows(f"SELECT b.* FROM businesses b{where}", () if list_id is None else (int(list_id),))
        return sorted({normalise_phone(r["phone"] or r["mobile"], r["country"]) for r in rows
                       if self.screening_of(r) in ("unknown", "stale")} - {""})

    # Today's calls ------------------------------------------------------------

    def today_calls(self, list_id=None, count=10, day=None):
        """The next businesses to ring: call-backs due today or overdue first,
        then the best new prospects (may email, has a website, has an email),
        then those with no answer so far. Nobody blocked, finished, without a
        phone, or already rung today."""
        day = day or today()
        count = max(1, min(int(count or 10), 100))
        params = [day, day]
        where = ""
        if list_id is not None:
            self.get_list(list_id)
            where = " AND b.id IN (SELECT business FROM list_items WHERE list_id = ?)"
            params.append(int(list_id))
        rows = self._rows(f"""
            SELECT b.*, coalesce(c.status, 'new') AS status, coalesce(c.note, '') AS note, c.call_back,
                   (SELECT count(*) FROM activities a WHERE a.business = b.id AND a.kind = 'call') AS calls,
                   (SELECT max(at) FROM activities a WHERE a.business = b.id AND a.kind = 'call') AS last_call,
                   (SELECT group_concat(l.name, '; ') FROM list_items i JOIN lists l ON l.id = i.list_id
                    WHERE i.business = b.id) AS lists
            FROM businesses b LEFT JOIN contacts c ON c.business = b.id
            WHERE (b.phone <> '' OR b.mobile <> '')
              AND coalesce(c.status, 'new') NOT IN ('not interested', 'customer', 'do not contact')
              AND (c.call_back IS NULL OR c.call_back <= ?)
              AND NOT EXISTS (SELECT 1 FROM activities a WHERE a.business = b.id AND a.kind = 'call'
                              AND substr(a.at, 1, 10) = ?
                              AND NOT (c.call_back IS NOT NULL AND c.call_back <= substr(a.at, 1, 10)))
              AND b.id IN (SELECT business FROM list_items){where}
            ORDER BY c.call_back IS NULL, c.call_back,
                     coalesce(c.status, 'new') = 'no answer',
                     b.rule <> 'can email', b.website = '', b.email = '', calls, b.name""", params)
        picked = []
        for row in rows:
            if self.is_blocked(row):
                continue
            number = normalise_phone(row["phone"] or row["mobile"], row["country"])
            row["dial"] = number
            row["mobile_number"] = is_mobile(number)
            row["screening"] = self.screening_of(row)
            row["why"] = self._why(row, day)
            picked.append(row)
            if len(picked) >= count:
                break
        return picked

    @staticmethod
    def _why(row, day):
        reasons = []
        if row.get("call_back"):
            reasons.append("call back due today" if row["call_back"] == day
                           else f"call back was due {row['call_back']}")
        if row.get("rule") == "can email":
            reasons.append("a company, so may also be emailed")
        if row.get("website"):
            reasons.append("has a website")
        if row.get("email"):
            reasons.append("has an email address")
        if row.get("status") == "no answer":
            reasons.append(f"no answer so far ({row.get('calls') or 0} tries)")
        return "; ".join(reasons) or "new"

    # Saved niches -------------------------------------------------------------

    def niches(self):
        found = self._rows("SELECT * FROM niches ORDER BY name")
        for n in found:
            n["query"] = json.loads(n["query"])
        return found

    def save_niche(self, name, query, country="uk"):
        """A named mix of sector, industry, niche, place and filters, as the map
        page's own query, so it opens the same view again."""
        name = str(name or "").strip()
        if not name:
            raise ValueError("A niche needs a name")
        if not isinstance(query, dict) or not query:
            raise ValueError("A niche needs the search it came from")
        clean = {str(k)[:40]: [str(x)[:120] for x in (v if isinstance(v, list) else [v]) if str(x)]
                 for k, v in query.items()}
        clean = {k: v for k, v in clean.items() if v}
        with self.lock, self.db:
            cursor = self.db.execute("INSERT INTO niches (name, country, query, created) VALUES (?,?,?,?)",
                                     (name, "us" if country == "us" else "uk", json.dumps(clean), now()))
            return cursor.lastrowid

    def delete_niche(self, niche_id):
        with self.lock, self.db:
            self.db.execute("DELETE FROM niches WHERE id = ?", (int(niche_id),))

    # Headline figures -----------------------------------------------------------

    def summary(self):
        counts = self._one("""
            SELECT (SELECT count(*) FROM lists) AS lists,
                   (SELECT count(*) FROM businesses) AS businesses,
                   (SELECT count(*) FROM contacts WHERE status <> 'new') AS contacted,
                   (SELECT count(*) FROM contacts WHERE status = 'interested') AS interested,
                   (SELECT count(*) FROM contacts WHERE status = 'customer') AS customers,
                   (SELECT count(*) FROM contacts WHERE call_back IS NOT NULL AND call_back <= ?) AS call_backs_due,
                   (SELECT count(*) FROM do_not_contact) AS do_not_contact,
                   (SELECT count(*) FROM activities WHERE kind = 'call' AND substr(at, 1, 10) = ?) AS calls_today,
                   (SELECT count(*) FROM niches) AS niches""", (today(), today()))
        return counts


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m recon.crm", description="Recon's small CRM.")
    parser.add_argument("--db", default=os.path.join("data", "crm.sqlite"))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("lists", help="show the saved lists")
    today_cmd = sub.add_parser("today", help="today's calls")
    today_cmd.add_argument("--list", type=int)
    today_cmd.add_argument("--count", type=int, default=10)
    unscreened = sub.add_parser("unscreened", help="numbers that need a TPS/CTPS check, as a CSV for the checker")
    unscreened.add_argument("--list", type=int)
    unscreened.add_argument("--out", default="-")
    screen = sub.add_parser("screen", help="import TPS/CTPS results: a CSV with phone and result columns")
    screen.add_argument("file")
    screen.add_argument("--source", default="tps-services")
    export = sub.add_parser("export", help="a list as a spreadsheet")
    export.add_argument("list", type=int)
    export.add_argument("out")
    args = parser.parse_args(argv)
    crm = CRM(args.db)
    if args.command == "lists":
        for l in crm.lists():
            print(f"{l['id']:>4}  {l['name']}: {l['businesses']} businesses, {l['contacted']} contacted")
    elif args.command == "today":
        for row in crm.today_calls(args.list, args.count):
            print(f"{row['name']}  {row['dial']}  [{row['screening']}]  {row['why']}")
    elif args.command == "unscreened":
        numbers = crm.unscreened(args.list)
        out = open(args.out, "w", newline="", encoding="utf-8") if args.out != "-" else None
        writer = csv.writer(out or __import__("sys").stdout)
        writer.writerow(["phone"])
        for n in numbers:
            writer.writerow([n])
        if out:
            out.close()
            print(f"{len(numbers)} numbers written to {args.out}")
    elif args.command == "screen":
        with open(args.file, newline="", encoding="utf-8-sig") as handle:
            saved = crm.record_screening(list(csv.DictReader(handle)), source=args.source)
        print(f"{saved} numbers recorded")
    elif args.command == "export":
        print(f"{crm.export_list(args.list, args.out)} businesses written to {args.out}")


if __name__ == "__main__":
    main()
