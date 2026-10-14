"""Numbers and map points for the website's dashboard.

Two jobs, both read-only:

- overview(): the headline numbers for the front page, read from the small
  summary files the master database already writes (counts.csv per country,
  sources.csv, trades/summary.csv), plus money figures from the trade lists
  when they carry them.
- places(query): businesses near a postcode or town, for the map. These come
  from the per-trade spreadsheets (master-db/trades/*.csv and the plumbers
  list), which are the only lists with a map position for every row.

A postcode or town is turned into a map position from the trade lists
themselves (the average position of the businesses sharing that postcode, or
in that town), so no outside service is needed.
"""

import csv
import glob
import math
import os
import re
import tempfile
import threading

GROUPS = ("uk", "us", "other")
MONEY = ("account_type", "size_band", "staff", "turnover", "net_assets", "accounts_to",
         "publishes_turnover")
POINT_LIMIT = 3000
EXPORT_LIMIT = 200_000
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
POSTCODE = re.compile(r"^[A-Z]{1,2}[0-9][A-Z0-9]?(?:[0-9][A-Z]{0,2})?$")
FULL = re.compile(r"^[A-Z]{1,2}[0-9][A-Z0-9]?[0-9][A-Z]{2}$")
AREA_LETTERS = re.compile(r"^[A-Z]{1,2}$")
PUBLISHES = "lower(coalesce(publishes_turnover, '')) IN ('yes', 'true', '1', 'y')"
# Size choices on the map -> what the trade lists' size_band starts with.
SIZES = {"micro": ["micro"], "small": ["small"], "medium-large": ["medium", "large"]}


def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def number(value):
    try:
        return int(float(value or 0))
    except ValueError:
        return 0


def one(query, key, default=""):
    values = query.get(key) or [default]
    return values[0]


def trade_name(slug):
    return slug.replace("-", " ").capitalize().replace(" and ", " and ")


class Dashboard:
    def __init__(self, folder, locate=None):
        self.folder = folder
        # A second way to find a place (the website passes GeoNames' postcode
        # centres), tried when the trade lists themselves don't know it.
        self.fallback = locate
        self.lock = threading.Lock()
        self._db = None
        self._loaded = None  # the trade files and their times, when loaded
        self._columns = set()

    # Files ------------------------------------------------------------------

    def trade_files(self):
        """{trade slug: path} for every list with a map position per row."""
        if not self.folder:
            return {}
        found = {}
        for path in sorted(glob.glob(os.path.join(self.folder, "trades", "*.csv"))):
            slug = os.path.splitext(os.path.basename(path))[0]
            if slug != "summary" and SLUG.match(slug):
                found[slug] = path
        for name in ("uk-plumbers-with-money.csv", "uk-plumbers-with-emails.csv"):
            plumbers = os.path.join(self.folder, "plumbers", name)
            if os.path.exists(plumbers):
                found.setdefault("plumbers", plumbers)
        return found

    def warm(self):
        try:
            self.money()
        except Exception:  # Only a head start: any problem shows on first use.
            pass

    def db(self):
        if self._db is None:
            try:
                import duckdb  # Already needed for Overture.
            except ImportError:
                raise ValueError("The dashboard needs DuckDB: python3 -m pip install duckdb") from None
            self._db = duckdb.connect(config={"memory_limit": "2GB", "threads": 2})
            self._db.execute("SET enable_progress_bar = false")
        return self._db

    def _load(self):
        """Read the trade lists into one table, again whenever a file changes."""
        files = self.trade_files()
        stamp = tuple((slug, path, os.path.getmtime(path)) for slug, path in files.items())
        if stamp == self._loaded:
            return
        if not files and self._loaded:
            return  # The shared folder blinked (files being republished): keep what we have.
        db = self.db()
        db.execute("DROP TABLE IF EXISTS places")
        if not files:
            self._columns = set()
            self._loaded = stamp
            return
        parts = []
        for slug, path in files.items():
            escaped = path.replace("'", "''")
            parts.append(f"""SELECT '{slug}' AS trade, * FROM read_csv('{escaped}', header = true,
                             all_varchar = true, union_by_name = true)""")
        db.execute("CREATE TABLE places AS " + " UNION ALL BY NAME ".join(parts))
        self._columns = {row[0] for row in db.execute("DESCRIBE places").fetchall()}
        # Missing columns become empty, so the queries below work on older lists.
        for column in ("lat", "lon", "email", "all_emails", "phone", "mobile", "website",
                       "contact_rule", "postcode", "town", "address", "company_number",
                       "company_type", "socials", "email_type", "category") + MONEY:
            if column not in self._columns:
                db.execute(f"ALTER TABLE places ADD COLUMN {column} VARCHAR")
        db.execute("""CREATE OR REPLACE TABLE places AS SELECT *,
                        TRY_CAST(lat AS DOUBLE) AS y, TRY_CAST(lon AS DOUBLE) AS x,
                        upper(replace(coalesce(postcode, ''), ' ', '')) AS pc,
                        CASE WHEN length(upper(replace(coalesce(postcode, ''), ' ', ''))) >= 5
                             THEN upper(replace(postcode, ' ', ''))[:-4] END AS outward
                      FROM places""")
        self._add_founded(db)
        self._loaded = stamp

    def _add_founded(self, db):
        """The year each registered company started, from the Companies House
        file in the master database, for the "started each year" chart."""
        db.execute("ALTER TABLE places ADD COLUMN IF NOT EXISTS founded INTEGER")
        found = sorted(glob.glob(os.path.join(self.folder, "companies-house", "*.parquet")))
        if not found:
            return
        try:
            db.execute("""UPDATE places SET founded = ch.year FROM (
                            SELECT CompanyNumber AS number,
                                   TRY_CAST(right(IncorporationDate, 4) AS INTEGER) AS year
                            FROM read_parquet(?)
                            WHERE CompanyNumber IN (SELECT company_number FROM places)) ch
                          WHERE places.company_number = ch.number""", [found[-1]])
        except Exception:  # Only a nice extra: the map works without it.
            pass

    # Front page -------------------------------------------------------------

    def overview(self):
        if not self.folder:
            return {"available": False}
        countries = {}
        for group in GROUPS:
            areas = [{"area": row["area"], **{k: number(v) for k, v in row.items() if k != "area"}}
                     for row in read_csv(os.path.join(self.folder, group, "counts.csv"))]
            totals = {}
            for area in areas:
                for key, value in area.items():
                    if key != "area":
                        totals[key] = totals.get(key, 0) + value
            countries[group] = {"totals": totals,
                                "areas": sorted(areas, key=lambda a: -a.get("organisations", 0))}
        sources = read_csv(os.path.join(self.folder, "sources.csv"))
        trades = [{k: (v if k == "trade" else number(v)) for k, v in row.items()}
                  for row in read_csv(os.path.join(self.folder, "trades", "summary.csv"))
                  if row.get("trade") and row["trade"] != "total"]
        return {
            "available": True,
            "countries": countries,
            "sources": [{"name": s.get("name", ""), "title": s.get("title", ""),
                         "country": s.get("country", ""), "licence": s.get("licence", ""),
                         "url": s.get("url", ""), "records": number(s.get("records")),
                         "with_email": number(s.get("with_email"))} for s in sources],
            "trades": trades,
            "money": self.money(),
        }

    def money(self, where="", params=()):
        """Who publishes their money: counts by size and by what they file."""
        with self.lock:
            self._load()
            if not self._loaded or not (self._columns & set(MONEY)):
                return {"available": False}
            db = self.db()
            base = f"FROM places{where}"
            total, with_number, publishes, worth, staff = db.execute(
                f"""SELECT count(*), count(*) FILTER (coalesce(company_number, '') <> ''),
                           count(*) FILTER ({PUBLISHES}),
                           count(*) FILTER (TRY_CAST(net_assets AS DOUBLE) IS NOT NULL),
                           count(*) FILTER (TRY_CAST(staff AS DOUBLE) IS NOT NULL)
                    {base}""", list(params)).fetchone()
            bands = db.execute(f"""SELECT coalesce(nullif(size_band, ''), 'not known'), count(*)
                                   {base} GROUP BY 1 ORDER BY 2 DESC""", list(params)).fetchall()
            accounts = db.execute(f"""SELECT coalesce(nullif(account_type, ''), 'not known'),
                                      count(*) {base} GROUP BY 1 ORDER BY 2 DESC LIMIT 12""",
                                  list(params)).fetchall()
        return {"available": True, "total": total, "registered": with_number,
                "publishes_turnover": publishes, "with_net_assets": worth, "with_staff": staff,
                "size_bands": [{"band": b, "count": n} for b, n in bands],
                "account_types": [{"type": t, "count": n} for t, n in accounts]}

    # The map ----------------------------------------------------------------

    def locate(self, place):
        """A postcode, part of a postcode or a town -> (lat, lon, label)."""
        text = (place or "").strip()
        if not text:
            return None
        db = self.db()
        code = text.upper().replace(" ", "")
        if POSTCODE.match(code) or AREA_LETTERS.match(code):
            # The whole postcode, then its first half (BN1 1AA -> BN1), then the
            # area letters (BN). BN1 must not also catch BN11 in Worthing.
            tries = []
            if FULL.match(code):
                tries += [("pc = ?", code), ("outward = ?", code[:-3])]
            elif not AREA_LETTERS.match(code):
                tries.append(("outward = ?", code))
            letters = re.match(r"[A-Z]+", code).group(0)
            tries.append(("regexp_matches(pc, ?)", f"^{letters}[0-9]"))
            for test, value in tries:
                y, x, n = db.execute(f"""SELECT avg(y), avg(x), count(*) FROM places
                                         WHERE y IS NOT NULL AND {test}""", [value]).fetchone()
                if n:
                    matched = value.replace("^", "").replace("[0-9]", "")
                    return {"lat": y, "lon": x, "label": text.upper(), "matched": matched}
        y, x, n = db.execute("""SELECT median(y), median(x), count(*) FROM places
                                WHERE y IS NOT NULL AND (town ILIKE ? OR address ILIKE ?)""",
                             [text, f"%, {text}%"]).fetchone()
        if n:
            return {"lat": y, "lon": x, "label": text.title(), "matched": text}
        if self.fallback:
            try:
                y, x, label = self.fallback(text)
                return {"lat": y, "lon": x, "label": label, "matched": text}
            except (LookupError, ValueError):
                pass
        return None

    def _where(self, query, centre, radius):
        clauses, params = ["y IS NOT NULL"], []
        trades = [t for t in query.get("trade", []) if t]
        for trade in trades:
            if not SLUG.match(trade):
                raise ValueError("Unknown trade")
        if trades:
            clauses.append("trade IN (" + ", ".join("?" for _ in trades) + ")")
            params += trades
        if centre:
            # A box first (quick), then the real distance in miles.
            dy = radius / 69.0
            dx = radius / (69.0 * max(math.cos(math.radians(centre["lat"])), 0.1))
            clauses.append("y BETWEEN ? AND ? AND x BETWEEN ? AND ?")
            params += [centre["lat"] - dy, centre["lat"] + dy, centre["lon"] - dx, centre["lon"] + dx]
            clauses.append(f"{distance(centre)} <= ?")
            params.append(radius)
        rule = one(query, "rule")
        if rule:
            clauses.append("contact_rule = ?")
            params.append(rule)
        has = set(query.get("has", []))
        for field, column in (("email", "coalesce(email, all_emails)"), ("phone", "phone"),
                              ("mobile", "mobile"), ("website", "website")):
            if field in has:
                clauses.append(f"coalesce({column}, '') <> ''")
        if "money" in has:
            clauses.append(PUBLISHES)
        if "worth" in has:
            clauses.append("TRY_CAST(net_assets AS DOUBLE) IS NOT NULL")
        if "company" in has:
            clauses.append("coalesce(company_number, '') <> ''")
        size = one(query, "size")
        if size:
            if size not in SIZES:
                raise ValueError("Unknown size")
            clauses.append("(" + " OR ".join("size_band ILIKE ?" for _ in SIZES[size]) + ")")
            params += [f"{band}%" for band in SIZES[size]]
        worth = one(query, "worth")
        if worth:
            clauses.append("TRY_CAST(net_assets AS DOUBLE) >= ?")
            params.append(float(worth))
        return " WHERE " + " AND ".join(clauses), params

    def places(self, query):
        radius = miles(query)
        with self.lock:
            self._load()
            if not self._loaded:
                return {"available": False}
            place = one(query, "near")
            centre = self.locate(place) if place else None
            if place and not centre:
                raise LookupError(f"Couldn't find {place}. Try a postcode such as BN1 or a town name.")
            where, params = self._where(query, centre, radius)
            db = self.db()
            total, with_email, may, with_phone, with_mobile, with_site = db.execute(
                f"""SELECT count(*), count(*) FILTER (coalesce(email, all_emails, '') <> ''),
                           count(*) FILTER (contact_rule = 'can email'),
                           count(*) FILTER (coalesce(phone, '') <> ''),
                           count(*) FILTER (coalesce(mobile, '') <> ''),
                           count(*) FILTER (coalesce(website, '') <> '')
                    FROM places{where}""", params).fetchone()
            by_trade = db.execute(f"""SELECT trade, count(*) FROM places{where}
                                      GROUP BY 1 ORDER BY 2 DESC""", params).fetchall()
            order = f"{distance(centre)}," if centre else ""
            rows = db.execute(
                f"""SELECT trade, name, address, town, postcode, y, x, website,
                           coalesce(nullif(email, ''), split_part(all_emails, ' (', 1)) AS email,
                           email_type, phone, mobile, contact_rule, company_number, company_type,
                           socials, size_band, turnover, staff, net_assets, account_type,
                           accounts_to, publishes_turnover
                    FROM places{where}
                    ORDER BY {order} coalesce(email, all_emails, '') = '', name
                    LIMIT {POINT_LIMIT}""", params)
            names = [d[0] for d in rows.description]
            points = [dict(zip(names, r)) for r in rows.fetchall()]
            districts = db.execute(f"""SELECT outward, count(*), count(*) FILTER (contact_rule = 'can email')
                                       FROM places{where} AND outward IS NOT NULL
                                       GROUP BY 1 ORDER BY 3 DESC, 2 DESC LIMIT 8""", params).fetchall()
            founded = self._founded(where, params)
        for point in points:
            point["lat"] = point.pop("y")
            point["lon"] = point.pop("x")
            for key, value in point.items():
                if value is None:
                    point[key] = ""
            if centre:
                point["miles"] = round(haversine(centre, point), 2)
        return {"available": True, "centre": centre, "miles": radius, "total": total,
                "by_district": [{"district": d, "count": n, "may_email": m} for d, n, m in districts],
                "founded": founded,
                "with_email": with_email, "may_email": may, "with_phone": with_phone,
                "with_mobile": with_mobile, "with_website": with_site,
                "by_trade": [{"trade": t, "name": trade_name(t), "count": n} for t, n in by_trade],
                "trades": [{"trade": t, "name": trade_name(t)} for t in self.trade_files()],
                "money": self.money_for(where, params),
                "shown": len(points), "points": points}

    def _founded(self, where, params):
        # Called with the lock held: companies started each year, the last 20 years.
        rows = self.db().execute(f"""SELECT founded, count(*) FROM places{where}
                                     AND founded >= year(current_date) - 19
                                     GROUP BY 1 ORDER BY 1""", params).fetchall()
        return [{"year": y, "count": n} for y, n in rows]

    def heat(self, query):
        """The whole country in postcode districts (BN1, LS1 ...): where each
        one sits, how many businesses it has and how many may be emailed."""
        with self.lock:
            self._load()
            if not self._loaded:
                return {"available": False}
            where, params = self._where(query, None, 0)
            rows = self.db().execute(
                f"""SELECT outward, avg(y), avg(x), count(*),
                           count(*) FILTER (contact_rule = 'can email')
                    FROM places{where} AND outward IS NOT NULL
                    GROUP BY 1 ORDER BY 4 DESC""", params).fetchall()
            founded = self._founded(where, params)
        return {"available": True, "founded": founded,
                "trades": [{"trade": t, "name": trade_name(t)} for t in self.trade_files()],
                "districts": [{"district": d, "lat": round(y, 4), "lon": round(x, 4),
                               "count": n, "may_email": m} for d, y, x, n, m in rows]}

    def money_for(self, where, params):
        # Called with the lock held: same as money(), without taking it again.
        if not (self._columns & set(MONEY)):
            return {"available": False}
        db = self.db()
        total, registered, publishes, worth = db.execute(
            f"""SELECT count(*), count(*) FILTER (coalesce(company_number, '') <> ''),
                       count(*) FILTER ({PUBLISHES}),
                       count(*) FILTER (TRY_CAST(net_assets AS DOUBLE) IS NOT NULL)
                FROM places{where}""", params).fetchone()
        bands = db.execute(f"""SELECT coalesce(nullif(size_band, ''), 'not known'), count(*)
                               FROM places{where} GROUP BY 1 ORDER BY 2 DESC""", params).fetchall()
        return {"available": True, "total": total, "registered": registered,
                "publishes_turnover": publishes, "with_net_assets": worth,
                "size_bands": [{"band": b, "count": n} for b, n in bands]}

    def export(self, query):
        """Every business in the chosen area as a CSV file (a temporary path)."""
        radius = miles(query)
        with self.lock:
            self._load()
            place = one(query, "near")
            centre = self.locate(place) if place else None
            if place and not centre:
                raise LookupError(f"Couldn't find {place}")
            where, params = self._where(query, centre, radius)
            handle, path = tempfile.mkstemp(suffix=".csv")
            os.close(handle)
            extra = f", round({distance(centre)}, 2) AS miles_away" if centre else ""
            order = f"{distance(centre)}," if centre else ""
            self.db().execute(
                f"""COPY (SELECT * EXCLUDE (y, x, pc, outward){extra} FROM places{where}
                          ORDER BY {order} name LIMIT {EXPORT_LIMIT})
                    TO '{path}' (HEADER, DELIMITER ',')""", params)
        return path


def miles(query):
    try:
        return min(max(float(one(query, "miles", "5") or 5), 0.2), 100)
    except ValueError:
        raise ValueError("Choose a distance in miles") from None


def distance(centre):
    """SQL for the distance in miles from the centre to each row."""
    lat, lon = float(centre["lat"]), float(centre["lon"])
    return (f"(3958.8 * 2 * asin(sqrt(pow(sin(radians(y - {lat}) / 2), 2) + "
            f"cos(radians({lat})) * cos(radians(y)) * pow(sin(radians(x - {lon}) / 2), 2))))")


def haversine(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (a["lat"], a["lon"], b["lat"], b["lon"]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 3958.8 * 2 * math.asin(math.sqrt(h))
