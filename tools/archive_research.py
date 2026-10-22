"""Acquire pinned research sources without importing or executing their code.

Run from a checkout: python3 tools/archive_research.py --software
Database downloads are kept under ignored data/research-acquisition, never git.
"""
import argparse
import concurrent.futures
import hashlib
import json
import pathlib
import shutil
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
PACK = ROOT / "research/recon-intelligence-2026-10-22"
PRIVATE = ROOT / "data/research-acquisition"

def get_json(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.load(response)

def download(url, target, expected_size=None):
    target = pathlib.Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and (expected_size is None or target.stat().st_size == expected_size):
        return receipt(target, url, "already_present")
    partial = target.with_name(target.name + ".part")
    offset = partial.stat().st_size if partial.exists() else 0
    headers = {"User-Agent": "Recon-Research-Archive/1.0"}
    if offset:
        headers["Range"] = "bytes=%d-" % offset
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=90) as response:
        resumed = offset and response.status == 206
        mode = "ab" if resumed else "wb"
        length = response.headers.get("Content-Length")
        if length and int(length) > shutil.disk_usage(target.parent).free - 1024**3:
            raise RuntimeError("Insufficient disk space; at least 1 GiB must remain free")
        with open(partial, mode) as handle:
            shutil.copyfileobj(response, handle, 1024 * 1024)
    if expected_size is not None and partial.stat().st_size != expected_size:
        raise RuntimeError("Incomplete download: expected %d bytes, received %d" % (expected_size, partial.stat().st_size))
    partial.replace(target)
    return receipt(target, url, "downloaded")

def receipt(path, url, status):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return {"path": str(path.relative_to(ROOT)), "source_url": url, "status": status,
            "bytes": path.stat().st_size, "sha256": digest.hexdigest()}

def task(job):
    try:
        result = download(job["url"], ROOT / job["path"], job.get("bytes"))
        result["id"] = job["id"]
    except Exception as exc:
        result = {"id": job["id"], "status": "failed", "reason": str(exc), "source_url": job["url"]}
    print(json.dumps(result), flush=True)
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--software", action="store_true")
    parser.add_argument("--databases", action="store_true")
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    jobs = []
    if args.software:
        catalogue = json.loads((PACK / "software-sources.json").read_text())
        for item in catalogue["repositories"]:
            name = item["repo"].replace("/", "__")
            base = "data/research-acquisition/software-private" if item["mode"] == "private_research_copy" else "research/vendor-archives"
            jobs.append({"id": name, "url": "https://github.com/%s/archive/%s.tar.gz" % (item["repo"], item["sha"]),
                         "path": "%s/%s-%s.tar.gz" % (base, name, item["sha"])})
    if args.databases:
        jobs.extend(json.loads((PACK / "database-downloads.json").read_text())["downloads"])
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(args.workers, 8))) as pool:
        results = list(pool.map(task, jobs))
    PRIVATE.mkdir(parents=True, exist_ok=True)
    (PRIVATE / ("receipts-%d.json" % time.time())).write_text(json.dumps(results, indent=2) + "\n")
    return 1 if any(r["status"] == "failed" for r in results) else 0

if __name__ == "__main__":
    raise SystemExit(main())

