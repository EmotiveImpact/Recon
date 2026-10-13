"""Recon's website: projects, target lists, runs and results in a browser.

    python3 -m recon.server            # then open http://localhost:8765

It serves the built site in web/dist and a small JSON API the site talks to.
It only listens on this computer by default, because the results hold
business contact details: never put it on the open internet.

Projects are products Edem sells (SALEANE first), saved in projects/. Each has
target lists in targets/ (their "project" field names the project). Runs are
the ordinary command line in the background, so the site never does anything
the command line can't.
"""

import argparse
import csv
import glob
import importlib.util
import io
import json
import mimetypes
import os
import re
import subprocess
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import directory, finder, places
from .target import COUNTRY_BOX, Target

SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
STEPS = ["run", "places", "companies", "rules", "people", "emails", "verify", "export"]
COUNTRIES = {"GB": "United Kingdom", "IE": "Ireland", "US": "United States"}
PAGE_MAX = 500


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:64] or "untitled"


class Workspace:
    """Files on disk, under one folder (the repository by default)."""

    def __init__(self, root, master=None):
        self.root = os.path.abspath(root)
        self.directory = directory.Directory(master or directory.default_folder(self.root),
                                             geo=os.path.join(self.root, "data", "geo"))
        self.projects_dir = os.path.join(self.root, "projects")
        self.targets_dir = os.path.join(self.root, "targets")
        self._results = {}  # path -> (mtime, rows)
        self.runs = Runs(self)

    # Projects -------------------------------------------------------------

    def _project_file(self, slug):
        return os.path.join(self.projects_dir, slug + ".json")

    def projects(self):
        found = {}
        for path in sorted(glob.glob(os.path.join(self.projects_dir, "*.json"))):
            slug = os.path.splitext(os.path.basename(path))[0]
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
            found[data.get("name", slug)] = {"slug": slug, "name": data.get("name", slug),
                                             "description": data.get("description", ""),
                                             "targets": []}
        for target in self.targets():
            name = target["project"] or "Unsorted"
            if name not in found:  # A target list naming a project with no file yet.
                found[name] = {"slug": slugify(name), "name": name, "description": "",
                               "targets": []}
            found[name]["targets"].append(target)
        return list(found.values())

    def save_project(self, data, slug=None):
        name = str(data.get("name", "")).strip()
        if not name:
            raise ValueError("A project needs a name")
        slug = slug or slugify(name)
        check_slug(slug)
        old = self._project_file(slug)
        renamed_from = None
        if os.path.exists(old):
            with open(old, encoding="utf-8") as handle:
                renamed_from = json.load(handle).get("name")
        write_json(old, {"name": name, "description": str(data.get("description", "")).strip()})
        if renamed_from and renamed_from != name:
            for target in self.targets():
                if target["project"] == renamed_from:
                    content = self.target(target["slug"])
                    content["project"] = name
                    write_json(self._target_file(target["slug"]), content)
        return slug

    # Target lists ---------------------------------------------------------

    def _target_file(self, slug):
        check_slug(slug)
        return os.path.join(self.targets_dir, slug + ".json")

    def targets(self):
        found = []
        for path in sorted(glob.glob(os.path.join(self.targets_dir, "*.json"))):
            slug = os.path.splitext(os.path.basename(path))[0]
            if not SLUG.match(slug):
                continue
            try:
                with open(path, encoding="utf-8") as handle:
                    data = json.load(handle)
            except (OSError, ValueError):
                continue
            result = self.result_file(slug)
            found.append({
                "slug": slug, "name": data.get("name", slug), "project": data.get("project", ""),
                "country": data.get("country", ""), "notes": data.get("notes", ""),
                "sectors": list(data.get("sectors", {})),
                "results": self.summary(slug) if result else None,
                "running": self.runs.active(slug),
            })
        return found

    def target(self, slug):
        path = self._target_file(slug)
        if not os.path.exists(path):
            raise LookupError(f"No target list called {slug}")
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)

    def save_target(self, data, slug=None):
        clean = clean_target(data)
        new = slug is None
        slug = slug or slugify(clean["name"])
        path = self._target_file(slug)
        if new and os.path.exists(path):
            raise ValueError("There is already a target list with that name")
        if not new and not os.path.exists(path):
            raise LookupError(f"No target list called {slug}")
        write_json(path, clean)
        Target.load(path)  # Prove the command line can read it.
        return slug

    # Results --------------------------------------------------------------

    def result_file(self, slug):
        """The newest finished spreadsheet, or the work in progress if none."""
        check_slug(slug)
        done = sorted(glob.glob(os.path.join(self.root, "out", f"{slug}-*.csv")))
        done = [p for p in done if re.fullmatch(re.escape(slug) + r"-\d{4}-\d\d-\d\d\.csv",
                                               os.path.basename(p))]
        if done:
            return done[-1]
        working = os.path.join(self.root, "data", slug, "places.csv")
        return working if os.path.exists(working) else None

    def rows(self, slug):
        path = self.result_file(slug)
        if not path:
            return None, []
        mtime = os.path.getmtime(path)
        cached = self._results.get(path)
        if not cached or cached[0] != mtime:
            cached = (mtime, places.read(path), columns(path))
            self._results[path] = cached
        return path, cached[1]

    def columns(self, slug):
        """The spreadsheet's own columns, so new ones show up without changes here."""
        path, _ = self.rows(slug)
        return self._results[path][2] if path else list(places.FIELDS)

    def summary(self, slug, rows=None):
        path, everything = self.rows(slug)
        rows = everything if rows is None else rows
        count = lambda test: sum(1 for r in rows if test(r))
        sectors = {}
        for row in rows:
            sector = sectors.setdefault(row["sector"] or "Other",
                                        {"total": 0, "can_email": 0, "ready": 0})
            sector["total"] += 1
            sector["can_email"] += row["contact_rule"] == "can email"
            sector["ready"] += ready(row)
        return {
            "file": os.path.relpath(path, self.root) if path else None,
            "updated": time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(path)))
            if path else None,
            "total": len(rows),
            "can_email": count(lambda r: r["contact_rule"] == "can email"),
            "post_only": count(lambda r: r["contact_rule"] == "post only"),
            "check": count(lambda r: r["contact_rule"] == "check local rules"),
            "with_email": count(lambda r: r["email"] or r["all_emails"]),
            "ready": count(ready),
            "with_person": count(lambda r: r["contact_name"]),
            "with_phone": count(lambda r: r["phone"] or r["all_phones"]),
            "mobile_only": count(lambda r: r["mobile_only"] == "yes"),
            "with_socials": count(lambda r: r["socials"]),
            "sectors": sectors,
        }

    def search(self, slug, query):
        """Filter, sort and page the results. query is a dict of lists (parse_qs)."""
        path, rows = self.rows(slug)
        chosen = filter_rows(rows, query)
        sort = one(query, "sort", "")
        if sort.lstrip("-") in self.columns(slug):
            key = sort.lstrip("-")
            numeric = key.endswith("confidence") or key in ("lat", "lon")
            chosen = sorted(chosen, reverse=sort.startswith("-"),
                            key=lambda r: (number(r.get(key)) if numeric else (r.get(key) or "").lower()))
        page = max(int(one(query, "page", "1") or 1), 1)
        size = min(max(int(one(query, "size", "50") or 50), 1), PAGE_MAX)
        return {"total": len(chosen), "page": page, "size": size,
                "rows": chosen[(page - 1) * size: page * size],
                "summary": self.summary(slug), "filtered": self.summary(slug, chosen)}

    def export(self, slug, query):
        _, rows = self.rows(slug)
        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=self.columns(slug), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(filter_rows(rows, query))
        return "﻿" + out.getvalue()  # Excel reads accents and £ with the marker.

    # What's set up on this computer ----------------------------------------

    def setup(self):
        zips = sorted(glob.glob(os.path.join(self.root, "data", "BasicCompanyData*.zip"))
                      + glob.glob(os.path.join(self.root, "data", "BasicCompanyData*.csv")))
        return {
            "duckdb": importlib.util.find_spec("duckdb") is not None,
            "companies_house_key": bool(os.environ.get("RECON_COMPANIES_HOUSE_KEY")),
            "hunter_key": bool(os.environ.get("RECON_HUNTER_KEY")),
            "companies_house_files": [os.path.relpath(p, self.root) for p in zips],
            "countries": [{"code": c, "name": COUNTRIES.get(c, c)} for c in COUNTRY_BOX],
            "ready_score": finder.READY,
        }


def columns(path):
    with open(path, newline="", encoding="utf-8-sig") as handle:
        header = next(csv.reader(handle), [])
    return header + [f for f in places.FIELDS if f not in header]


def ready(row):
    score = number(row["email_confidence"])
    return bool(row["email"] and row["contact_rule"] == "can email" and score >= finder.READY)


def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return -1.0


def one(query, key, default=""):
    values = query.get(key) or [default]
    return values[0]


def filter_rows(rows, query):
    words = one(query, "q").lower().split()
    sector = one(query, "sector")
    rule = one(query, "rule")
    town = one(query, "town").lower()
    has = set(query.get("has", []))
    email_type = one(query, "email_type")
    chosen = []
    for row in rows:
        if sector and row["sector"] != sector:
            continue
        if rule and row["contact_rule"] != rule:
            continue
        if town and town not in row["town"].lower():
            continue
        if email_type and email_type not in row["email_type"] + " " + row["all_emails"]:
            continue
        if "email" in has and not (row["email"] or row["all_emails"]):
            continue
        if "ready" in has and not ready(row):
            continue
        if "phone" in has and not (row["phone"] or row["all_phones"]):
            continue
        if "mobile" in has and not row["mobile"]:
            continue
        if "socials" in has and not row["socials"]:
            continue
        if "person" in has and not row["contact_name"]:
            continue
        if "website" in has and not row["website"]:
            continue
        if "company" in has and not row["company_number"]:
            continue
        if words:
            haystack = " ".join(row.get(f) or "" for f in (
                "name", "town", "postcode", "address", "email", "all_emails", "website",
                "company_name", "legal_name", "other_names", "contact_name", "category")).lower()
            if not all(w in haystack for w in words):
                continue
        chosen.append(row)
    return chosen


def check_slug(slug):
    if not SLUG.match(slug or ""):
        raise ValueError("Names may only use small letters, numbers and dashes")


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp = path + ".part"
    with open(temp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    os.replace(temp, path)


def clean_target(data):
    """Check a target list from the site. Keys the site doesn't know (such as
    ones a newer Recon adds) are kept as they are, so saving never loses them."""
    name = str(data.get("name", "")).strip()
    if not name:
        raise ValueError("A target list needs a name")
    country = str(data.get("country", "")).strip().upper()
    box = data.get("box")
    if country not in COUNTRY_BOX and not box:
        raise ValueError(f"Recon doesn't know the map area for {country or 'that country'} yet")
    sectors = {}
    for sector_name, sector in (data.get("sectors") or {}).items():
        sector_name = str(sector_name).strip()
        if not sector_name:
            continue
        words = lambda key: list(dict.fromkeys(
            str(v).strip() for v in sector.get(key, []) if str(v).strip()))
        osm = []
        for pair in sector.get("osm", []):
            if isinstance(pair, str):
                pair = pair.split("=", 1)
            if len(pair) == 2 and all(str(p).strip() for p in pair):
                tag = [str(pair[0]).strip(), str(pair[1]).strip()]
                if tag not in osm:
                    osm.append(tag)
        sectors[sector_name] = {"overture": words("overture"), "osm": osm, "sic": words("sic"),
                                **extras(sector, ("overture", "osm", "sic"))}
    if not sectors:
        raise ValueError("Add at least one kind of business")
    clean = {"name": name, "project": str(data.get("project", "")).strip(), "country": country,
             "notes": str(data.get("notes", "")).strip(), "sectors": sectors,
             **extras(data, ("name", "project", "country", "notes", "sectors", "box"))}
    if box:
        if len(box) != 4:
            raise ValueError("A map box needs four numbers: west, south, east, north")
        clean["box"] = [float(b) for b in box]
    return clean


def extras(data, known):
    return {key: value for key, value in data.items() if key not in known}


class Runs:
    """Command-line runs started from the site, each logged to a file."""

    def __init__(self, workspace):
        self.workspace = workspace
        self.lock = threading.Lock()
        self.all = {}

    def start(self, slug, step="run", options=None):
        options = options or {}
        check_slug(slug)
        if step not in STEPS:
            raise ValueError(f"Unknown step {step}")
        if self.active(slug):
            raise ValueError("That target list is already running")
        target_file = os.path.join("targets", slug + ".json")
        if not os.path.exists(os.path.join(self.workspace.root, target_file)):
            raise LookupError(f"No target list called {slug}")
        command = [sys.executable, "-u", "-m", "recon", step, target_file]
        for flag in ("skip_osm", "skip_overture", "can_email_only", "hunter"):
            if options.get(flag):
                command.append("--" + flag.replace("_", "-"))
        if options.get("overture_release"):
            command += ["--overture-release", str(options["overture_release"])]
        if options.get("smtp_from"):
            command += ["--smtp-from", str(options["smtp_from"])]
        files = [f for f in options.get("companies_house", []) if f]
        for name in files:
            full = os.path.abspath(os.path.join(self.workspace.root, name))
            if not full.startswith(self.workspace.root + os.sep) or not os.path.exists(full):
                raise ValueError(f"Can't find the Companies House file {name}")
        if files:
            command += ["--companies-house", *files]
        run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + slug
        log = os.path.join(self.workspace.root, "data", slug, "runs", run_id + ".log")
        os.makedirs(os.path.dirname(log), exist_ok=True)
        handle = open(log, "w", encoding="utf-8")
        process = subprocess.Popen(command, cwd=self.workspace.root, stdout=handle,
                                   stderr=subprocess.STDOUT, env={**os.environ,
                                                                  "PYTHONUNBUFFERED": "1"})
        run = {"id": run_id, "target": slug, "step": step, "started": time.time(),
               "finished": None, "status": "running", "log": log, "process": process,
               "handle": handle}
        with self.lock:
            self.all[run_id] = run
        threading.Thread(target=self._wait, args=(run,), daemon=True).start()
        return self.view(run)

    def _wait(self, run):
        code = run["process"].wait()
        run["handle"].close()
        run["finished"] = time.time()
        run["status"] = ("finished" if code == 0 else
                         "stopped" if run.get("stopping") else "failed")

    def stop(self, run_id):
        run = self.all.get(run_id)
        if not run:
            raise LookupError("No such run")
        if run["status"] == "running":
            run["stopping"] = True
            run["process"].terminate()
        return self.view(run)

    def active(self, slug):
        return any(r["target"] == slug and r["status"] == "running" for r in self.all.values())

    def view(self, run, log=False):
        shown = {k: run[k] for k in ("id", "target", "step", "started", "finished", "status")}
        if log:
            try:
                with open(run["log"], encoding="utf-8", errors="replace") as handle:
                    shown["log"] = handle.read()[-20000:]
            except OSError:
                shown["log"] = ""
        return shown

    def list(self):
        return sorted((self.view(r) for r in self.all.values()),
                      key=lambda r: r["started"], reverse=True)

    def get(self, run_id):
        run = self.all.get(run_id)
        if not run:
            raise LookupError("No such run")
        return self.view(run, log=True)


def handler_for(workspace, site):
    class Handler(BaseHTTPRequestHandler):
        server_version = "Recon"

        def log_message(self, *args):
            pass

        def _send(self, status, body, kind="application/json", headers=None):
            data = body if isinstance(body, bytes) else body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(data)

        def _json(self, data, status=200):
            self._send(status, json.dumps(data, ensure_ascii=False))

        def _body(self):
            length = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(length) or b"{}") if length else {}

        def _route(self, method):
            url = urllib.parse.urlparse(self.path)
            parts = [urllib.parse.unquote(p) for p in url.path.strip("/").split("/") if p]
            query = urllib.parse.parse_qs(url.query)
            if not parts or parts[0] != "api":
                if method != "GET":
                    return self._json({"error": "Not found"}, 404)
                return self._static(url.path)
            # Only accept requests the site itself makes, so another web page
            # open in the same browser can't start runs or change lists.
            if method != "GET" and self.headers.get("X-Recon") != "1":
                return self._json({"error": "Missing X-Recon header"}, 403)
            try:
                return self._api(method, parts[1:], query)
            except LookupError as error:
                return self._json({"error": str(error).strip("'\"")}, 404)
            except (ValueError, KeyError, TypeError, SystemExit) as error:
                return self._json({"error": str(error).strip("'\"")}, 400)

        def _api(self, method, parts, query):
            route = (method, *parts)
            if route == ("GET", "setup"):
                return self._json(workspace.setup())
            if route == ("GET", "projects"):
                return self._json(workspace.projects())
            if route == ("POST", "projects"):
                body = self._body()
                slug = slugify(str(body.get("name", "")))
                if os.path.exists(workspace._project_file(slug)):
                    raise ValueError("There is already a project with that name")
                return self._json({"slug": workspace.save_project(body)}, 201)
            if method == "PUT" and len(parts) == 2 and parts[0] == "projects":
                check_slug(parts[1])
                return self._json({"slug": workspace.save_project(self._body(), parts[1])})
            if route == ("POST", "targets"):
                return self._json({"slug": workspace.save_target(self._body())}, 201)
            if len(parts) >= 2 and parts[0] == "targets":
                slug = parts[1]
                check_slug(slug)
                rest = tuple(parts[2:])
                if method == "GET" and not rest:
                    return self._json(workspace.target(slug))
                if method == "PUT" and not rest:
                    return self._json({"slug": workspace.save_target(self._body(), slug)})
                if method == "GET" and rest == ("results",):
                    return self._json(workspace.search(slug, query))
                if method == "GET" and rest == ("export",):
                    name = f"{slug}-{time.strftime('%Y-%m-%d')}.csv"
                    return self._send(200, workspace.export(slug, query), "text/csv; charset=utf-8",
                                      {"Content-Disposition": f'attachment; filename="{name}"'})
            if route == ("GET", "master"):
                return self._json(workspace.directory.status())
            if route == ("GET", "master", "search"):
                return self._json(workspace.directory.search(query))
            if route == ("GET", "master", "kinds"):
                return self._json(workspace.directory.kinds(one(query, "group", "uk")))
            if route == ("GET", "master", "export"):
                return self._file(workspace.directory.export(query))
            if route == ("GET", "runs"):
                return self._json(workspace.runs.list())
            if route == ("POST", "runs"):
                body = self._body()
                return self._json(workspace.runs.start(body.get("target", ""),
                                                       body.get("step", "run"),
                                                       body.get("options")), 201)
            if method == "GET" and len(parts) == 2 and parts[0] == "runs":
                return self._json(workspace.runs.get(parts[1]))
            if method == "POST" and len(parts) == 3 and parts[0] == "runs" and parts[2] == "stop":
                return self._json(workspace.runs.stop(parts[1]))
            if route == ("POST", "categories"):
                body = self._body()
                return self._json(find_categories(body.get("country", "GB"), body.get("words", []),
                                                  body.get("release")))
            return self._json({"error": "Not found"}, 404)

        def _file(self, path):
            """Send a CSV made for this request, then delete it."""
            name = f"recon-businesses-{time.strftime('%Y-%m-%d')}.csv"
            try:
                size = os.path.getsize(path)
                self.send_response(200)
                self.send_header("Content-Type", "text/csv; charset=utf-8")
                self.send_header("Content-Length", str(size + 3))
                self.send_header("Content-Disposition", f'attachment; filename="{name}"')
                self.end_headers()
                self.wfile.write("\ufeff".encode("utf-8"))  # So Excel reads accents and £.
                with open(path, "rb") as handle:
                    while chunk := handle.read(1 << 20):
                        self.wfile.write(chunk)
            finally:
                os.remove(path)

        def _static(self, path):
            if not site or not os.path.isdir(site):
                return self._send(200, NOT_BUILT, "text/html; charset=utf-8")
            full = os.path.abspath(os.path.join(site, path.lstrip("/")))
            if not full.startswith(os.path.abspath(site)) or not os.path.isfile(full):
                full = os.path.join(site, "index.html")  # The site handles its own pages.
            kind = mimetypes.guess_type(full)[0] or "application/octet-stream"
            with open(full, "rb") as handle:
                self._send(200, handle.read(), kind)

        def do_GET(self):
            self._route("GET")

        def do_POST(self):
            self._route("POST")

        def do_PUT(self):
            self._route("PUT")

    return Handler


def find_categories(country, words, release=None):
    """Overture's exact category names containing any of the words, with counts."""
    from . import overture  # Needs DuckDB and the internet; only loaded when asked.
    words = [w.strip() for w in words if w.strip()]
    if not words:
        raise ValueError("Type a word or two, such as dentist or yoga")
    country = str(country).upper()
    if country not in COUNTRY_BOX:
        raise ValueError(f"Recon doesn't know the map area for {country} yet")
    target = Target(name="search", country=country, sectors={}, box=COUNTRY_BOX[country])
    try:
        found = overture.categories(target, words, release)
    except ImportError:
        raise ValueError("Searching Overture needs DuckDB: python3 -m pip install duckdb")
    return [{"category": c, "places": n} for c, n in found]


NOT_BUILT = """<!doctype html><meta charset="utf-8"><title>Recon</title>
<body style="font-family:system-ui;padding:3rem;max-width:40rem">
<h1>Recon</h1><p>The website hasn't been built yet. In the <code>web</code> folder run
<code>npm install</code> then <code>npm run build</code>, and refresh this page.</p>"""


def main(argv=None):
    parser = argparse.ArgumentParser(prog="recon.server", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1",
                        help="defaults to this computer only; the results are private")
    parser.add_argument("--root", default=".", help="the Recon folder (default: here)")
    parser.add_argument("--master", help="the master database folder (from recon.master); "
                                         "found by itself in data/master-db or RECON_MASTER")
    args = parser.parse_args(argv)
    workspace = Workspace(args.root, args.master)
    site = os.path.join(workspace.root, "web", "dist")
    server = ThreadingHTTPServer((args.host, args.port), handler_for(workspace, site))
    print(f"Recon is open at http://{'localhost' if args.host == '127.0.0.1' else args.host}:"
          f"{args.port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
