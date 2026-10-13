"""Where a UK postcode is, from GeoNames' free postcode file.

GeoNames publishes every UK postcode with its position (CC BY 4.0, built on
Royal Mail and Ordnance Survey open data): https://www.geonames.org. Recon uses
it to measure how far a company's registered office is from the business, so
a company registered with an accountant in the next town can still be matched
while one with the same name at the other end of the country is not.

The file is 15 MB; it is downloaded to data/geo/ and kept for three months.
"""

import collections
import io
import os
import zipfile

from . import osm, text

URL = "https://download.geonames.org/export/zip/GB_full.csv.zip"
KEEP_DAYS = 90


def postcode_file(folder=os.path.join("data", "geo")):
    """Path of the postcode file, downloading it when missing or old. None if it
    cannot be had, in which case distances are judged from the places found."""
    path = os.path.join(folder, os.path.basename(URL))
    if osm._fresh(path, KEEP_DAYS):
        return path
    os.makedirs(folder, exist_ok=True)
    try:
        print(f"  Downloading {URL}")
        osm._download(URL, path)
    except OSError as error:
        print(f"  Could not download the postcode file ({error}); distances will be rougher")
        return path if os.path.exists(path) else None
    return path


class Postcodes:
    """Positions of the postcodes asked for, and the middle of every district."""

    def __init__(self, path=None, wanted=()):
        self.points = {}
        self.middles = {}
        if not path:
            return
        wanted = set(wanted)
        sums = collections.defaultdict(lambda: [0.0, 0.0, 0])
        with zipfile.ZipFile(path) as archive:
            member = next(n for n in archive.namelist() if n.endswith(".txt"))
            with archive.open(member) as raw:
                for line in io.TextIOWrapper(raw, encoding="utf-8"):
                    fields = line.rstrip("\n").split("\t")
                    if len(fields) < 11:
                        continue
                    try:
                        where = float(fields[9]), float(fields[10])
                    except ValueError:
                        continue
                    code = text.postcode(fields[1])
                    if code in wanted:
                        self.points[code] = where
                    total = sums[text.postcode_district(code)]
                    total[0] += where[0]
                    total[1] += where[1]
                    total[2] += 1
        self.middles = {d: (lat / n, lon / n) for d, (lat, lon, n) in sums.items() if d}

    def find(self, postcode):
        """Position of a postcode, or of its district's middle, or None."""
        return self.points.get(postcode) or self.middles.get(text.postcode_district(postcode))
