import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { MasterResults, Row } from "../api";
import { splitList } from "../ui";

// Free OpenStreetMap tiles. Their rules ask for the credit line and light use,
// which one person browsing a list is.
const TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const CREDIT = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors. Postcodes: <a href="https://www.geonames.org">GeoNames</a>';
const GREEN = "#34d399";
const AMBER = "#fbbf24";
const START: Record<string, [number, number, number]> = { uk: [54.6, -3.2, 5], us: [39.5, -98.5, 4] };

// Organisations are placed at their postcode's centre, so several can share a
// spot. Each spot gets one pin listing everyone there.
function spots(points: Row[]) {
  const found = new Map<string, Row[]>();
  for (const p of points) {
    const key = `${p.lat},${p.lon}`;
    found.set(key, [...(found.get(key) ?? []), p]);
  }
  return [...found.values()];
}

function el(tag: string, className = "", text = "") {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

// Built from elements rather than HTML text, so a name can't inject anything.
function popup(rows: Row[], onOpen: (row: Row) => void) {
  const box = el("div", "pin-popup");
  if (rows.length > 1) box.append(el("div", "pin-count", `${rows.length} at this postcode`));
  for (const row of rows.slice(0, 8)) {
    const item = el("div", "pin-item");
    item.append(el("div", "pin-name", row.name));
    const can = row.can_email === "can email";
    item.append(el("span", `pin-rule ${can ? "good" : "warn"}`, can ? "Can email" : "Post only"));
    const email = splitList(row.emails)[0];
    const phone = splitList(row.phones)[0];
    const site = splitList(row.website)[0];
    if (email) item.append(el("div", "pin-line", `✉ ${email}`));
    if (phone) item.append(el("div", "pin-line", `☎ ${phone}`));
    if (site) {
      const link = el("a", "pin-line", site.replace(/^https?:\/\/(www\.)?/, "")) as HTMLAnchorElement;
      link.href = site.startsWith("http") ? site : `https://${site}`;
      link.target = "_blank";
      link.rel = "noreferrer";
      item.append(link);
    }
    if (!email && !phone && !site) item.append(el("div", "pin-line faint", [row.address, row.postcode].filter(Boolean).join(", ")));
    const more = el("button", "pin-more", "More details");
    more.addEventListener("click", () => onOpen(row));
    item.append(more);
    box.append(item);
  }
  if (rows.length > 8) box.append(el("div", "pin-count", `and ${rows.length - 8} more in the list`));
  return box;
}

export default function ResultsMap({ data, group, onOpen }: { data: MasterResults; group: string; onOpen: (row: Row) => void }) {
  const box = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const pins = useRef<L.LayerGroup | null>(null);
  const open = useRef(onOpen);
  open.current = onOpen;

  useEffect(() => {
    if (!box.current) return;
    const m = L.map(box.current, { preferCanvas: true, scrollWheelZoom: false, worldCopyJump: true });
    L.tileLayer(TILES, { maxZoom: 19, attribution: CREDIT }).addTo(m);
    pins.current = L.layerGroup().addTo(m);
    map.current = m;
    return () => { m.remove(); map.current = null; };
  }, []);

  useEffect(() => {
    const m = map.current;
    const layer = pins.current;
    if (!m || !layer) return;
    layer.clearLayers();
    const bounds = L.latLngBounds([]);
    const { circle, points } = data;
    if (circle) {
      const ring = L.circle([circle.lat, circle.lon], {
        radius: circle.miles * 1609.34, color: "#7c5cff", weight: 2, fillColor: "#7c5cff", fillOpacity: 0.06, interactive: false,
      }).addTo(layer);
      L.circleMarker([circle.lat, circle.lon], { radius: 4, color: "#7c5cff", fillOpacity: 1, interactive: false }).addTo(layer);
      bounds.extend(ring.getBounds());
    }
    for (const rows of spots(points)) {
      const where = L.latLng(Number(rows[0].lat), Number(rows[0].lon));
      const can = rows.some((r) => r.can_email === "can email");
      L.circleMarker(where, {
        radius: Math.min(5 + rows.length, 12), color: "#0b0d14", weight: 1, fillColor: can ? GREEN : AMBER, fillOpacity: 0.9,
      })
        .bindPopup(() => popup(rows, (row) => open.current(row)), { maxWidth: 300 })
        .addTo(layer);
      if (!circle) bounds.extend(where);
    }
    if (bounds.isValid()) m.fitBounds(bounds, { padding: [24, 24], maxZoom: 15 });
    else {
      const [lat, lon, zoom] = START[group] ?? [20, 0, 2];
      m.setView([lat, lon], zoom);
    }
  }, [data, group]);

  return (
    <div className="map-wrap">
      <div ref={box} className="map" />
      <div className="map-key">
        <span><i style={{ background: GREEN }} /> Can email</span>
        <span><i style={{ background: AMBER }} /> Post only</span>
      </div>
    </div>
  );
}
