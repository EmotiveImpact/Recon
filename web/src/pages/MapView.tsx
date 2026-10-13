import { useEffect, useMemo, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { Building2, Download, Globe, Mail, MapPin, Phone, PoundSterling, Search, Smartphone, X } from "lucide-react";
import { api, type MapResults, type Place } from "../api";
import { fmt, pct, RuleBadge } from "../ui";

// Businesses near a postcode or town, as pins on a map with the list beside it.
// The pins come from the trade lists, which have a map position for every row.

const RADII = [1, 2, 5, 10, 25, 50];
const FILTERS: [string, string, typeof Mail][] = [
  ["email", "Has an email", Mail],
  ["mobile", "Has a mobile", Smartphone],
  ["website", "Has a website", Globe],
  ["company", "Registered company", Building2],
  ["money", "Publishes turnover", PoundSterling],
];
const SIZES: [string, string][] = [["", "Any size"], ["micro", "Micro"], ["small", "Small"], ["medium-large", "Medium or large"]];
const WORTH: [string, string][] = [["", "Any worth"], ["10000", "£10k+"], ["100000", "£100k+"], ["1000000", "£1m+"]];
const GREEN = "#34d399";
const AMBER = "#fbbf24";

const pinColour = (p: Place) => (p.contact_rule === "can email" ? GREEN : AMBER);
const tradeName = (t: string) => (t.charAt(0).toUpperCase() + t.slice(1)).replaceAll("-", " ");
const money = (v: string) => {
  const n = Number(v);
  if (!v || Number.isNaN(n)) return v;
  return n >= 1e6 ? `£${(n / 1e6).toFixed(1)}m` : n >= 1e3 ? `£${Math.round(n / 1e3)}k` : `£${fmt(n)}`;
};

function popupHtml(p: Place) {
  const esc = (s: string) => s.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
  const site = p.website ? `<a href="${esc(p.website.startsWith("http") ? p.website : "https://" + p.website)}" target="_blank" rel="noreferrer">${esc(p.website.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, ""))}</a>` : "";
  const lines = [
    p.email && `<div>✉️ ${esc(p.email)}</div>`,
    (p.phone || p.mobile) && `<div>📞 ${esc(p.phone || p.mobile)}</div>`,
    site && `<div>🌐 ${site}</div>`,
    p.turnover && `<div>💷 Turnover ${esc(money(p.turnover))}</div>`,
    p.net_assets && `<div>🏦 Net worth ${esc(money(p.net_assets))}${p.staff ? `, ${esc(p.staff)} staff` : ""}</div>`,
  ].filter(Boolean).join("");
  const rule = p.contact_rule === "can email"
    ? `<span class="pop-badge can">✓ Can email</span>` : `<span class="pop-badge post">✉ Post only</span>`;
  return `<div class="pop"><b>${esc(p.name)}</b><div class="pop-sub">${esc(tradeName(p.trade))} · ${esc([p.town, p.postcode].filter(Boolean).join(" "))}</div>${rule}${lines}</div>`;
}

export default function MapView({ initial }: { initial: URLSearchParams }) {
  const start = initial.get("near") ?? (initial.getAll("trade").length ? "" : "BN1");
  const [typed, setTyped] = useState(start);
  const [near, setNear] = useState(start);
  const [km, setKm] = useState(Number(initial.get("km")) || 5);
  const [trades, setTrades] = useState<string[]>(initial.getAll("trade"));
  const [rule, setRule] = useState("");
  const [has, setHas] = useState<string[]>([]);
  const [size, setSize] = useState(initial.get("size") || "");
  const [worth, setWorth] = useState(initial.get("worth") || "");
  const [data, setData] = useState<MapResults | null>(null);
  const [allTrades, setAllTrades] = useState<{ trade: string; name: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [picked, setPicked] = useState<Place | null>(null);
  const mapBox = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const layer = useRef<L.LayerGroup | null>(null);
  const markers = useRef<Map<Place, L.CircleMarker>>(new Map());

  const query = useMemo(() => {
    const p = new URLSearchParams({ km: String(km) });
    if (near.trim()) p.set("near", near.trim());
    trades.forEach((t) => p.append("trade", t));
    if (rule) p.set("rule", rule);
    has.forEach((h) => p.append("has", h));
    if (size) p.set("size", size);
    if (worth) p.set("worth", worth);
    return p;
  }, [near, km, trades, rule, has, size, worth]);

  useEffect(() => {
    if (!mapBox.current || map.current) return;
    const m = L.map(mapBox.current, { preferCanvas: true, zoomControl: false }).setView([54.5, -2.5], 6);
    L.control.zoom({ position: "bottomright" }).addTo(m);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(m);
    layer.current = L.layerGroup().addTo(m);
    map.current = m;
    return () => { m.remove(); map.current = null; };
  }, []);

  useEffect(() => {
    setBusy(true);
    window.history.replaceState(null, "", `#/map?${query}`);
    api.map(query).then(
      (d) => {
        setData(d);
        if (d.trades?.length) setAllTrades(d.trades);
        setError("");
        setBusy(false);
      },
      (e) => { setError(e.message); setBusy(false); },
    );
  }, [query]);

  // Draw the pins and the circle whenever the results change.
  useEffect(() => {
    const m = map.current;
    const group = layer.current;
    if (!m || !group || !data?.available) return;
    group.clearLayers();
    markers.current.clear();
    if (data.centre) {
      L.circle([data.centre.lat, data.centre.lon], {
        radius: data.km * 1000, color: "#7c5cff", weight: 1.5, fillColor: "#7c5cff", fillOpacity: 0.06,
      }).addTo(group);
    }
    for (const p of data.points) {
      const marker = L.circleMarker([p.lat, p.lon], {
        radius: 6, color: "#0b0d14", weight: 1.5, fillColor: pinColour(p), fillOpacity: 0.95,
      }).bindPopup(popupHtml(p), { closeButton: false, maxWidth: 280 });
      marker.on("click", () => setPicked(p));
      marker.addTo(group);
      markers.current.set(p, marker);
    }
    if (data.centre) {
      m.fitBounds(L.latLng(data.centre.lat, data.centre.lon).toBounds(data.km * 2000), { padding: [20, 20] });
    } else if (data.points.length) {
      m.fitBounds(L.latLngBounds(data.points.map((p) => [p.lat, p.lon] as [number, number])), { padding: [30, 30] });
    }
  }, [data]);

  const show = (p: Place) => {
    setPicked(p);
    const marker = markers.current.get(p);
    if (map.current && marker) {
      map.current.setView([p.lat, p.lon], Math.max(map.current.getZoom(), 15));
      marker.openPopup();
    }
  };
  const toggle = (list: string[], set: (v: string[]) => void, v: string) =>
    set(list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);

  return (
    <div className="mapview">
      <aside className="map-side">
        <form className="map-search" onSubmit={(e) => { e.preventDefault(); setNear(typed); }}>
          <div className="search">
            <MapPin size={16} />
            <input className="input" value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="Postcode or town, for example BN1 or Leeds" />
          </div>
          <button className="btn primary" type="submit"><Search size={15} /></button>
        </form>
        <div className="row" style={{ gap: 6 }}>
          <span className="small muted">Within</span>
          <div className="seg small">
            {RADII.map((r) => (
              <button key={r} className={km === r ? "on" : ""} onClick={() => setKm(r)}>{r} km</button>
            ))}
          </div>
        </div>
        <select className="input select" value={trades[0] ?? ""} onChange={(e) => setTrades(e.target.value ? [e.target.value] : [])}>
          <option value="">Every trade</option>
          {allTrades.map((t) => <option key={t.trade} value={t.trade}>{tradeName(t.trade)}</option>)}
        </select>
        <div className="chips">
          {[["", "Everyone"], ["can email", "Can email"], ["post only", "Post only"]].map(([v, label]) => (
            <button key={label} className={`chip ${rule === v ? "on" : ""}`} onClick={() => setRule(v)}>{label}</button>
          ))}
          {FILTERS.map(([v, label, Icon]) => (
            <button key={v} className={`chip ${has.includes(v) ? "on" : ""}`} onClick={() => toggle(has, setHas, v)}>
              <Icon size={13} /> {label}
            </button>
          ))}
        </div>

        <div className="row" style={{ gap: 6 }}>
          <div className="seg small">
            {SIZES.map(([v, label]) => <button key={label} className={size === v ? "on" : ""} onClick={() => setSize(v)}>{label}</button>)}
          </div>
          <div className="seg small">
            {WORTH.map(([v, label]) => <button key={label} className={worth === v ? "on" : ""} onClick={() => setWorth(v)}>{label}</button>)}
          </div>
        </div>
        {error && <div className="notice bad">{error}</div>}

        {data?.available && (
          <>
            <div className="map-stats" style={{ opacity: busy ? 0.5 : 1 }}>
              <div><b>{fmt(data.total)}</b><span>businesses{data.centre ? ` within ${data.km} km of ${data.centre.label}` : ""}</span></div>
              <div className="green"><b>{fmt(data.may_email)}</b><span>can email</span></div>
              <div className="blue"><b>{fmt(data.with_email)}</b><span>have an email</span></div>
              <div className="pink"><b>{fmt(data.with_mobile)}</b><span>have a mobile</span></div>
            </div>
            {data.money.available && (
              <div className="small muted">
                <PoundSterling size={13} style={{ verticalAlign: -2 }} /> {fmt(data.money.registered)} registered companies ({pct(data.money.registered ?? 0, data.money.total ?? 0)}),{" "}
                {fmt(data.money.with_net_assets)} show their net worth, {fmt(data.money.publishes_turnover)} their turnover.
              </div>
            )}
            <div className="spread">
              <span className="small faint">
                {data.shown < data.total ? `${data.centre ? "Nearest" : "First"} ${fmt(data.shown)} shown. ` : ""}
                <span className="legend-dot" style={{ background: GREEN }} /> can email
                <span className="legend-dot" style={{ background: AMBER, marginLeft: 10 }} /> post only
              </span>
              <a className="btn small" href={api.mapExportUrl(query)}><Download size={14} /> Download</a>
            </div>
            <div className="map-list">
              {data.points.map((p, i) => (
                <button key={`${p.name}-${i}`} className={`map-item ${picked === p ? "on" : ""}`} onClick={() => show(p)}>
                  <span className="pin" style={{ background: pinColour(p) }} />
                  <span className="map-item-body">
                    <b>{p.name}</b>
                    <span className="cell-sub">
                      {tradeName(p.trade)}{p.postcode ? ` · ${p.postcode}` : ""}{p.km !== undefined ? ` · ${p.km} km` : ""}
                    </span>
                    <span className="map-item-icons">
                      {p.email && <Mail size={13} />}
                      {(p.phone || p.mobile) && <Phone size={13} />}
                      {p.website && <Globe size={13} />}
                      {p.turnover ? <span className="badge green-soft">turnover {money(p.turnover)}</span>
                        : p.net_assets ? <span className="badge grey" style={{ padding: "0 7px", fontSize: 11 }}>worth {money(p.net_assets)}</span> : null}
                      {p.size_band && /^(micro|small|medium|large)/.test(p.size_band) && <span className="faint small">{p.size_band}</span>}
                    </span>
                  </span>
                </button>
              ))}
              {!data.points.length && <div className="empty">Nothing here. Try a wider circle or fewer filters.</div>}
            </div>
          </>
        )}
        {data && !data.available && <div className="notice warn">The trade lists aren't on this computer yet, so there's nothing to map.</div>}
      </aside>
      <div className="map-wrap">
        <div ref={mapBox} className="map" />
        {busy && <div className="map-busy">Looking…</div>}
        {picked && (
          <div className="map-card">
            <div className="spread" style={{ alignItems: "flex-start" }}>
              <div>
                <b>{picked.name}</b>
                <div className="cell-sub">{[picked.address, picked.town, picked.postcode].filter(Boolean).join(", ")}</div>
              </div>
              <button className="btn ghost small" onClick={() => setPicked(null)} aria-label="Close"><X size={14} /></button>
            </div>
            <RuleBadge rule={picked.contact_rule} />
            <dl className="kv">
              {picked.email && (<><dt>Email</dt><dd>{picked.email} <span className="faint small">{picked.email_type}</span></dd></>)}
              {picked.phone && (<><dt>Phone</dt><dd>{picked.phone}</dd></>)}
              {picked.mobile && picked.mobile !== picked.phone && (<><dt>Mobile</dt><dd>{picked.mobile}</dd></>)}
              {picked.website && (<><dt>Website</dt><dd><a href={picked.website} target="_blank" rel="noreferrer" style={{ color: "var(--accent-2)" }}>{picked.website.replace(/^https?:\/\/(www\.)?/, "")}</a></dd></>)}
              {picked.company_number && (<><dt>Company</dt><dd>{picked.company_number} {picked.company_type && <span className="faint small">{picked.company_type}</span>}</dd></>)}
              {picked.size_band && (<><dt>Size</dt><dd>{picked.size_band}{picked.staff ? `, ${picked.staff} staff` : ""}</dd></>)}
              {picked.turnover && (<><dt>Turnover</dt><dd>{money(picked.turnover)}{picked.accounts_to ? ` (accounts to ${picked.accounts_to})` : ""}</dd></>)}
              {picked.net_assets && (<><dt>Net assets</dt><dd>{money(picked.net_assets)}</dd></>)}
            </dl>
          </div>
        )}
      </div>
    </div>
  );
}
