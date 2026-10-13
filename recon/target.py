"""A target list: which kinds of business one project wants to reach, and where.

Each project gets its own JSON file in targets/. List broad sectors first:
for OpenStreetMap, when a place matches two sectors the later one wins.
"""

import json
from dataclasses import dataclass, field

# Rough boxes; each source's own country code then trims neighbours.
COUNTRY_BOX = {
    "GB": (-8.7, 49.8, 1.8, 60.9),
    "IE": (-10.7, 51.3, -5.9, 55.5),
    "US": (-125.0, 24.4, -66.9, 49.4),
}


@dataclass
class Target:
    name: str
    country: str
    sectors: dict
    project: str = ""
    notes: str = ""
    box: tuple = field(default=None)

    @classmethod
    def load(cls, path):
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        country = data["country"].upper()
        box = tuple(data["box"]) if data.get("box") else COUNTRY_BOX.get(country)
        if not box:
            raise SystemExit(f"No map box known for {country}; add \"box\": [west, south, east, north]")
        return cls(name=data["name"], country=country, sectors=data["sectors"],
                   project=data.get("project", ""), notes=data.get("notes", ""), box=box)

    def overture_categories(self):
        return sorted({c for s in self.sectors.values() for c in s.get("overture", [])})

    def osm_tags(self):
        """Distinct (key, value) pairs to ask OpenStreetMap for."""
        seen = []
        for sector in self.sectors.values():
            for key, value in sector.get("osm", []):
                if (key, value) not in seen:
                    seen.append((key, value))
        return seen

    def sic_codes(self):
        return {code: name for name, s in self.sectors.items() for code in s.get("sic", [])}

    def overture_sector(self, primary, alternates=()):
        """Sector for an Overture place, judged on its primary category first."""
        for category in [primary, *(alternates or [])]:
            for name, sector in self.sectors.items():
                if category in sector.get("overture", []):
                    return name
        return None

    def osm_sector(self, tags):
        """Sector for an OpenStreetMap element. Later, narrower matches win,
        so a hairdresser tagged hairdresser=barber lands with barbers."""
        found = None
        for name, sector in self.sectors.items():
            if any(tags.get(key) == value for key, value in sector.get("osm", [])):
                found = name
        return found
