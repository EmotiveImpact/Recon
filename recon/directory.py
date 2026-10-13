"""Search the master database (built by recon.master) for the website.

The master database is a folder of parquet files, one per area:
uk/england.parquet, us/ca.parquet, other/<country>.parquet and so on, each
with one row per organisation. This module only reads them, with DuckDB.

A search is plain words for the trade, such as "plumbers" or "dental,
dentist". Commas separate alternatives; words within one alternative must all
appear in the organisation's name, trade description or kind. Words are cut
to their stem, so "plumbers" also finds "plumbing".
"""

import csv
import glob
import os
import re
import tempfile
import threading

GROUPS = ("uk", "us", "other")
COLUMNS = ["name", "kind", "category", "legal_form", "address", "town", "region", "postcode",
           "country", "website", "emails", "phones", "socials", "people", "can_email", "sources"]
EXPORT_LIMIT = 1_000_000
SOURCE = "read_parquet(?, filename = true, union_by_name = true)"
AREA = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
ENDINGS = "(?:e|es|s|er|ers|ing|ings|ed|y|ies|al|ist|ists|ry|ery|ian|ians)?"
WORD = re.compile(r"[a-z0-9&']+")


def stem(word):
    """plumbers -> plumb, cleaning -> clean, salons -> salon."""
    word = word.lower()
    for ending in ("ings", "ing", "ers", "er", "ies", "s"):
        if word.endswith(ending) and len(word) - len(ending) >= 4:
            return word[: -len(ending)] + ("y" if ending == "ies" else "")
    return word


def terms(query):
    """'plumbers, heating engineer' -> [['plumb'], ['heat', 'engine']]"""
    found = []
    for part in (query or "").lower().split(","):
        words = [stem(w) for w in WORD.findall(part)]
        if words:
            found.append(words)
    return found


def default_folder(root):
    for folder in (os.environ.get("RECON_MASTER"), os.path.join(root, "data", "master-db"),
                   "/mnt/project-files/master-db"):
        if folder and os.path.isdir(os.path.join(folder, "uk")):
            return folder
    return None


class Directory:
    def __init__(self, folder):
        self.folder = folder
        self.lock = threading.Lock()
        self._db = None
        self._kinds = {}

    @property
    def available(self):
        return bool(self.folder) and any(self.files(g) for g in GROUPS)

    def db(self):
        if self._db is None:
            try:
                import duckdb  # Already needed for Overture.
            except ImportError:
                raise ValueError("Searching the master database needs DuckDB: "
                                 "python3 -m pip install duckdb") from None
            self._db = duckdb.connect()
            self._db.execute("SET enable_progress_bar = false")
        return self._db

    def files(self, group, area=""):
        if group not in GROUPS:
            raise ValueError("Choose the UK, the US or elsewhere")
        if area:
            if not AREA.match(area):
                raise ValueError("Unknown area")
            path = os.path.join(self.folder, group, area + ".parquet")
            if not os.path.exists(path):
                raise LookupError(f"No {area} in the master database")
            return [path]
        return sorted(glob.glob(os.path.join(self.folder, group, "*.parquet")))

    # What's in it -----------------------------------------------------------

    def status(self):
        if not self.available:
            return {"available": False, "folder": self.folder}
        groups = {}
        for group in GROUPS:
            counts = {}
            path = os.path.join(self.folder, group, "counts.csv")
            if os.path.exists(path):
                with open(path, newline="", encoding="utf-8") as handle:
                    for row in csv.DictReader(handle):
                        counts[row["area"]] = {k: int(v or 0) for k, v in row.items() if k != "area"}
            areas = [os.path.splitext(os.path.basename(p))[0] for p in self.files(group)]
            groups[group] = [{"area": a, **counts.get(a, {})} for a in areas]
        return {"available": True, "folder": self.folder, "groups": groups,
                "sources": self.sources()}

    def sources(self):
        path = os.path.join(self.folder, "sources.csv")
        if not os.path.exists(path):
            return []
        with open(path, newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    def kinds(self, group):
        if group not in self._kinds:
            sql = f"SELECT kind, count(*) FROM {SOURCE} GROUP BY 1 ORDER BY 2 DESC LIMIT 40"
            with self.lock:
                rows = self.db().execute(sql, [self.files(group)]).fetchall()
            self._kinds[group] = [{"kind": k, "count": n} for k, n in rows if k]
        return self._kinds[group]

    # Searching --------------------------------------------------------------


    @staticmethod
    def _match(groups, field):
        """SQL for the search words against one field, and its parameters."""
        alternatives, params = [], []
        for words in groups:
            # ILIKE first because it is quick; the pattern then insists on a
            # whole word, so "plumb" finds plumbers but not Plumbland.
            alternatives.append("(" + " AND ".join(
                f"({field} ILIKE ? AND regexp_matches({field}, ?, 'i'))" for _ in words) + ")")
            for word in words:
                params += [f"%{word}%", rf"\b{re.escape(word)}{ENDINGS}\b"]
        return "(" + " OR ".join(alternatives) + ")", params

    def _where(self, query):
        clauses, params = [], []
        groups = terms(one(query, "q"))
        if groups:
            sql, more = self._match(groups, "concat_ws(' ', name, category, kind)")
            clauses.append(sql)
            params += more
        rule = one(query, "rule")
        if rule:
            clauses.append("can_email = ?")
            params.append(rule)
        kind = one(query, "kind")
        if kind:
            clauses.append("kind ILIKE ?")
            params.append(f"%{kind}%")
        town = one(query, "town")
        if town:
            clauses.append("(town ILIKE ? OR postcode ILIKE ?)")
            params += [f"%{town}%", f"{town}%"]
        has = set(query.get("has", []))
        for field, column in (("email", "emails"), ("phone", "phones"), ("website", "website"),
                              ("person", "people")):
            if field in has:
                clauses.append(f"coalesce({column}, '') <> ''")
        return (" WHERE " + " AND ".join(clauses)) if clauses else "", params

    def search(self, query):
        group = one(query, "group", "uk")
        files = self.files(group, one(query, "area"))
        where, params = self._where(query)
        page = max(int(one(query, "page", "1") or 1), 1)
        size = min(max(int(one(query, "size", "50") or 50), 1), 200)
        groups = terms(one(query, "q"))
        named, named_params = self._match(groups, "name") if groups else ("false", [])
        with self.lock:
            db = self.db()
            db.execute(f"""CREATE OR REPLACE TEMP TABLE found AS
                           SELECT {', '.join(COLUMNS)}, {named} AS named,
                                  regexp_extract(filename, '([^/\\\\]+)\\.parquet$', 1) AS area
                           FROM {SOURCE}{where}""", [*named_params, files, *params])
            total, with_email, may_email, with_phone, with_site = db.execute(
                """SELECT count(*), count(*) FILTER (coalesce(emails, '') <> ''),
                          count(*) FILTER (can_email = 'can email'),
                          count(*) FILTER (coalesce(phones, '') <> ''),
                          count(*) FILTER (coalesce(website, '') <> '') FROM found""").fetchone()
            by_area = db.execute("""SELECT area, count(*) FROM found GROUP BY 1
                                    ORDER BY 2 DESC LIMIT 60""").fetchall()
            by_source = db.execute("""SELECT trim(s) AS source, count(*) FROM
                                      (SELECT unnest(string_split(sources, ';')) AS s FROM found)
                                      GROUP BY 1 ORDER BY 2 DESC LIMIT 12""").fetchall()
            # Rows with an email first, then a phone, so the useful ones lead.
            # Name matches first (a plumber, not a museum that mentions plumbing),
            # then those with an email, then a phone.
            rows = db.execute(f"""SELECT * EXCLUDE (named) FROM found
                                  ORDER BY named DESC, coalesce(emails, '') = '',
                                           coalesce(phones, '') = '', name
                                  LIMIT {size} OFFSET {(page - 1) * size}""")
            names = [d[0] for d in rows.description]
            rows = [{k: ("" if v is None else str(v)) for k, v in zip(names, r)} for r in rows.fetchall()]
            db.execute("DROP TABLE found")
        return {"total": total, "with_email": with_email, "may_email": may_email,
                "with_phone": with_phone, "with_website": with_site, "page": page, "size": size,
                "by_area": [{"area": a, "count": n} for a, n in by_area],
                "by_source": [{"source": s, "count": n} for s, n in by_source if s],
                "rows": rows}

    def export(self, query):
        """A CSV file of every match (up to EXPORT_LIMIT), as a temporary path."""
        group = one(query, "group", "uk")
        files = self.files(group, one(query, "area"))
        where, params = self._where(query)
        handle, path = tempfile.mkstemp(suffix=".csv")
        os.close(handle)
        with self.lock:
            self.db().execute(
                f"""COPY (SELECT {', '.join(COLUMNS)},
                                 regexp_extract(filename, '([^/\\\\]+)\\.parquet$', 1) AS area
                          FROM {SOURCE}{where}
                          ORDER BY coalesce(emails, '') = '', name LIMIT {EXPORT_LIMIT})
                    TO '{path}' (HEADER, DELIMITER ',')""", [files, *params])
        return path


def one(query, key, default=""):
    values = query.get(key) or [default]
    return values[0]
