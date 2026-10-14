"""Search the master database (built by recon.master) for the website.

The master database is a folder of parquet files, one per area (a big area
may instead be a folder of parts, england/part-0.parquet and so on):
uk/england.parquet, us/ca.parquet, other/<country>.parquet and so on, each
with one row per organisation. This module only reads them, with DuckDB.

A search is plain words for the trade, such as "plumbers" or "dental,
dentist". Commas separate alternatives; words within one alternative must all
appear in the organisation's name, trade description or kind. Words are cut
to their stem, so "plumbers" also finds "plumbing".

A search can also be limited to a circle: "near" a postcode, ZIP code or town,
within so many miles. Positions come from GeoNames' free postcode files
(CC BY 4.0, https://www.geonames.org): every UK postcode and US ZIP code with
its centre. The registers give a postcode but rarely a position, so each
organisation is placed at its postcode's centre, which is close enough for a
map. The files are downloaded once to data/geo/.
"""

import csv
import glob
import math
import os
import re
import tempfile
import threading
import urllib.request
import zipfile

GROUPS = ("uk", "us", "other")
COLUMNS = ["name", "kind", "category", "legal_form", "address", "town", "region", "postcode",
           "country", "website", "emails", "phones", "socials", "people", "can_email", "sources"]
EXPORT_LIMIT = 1_000_000
SOURCE = "read_parquet(?, filename = true, union_by_name = true)"
AREA = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
ENDINGS = "(?:e|es|s|er|ers|ing|ings|ed|y|ies|al|ist|ists|ry|ery|ian|ians)?"
WORD = re.compile(r"[a-z0-9&']+")
MAP_LIMIT = 3000
MILES = 3958.8  # The Earth's radius.
# Postcode centres, and how a register's postcode is written to match them.
POSTCODES = {
    "uk": ("https://download.geonames.org/export/zip/GB_full.csv.zip", "GB_full.txt",
           "upper(replace(coalesce({}, ''), ' ', ''))"),
    "us": ("https://download.geonames.org/export/zip/US.zip", "US.txt",
           "left(regexp_replace(coalesce({}, ''), '[^0-9]', '', 'g'), 5)"),
}
UK_POSTCODE = re.compile(r"^[A-Z]{1,2}[0-9][0-9A-Z]?([0-9][A-Z]{2})?$")


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


def distance(lat, lon, middle=None):
    """SQL for the miles from (lat, lon) columns to a point: the middle given,
    as numbers, or else three parameters (latitude, latitude, longitude)."""
    at, along = (float(middle[0]), float(middle[1])) if middle else ("?", "?")
    return (f"{MILES} * 2 * asin(sqrt(power(sin(radians({lat} - {at}) / 2), 2) + "
            f"cos(radians({at})) * cos(radians({lat})) * power(sin(radians({lon} - {along}) / 2), 2)))")


class Directory:
    def __init__(self, folder, geo=os.path.join("data", "geo")):
        self.folder = folder
        self.geo = geo
        self.lock = threading.RLock()
        self._db = None
        self._kinds = {}
        self._postcodes = {}

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

    def _area_files(self, group, area):
        """A big area comes as a folder of parts (england/part-0.parquet ...),
        because very large files don't reach every computer; prefer those."""
        parts = sorted(glob.glob(os.path.join(self.folder, group, area, "part-*.parquet")))
        if parts:
            return parts
        path = os.path.join(self.folder, group, area + ".parquet")
        return [path] if os.path.exists(path) else []

    def areas(self, group):
        if group not in GROUPS:
            raise ValueError("Choose the UK, the US or elsewhere")
        root = os.path.join(self.folder or "", group)
        found = {os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(root, "*.parquet"))}
        found |= {os.path.basename(os.path.dirname(p)) for p in glob.glob(os.path.join(root, "*", "part-*.parquet"))}
        return sorted(a for a in found if AREA.match(a))

    def files(self, group, area=""):
        if group not in GROUPS:
            raise ValueError("Choose the UK, the US or elsewhere")
        if area:
            if not AREA.match(area):
                raise ValueError("Unknown area")
            paths = self._area_files(group, area)
            if not paths:
                raise LookupError(f"No {area} in the master database")
            return paths
        paths = [p for a in self.areas(group) for p in self._area_files(group, a)]
        if not paths:  # The shared folder can blink while files are republished.
            raise LookupError("The master database can't be read just now. Try again in a minute.")
        return paths

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
            areas = self.areas(group)
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

    # Positions --------------------------------------------------------------

    def postcodes(self, group):
        """Name of the table of postcode centres for the UK or US, loading it the
        first time. None for elsewhere, or when the file can't be had."""
        if group not in POSTCODES:
            return None
        if group not in self._postcodes:
            if not self.geo:
                return None
            table = f"postcodes_{group}"
            cache = os.path.join(self.geo, f"{group}-postcodes.parquet")
            if not os.path.exists(cache):
                self._postcode_cache(group, cache)
            self.db().execute(f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM read_parquet(?)",
                              [cache])
            self._postcodes[group] = table
        return self._postcodes[group]

    def _postcode_cache(self, group, cache):
        """Turn GeoNames' download into a small file of postcode centres."""
        url, member, written = POSTCODES[group]
        os.makedirs(self.geo, exist_ok=True)
        archive = os.path.join(self.geo, os.path.basename(url))
        if not os.path.exists(archive):
            try:
                urllib.request.urlretrieve(url, archive + ".part")
            except OSError as error:
                raise ValueError(f"Couldn't download the postcode file ({error})") from None
            os.replace(archive + ".part", archive)
        text = os.path.join(self.geo, member)
        with zipfile.ZipFile(archive) as zipped:
            zipped.extract(member, self.geo)
        try:
            self.db().execute(f"""COPY (
                SELECT {written.format('code')} AS code, any_value(place) AS place,
                       any_value(state) AS state, any_value(state_code) AS state_code,
                       any_value(county) AS county, avg(lat) AS lat, avg(lon) AS lon
                FROM read_csv(?, delim = '\t', header = false, quote = '',
                              columns = {{'country': 'VARCHAR', 'code': 'VARCHAR', 'place': 'VARCHAR',
                                         'state': 'VARCHAR', 'state_code': 'VARCHAR',
                                         'county': 'VARCHAR', 'c2': 'VARCHAR', 'c3': 'VARCHAR',
                                         'c4': 'VARCHAR', 'lat': 'DOUBLE', 'lon': 'DOUBLE',
                                         'accuracy': 'VARCHAR'}})
                WHERE lat IS NOT NULL
                GROUP BY 1) TO '{cache}' (FORMAT parquet)""", [text])
        finally:
            os.remove(text)

    def locate(self, group, place):
        """Where a postcode, ZIP code or town is: (latitude, longitude, label).
        A UK postcode's first half ("BS1") gives the middle of that district."""
        with self.lock:
            table = self.postcodes(group)
        if not table:
            raise ValueError("Distances work for the UK and the US only")
        place = " ".join((place or "").split())
        code = place.upper().replace(" ", "")
        attempts = []
        if group == "uk" and UK_POSTCODE.match(code):
            attempts += [("code = ?", code), ("left(code, length(code) - 3) = ?", code)]
        if group == "us" and re.fullmatch(r"\d{5}(-?\d{4})?", code):
            attempts.append(("code = ?", code[:5]))
        town, _, state = place.partition(",")
        if state.strip():  # "Austin, TX" or "Austin, Texas"
            attempts.append(("lower(place) = lower(?) AND lower(?) IN (lower(state), lower(state_code))",
                             (town.strip(), state.strip())))
        attempts += [("lower(place) = lower(?)", place), ("lower(county) = lower(?)", place)]
        with self.lock:
            for where, value in attempts:
                values = list(value) if isinstance(value, tuple) else [value]
                # A town name can be in more than one nation or state (Newport,
                # Springfield): take the one with the most postcodes.
                found = self.db().execute(
                    f"""SELECT avg(lat), avg(lon), count(*), state FROM {table} WHERE {where}
                        GROUP BY state ORDER BY 3 DESC LIMIT 1""", values).fetchone()
                if found:
                    label = place.upper() if where.startswith(("code", "left")) else \
                        f"{place.split(',')[0].title()}, {found[3]}" if found[3] else place.title()
                    return found[0], found[1], label
        raise LookupError(f"Couldn't find {place}. Try a postcode instead.")

    def _near(self, query, group):
        """SQL limiting a search to a circle, its parameters, and the circle."""
        place = one(query, "near").strip()
        if not place:
            return "", [], None
        try:
            miles = min(max(float(one(query, "miles", "5") or 5), 0.5), 100)
        except ValueError:
            raise ValueError("Choose a distance in miles") from None
        lat, lon, label = self.locate(group, place)
        table = self.postcodes(group)
        # A box first because it is quick, then the true distance.
        rise = miles / 69.0
        reach = miles / max(69.0 * math.cos(math.radians(lat)), 1)
        sql = (f"{POSTCODES[group][2].format('postcode')} IN (SELECT code FROM {table} "
               f"WHERE lat BETWEEN ? AND ? AND lon BETWEEN ? AND ? AND "
               f"{distance('lat', 'lon')} <= ?)")
        params = [lat - rise, lat + rise, lon - reach, lon + reach, lat, lat, lon, miles]
        return sql, params, {"lat": lat, "lon": lon, "miles": miles, "label": label}

    def _within(self, group, files, circle):
        """Only the area files (nations or states) the circle touches, plus
        "unknown", so a search near Austin doesn't read every state."""
        table = self.postcodes(group)
        rise = circle["miles"] / 69.0
        reach = circle["miles"] / max(69.0 * math.cos(math.radians(circle["lat"])), 1)
        with self.lock:
            rows = self.db().execute(
                f"""SELECT DISTINCT state, state_code FROM {table}
                    WHERE lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?""",
                [circle["lat"] - rise, circle["lat"] + rise,
                 circle["lon"] - reach, circle["lon"] + reach]).fetchall()
        names = {"unknown"}
        for state, code in rows:
            if not state:  # Jersey, Guernsey and the Isle of Man have no nation.
                names.add("crown-dependencies")
            names.add(re.sub(r"[^a-z0-9]+", "-", (state or "").lower()).strip("-"))
            names.add((code or "").lower())
        kept = [f for f in files if area_of(f) in names]
        return kept or files

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

    def _where(self, query, group):
        clauses, params = [], []
        near, more, circle = self._near(query, group)
        if near:
            clauses.append(near)
            params += more
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
        return (" WHERE " + " AND ".join(clauses)) if clauses else "", params, circle

    def _placed(self, group, inner, circle):
        """SQL adding lat, lon and miles (from the circle's middle) to the rows of
        another query, from their postcodes, and any parameters it adds."""
        try:
            with self.lock:
                table = self.postcodes(group)
        except ValueError:
            table = None  # No postcode file: the list still works, without a map.
        if not table:
            return (f"SELECT *, NULL::DOUBLE AS lat, NULL::DOUBLE AS lon, NULL::DOUBLE AS miles "
                    f"FROM ({inner})"), []
        # The middle goes in as numbers, as parameters here would come before the
        # inner query's own.
        miles = distance("p.lat", "p.lon", (circle["lat"], circle["lon"])) if circle else "NULL::DOUBLE"
        return (f"SELECT f.*, p.lat, p.lon, {miles} AS miles FROM ({inner}) f "
                f"LEFT JOIN {table} p ON p.code = {POSTCODES[group][2].format('f.postcode')}"), []

    def search(self, query):
        group = one(query, "group", "uk")
        files = self.files(group, one(query, "area"))
        where, params, circle = self._where(query, group)
        if circle and not one(query, "area"):
            files = self._within(group, files, circle)
        page = max(int(one(query, "page", "1") or 1), 1)
        size = min(max(int(one(query, "size", "50") or 50), 1), 200)
        groups = terms(one(query, "q"))
        named, named_params = self._match(groups, "name") if groups else ("false", [])
        found = f"""SELECT {', '.join(COLUMNS)}, {named} AS named,
                           regexp_extract(filename, '([^/\\\\]+?)([/\\\\]part-[0-9]+)?\\.parquet$', 1) AS area
                    FROM {SOURCE}{where}"""
        found_params = [*named_params, files, *params]
        if circle:  # Few rows, so place them all now and put the nearest first.
            found, more = self._placed(group, found, circle)
            found_params += more
        # Name matches first (a plumber, not a museum that mentions plumbing),
        # then those with an email, then a phone, then the nearest.
        order = ("named DESC, coalesce(emails, '') = '', coalesce(phones, '') = '', "
                 + ("miles, " if circle else "") + "name")
        with self.lock:
            db = self.db()
            db.execute(f"CREATE OR REPLACE TEMP TABLE found AS {found}", found_params)
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
            rows_sql = f"SELECT * FROM found ORDER BY {order} LIMIT {size} OFFSET {(page - 1) * size}"
            rows_params = []
            if not circle:
                rows_sql, rows_params = self._placed(group, rows_sql, None)
            rows = self._rows(db.execute(f"SELECT * EXCLUDE (named) FROM ({rows_sql}) ORDER BY {order}",
                                         rows_params))
            # The map: every match with a position, up to MAP_LIMIT, best first.
            # Only on the first page, as turning pages doesn't change it.
            points, placed = [], 0
            if page == 1:
                map_sql, map_params = ("SELECT * FROM found", []) if circle else \
                    self._placed(group, "SELECT * FROM found", None)
                db.execute(f"CREATE OR REPLACE TEMP TABLE pinned AS {map_sql}", map_params)
                placed = db.execute("SELECT count(*) FROM pinned WHERE lat IS NOT NULL").fetchone()[0]
                points = self._rows(db.execute(
                    f"""SELECT * EXCLUDE (named) REPLACE (left(category, 300) AS category)
                        FROM pinned WHERE lat IS NOT NULL ORDER BY {order} LIMIT {MAP_LIMIT}"""))
                db.execute("DROP TABLE pinned")
            db.execute("DROP TABLE found")
        return {"total": total, "with_email": with_email, "may_email": may_email,
                "with_phone": with_phone, "with_website": with_site, "page": page, "size": size,
                "by_area": [{"area": a, "count": n} for a, n in by_area],
                "by_source": [{"source": s, "count": n} for s, n in by_source if s],
                "rows": rows, "circle": circle, "placed": placed, "points": points}

    @staticmethod
    def _rows(result):
        names = [d[0] for d in result.description]
        return [{k: ("" if v is None else round(v, 5) if isinstance(v, float) else str(v))
                 for k, v in zip(names, r)} for r in result.fetchall()]

    def export(self, query):
        """A CSV file of every match (up to EXPORT_LIMIT), as a temporary path."""
        group = one(query, "group", "uk")
        files = self.files(group, one(query, "area"))
        where, params, circle = self._where(query, group)
        if circle and not one(query, "area"):
            files = self._within(group, files, circle)
        inner = f"""SELECT {', '.join(COLUMNS)},
                           regexp_extract(filename, '([^/\\\\]+?)([/\\\\]part-[0-9]+)?\\.parquet$', 1) AS area
                    FROM {SOURCE}{where}"""
        placed, more = self._placed(group, inner, circle)
        order = "coalesce(emails, '') = '', " + ("miles, " if circle else "") + "name"
        handle, path = tempfile.mkstemp(suffix=".csv")
        os.close(handle)
        with self.lock:
            self.db().execute(
                f"""COPY (SELECT * {'' if circle else 'EXCLUDE (miles)'} FROM ({placed})
                          ORDER BY {order} LIMIT {EXPORT_LIMIT})
                    TO '{path}' (HEADER, DELIMITER ',')""", [files, *params, *more])
        return path


def area_of(path):
    """uk/wales.parquet -> wales; uk/england/part-2.parquet -> england."""
    name = os.path.splitext(os.path.basename(path))[0]
    return os.path.basename(os.path.dirname(path)) if re.fullmatch(r"part-\d+", name) else name


def one(query, key, default=""):
    values = query.get(key) or [default]
    return values[0]
