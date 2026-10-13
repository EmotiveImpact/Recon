import { useEffect, useMemo, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { Building2, Download, Globe, Layers, Mail, MapPin, Phone, PoundSterling, Search, Smartphone, X } from "lucide-react";
import { api, type MapResults, type MasterResults, type Row } from "../api";
import { fmt, pct, RuleBadge, splitList } from "../ui";

// The one map: businesses near a postcode or town, as pins with the list beside them.
// Two kinds of list can be shown:
// - "trades": the UK trade lists, checked one by one, with an exact position for
//   every business plus company size, net worth and turnover.
// - "all": every open register in the master database, UK or US, any kind of
//   organisation, each placed at the middle of its postcode or ZIP code.

const RADII = [1, 2, 5, 10, 25, 50];
const TRADE_FILTERS: [string, string, typeof Mail][] = [
  ["email", "Has an email", Mail],
  ["mobile", "Has a mobile", Smartphone],
  ["website", "Has a website", Globe],
  ["company", "Registered company", Building2],
  ["money", "Publishes turnover", PoundSterling],
];
const ALL_FILTERS: [string, string, typeof Mail][] = [
  ["email", "Has an email", Mail],
  ["phone", "Has a phone", Phone],
  ["website", "Has a website", Globe],
];
const SIZES: [string, string][] = [["", "Any size"], ["micro", "Micro"], ["small", "Small"], ["medium-large", "Medium or large"]];
const WORTH: [string, string][] = [["", "Any worth"], ["10000", "£10k+"], ["100000", "£100k+"], ["1000000", "£1m+"]];
const GREEN = "#34d399";
const AMBER = "#fbbf24";

// One business on the map, whichever list it came from.
type Item = {
  name: string; what: string; address: string; town: string; postcode: string;
  lat: number; lon: number; miles: number | null; rule: string;
  email: string; emailType: string; phone: string; mobile: string; website: string;
  company: string; companyType: string; size: string; staff: string;
  turnover: string; netAssets: string; accountsTo: string; sources: string;
};

const tradeName = (t: string) => (t.charAt(0).toUpperCase() + t.slice(1)).replaceAll("-", " ");
const money = (v: string) => {
  const n = Number(v);
  if (!v || Number.isNaN(n)) return v;
  const sign = n < 0 ? "-" : "";
  const a = Math.abs(n);
  return `${sign}£${a >= 1e6 ? `${(a / 1e6).toFixed(1)}m` : a >= 1e3 ? `${Math.round(a / 1e3)}k` : fmt(a)}`;
};
const link = (site: string) => (/^https?:\/\//i.test(site) ? site : `https://${site}`);
const pinColour = (i: Item) => (i.rule === "can email" ? GREEN : AMBER);
const distance = (m: number | null) => (m === null ? "" : `${m < 10 ? m.toFixed(1) : Math.round(m)} mi`);

function fromTrade(p: MapResults["points"][number]): Item {
  return {
    name: p.name, what: tradeName(p.trade), address: p.address, town: p.town, postcode: p.postcode,
    lat: p.lat, lon: p.lon, miles: p.miles ?? null, rule: p.contact_rule,
    email: p.email, emailType: p.email_type, phone: p.phone, mobile: p.mobile, website: p.website,
    company: p.company_number, companyType: p.company_type, size: p.size_band, staff: p.staff,
    turnover: p.turnover, netAssets: p.net_assets, accountsTo: p.accounts_to, sources: "",
  };
}

function fromRegister(r: Row): Item {
  const phones = splitList(r.phones);
  return {
    name: r.name, what: r.kind, address: r.address, town: r.town, postcode: r.postcode,
    lat: Number(r.lat), lon: Number(r.lon), miles: r.miles === "" || r.miles === undefined ? null : Number(r.miles),
    rule: r.can_email, email: splitList(r.emails)[0] ?? "", emailType: "", phone: phones[0] ?? "", mobile: "",
    website: splitList(r.website)[0] ?? "", company: "", companyType: r.legal_form, size: "", staff: "",
    turnover: "", netAssets: "", accountsTo: "", sources: r.sources,
  };
}

// Built from elements rather than HTML text, so a name can't inject anything.
function popup(i: Item) {
  const el = (tag: string, cls = "", text = "") => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text) node.textContent = text;
    return node;
  };
  const box = el("div", "pop");
  box.append(el("b", "", i.name));
  box.append(el("div", "pop-sub", [i.what, [i.town, i.postcode].filter(Boolean).join(" ")].filter(Boolean).join(" · ")));
  const can = i.rule === "can email";
  box.append(el("span", `pop-badge ${can ? "can" : "post"}`, can ? "✓ Can email" : "✉ Post only"));
  if (i.email) box.append(el("div", "", `✉️ ${i.email}`));
  if (i.phone || i.mobile) box.append(el("div", "", `📞 ${i.phone || i.mobile}`));
  if (i.website) {
    const a = el("a", "", `🌐 ${i.website.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, "")}`) as HTMLAnchorElement;
    a.href = link(i.website);
    a.target = "_blank";
    a.rel = "noreferrer";
    box.append(el("div"), a);
  }
  if (i.turnover) box.append(el("div", "", `💷 Turnover ${money(i.turnover)}`));
  if (i.netAssets) box.append(el("div", "", `🏦 Net worth ${money(i.netAssets)}${i.staff ? `, ${i.staff} staff` : ""}`));
  return box;
}

export default function MapView({ initial }: { initial: URLSearchParams }) {
  const [source, setSource] = useState(initial.get("source") === "all" ? "all" : "trades");
  const start = initial.get("near") ?? (initial.getAll("trade").length || initial.get("size") || initial.get("q") ? "" : "BN1");
  const [typed, setTyped] = useState(start);
  const [near, setNear] = useState(start);
  const [radius, setRadius] = useState(Number(initial.get("miles")) || 5);
  const [trades, setTrades] = useState<string[]>(initial.getAll("trade"));
  const [group, setGroup] = useState(initial.get("group") === "us" ? "us" : "uk");
  const [qTyped, setQTyped] = useState(initial.get("q") ?? "");
  const [q, setQ] = useState(initial.get("q") ?? "");
  const [area, setArea] = useState(initial.get("area") ?? "");
  const [rule, setRule] = useState("");
  const [has, setHas] = useState<string[]>([]);
  const [size, setSize] = useState(initial.get("size") || "");
  const [worth, setWorth] = useState(initial.get("worth") || "");
  const [trade, setTrade] = useState<MapResults | null>(null);
  const [all, setAll] = useState<MasterResults | null>(null);
  const [allTrades, setAllTrades] = useState<{ trade: string; name: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [picked, setPicked] = useState<Item | null>(null);
  const mapBox = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const layer = useRef<L.LayerGroup | null>(null);
  const markers = useRef<Map<Item, L.CircleMarker>>(new Map());

  const query = useMemo(() => {
    const p = new URLSearchParams({ source, miles: String(radius) });
    if (near.trim()) p.set("near", near.trim());
    if (rule) p.set("rule", rule);
    has.forEach((h) => p.append("has", h));
    if (source === "trades") {
      trades.forEach((t) => p.append("trade", t));
      if (size) p.set("size", size);
      if (worth) p.set("worth", worth);
    } else {
      p.set("group", group);
      if (q.trim()) p.set("q", q.trim());
      if (area && !near.trim()) p.set("area", area);
    }
    return p;
  }, [source, near, radius, trades, rule, has, size, worth, group, q, area]);

  const needsMore = source === "all" && !near.trim() && !q.trim() && !area;

  useEffect(() => {
    if (!mapBox.current || map.current) return;
    const m = L.map(mapBox.current, { preferCanvas: true, zoomControl: false, worldCopyJump: true }).setView([54.5, -2.5], 6);
    L.control.zoom({ position: "bottomright" }).addTo(m);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors. Postcodes: <a href="https://www.geonames.org">GeoNames</a>',
    }).addTo(m);
    layer.current = L.layerGroup().addTo(m);
    map.current = m;
    return () => { m.remove(); map.current = null; };
  }, []);

  useEffect(() => {
    window.history.replaceState(null, "", `#/map?${query}`);
    setPicked(null);
    if (needsMore) { setAll(null); return; }
    setBusy(true);
    const done = () => { setError(""); setBusy(false); };
    const failed = (e: Error) => { setError(e.message); setBusy(false); };
    if (source === "trades") {
      api.map(query).then((d) => { setTrade(d); if (d.trades?.length) setAllTrades(d.trades); done(); }, failed);
    } else {
      api.masterSearch(query).then((d) => { setAll(d); done(); }, failed);
    }
  }, [query, needsMore]);

  // What's on show, in one shape whichever list it came from.
  const view = useMemo(() => {
    if (source === "trades" && trade?.available) {
      return {
        items: trade.points.map(fromTrade),
        centre: trade.centre ? { lat: trade.centre.lat, lon: trade.centre.lon, label: trade.centre.label } : null,
        total: trade.total, may: trade.may_email, email: trade.with_email, fourth: [trade.with_mobile, "have a mobile"] as [number, string],
        mapped: trade.total,
      };
    }
    if (source === "all" && all) {
      return {
        items: all.points.map(fromRegister).filter((i) => !Number.isNaN(i.lat)),
        centre: all.circle ? { lat: all.circle.lat, lon: all.circle.lon, label: all.circle.label } : null,
        total: all.total, may: all.may_email, email: all.with_email, fourth: [all.with_phone, "have a phone"] as [number, string],
        mapped: all.placed,
      };
    }
    return null;
  }, [source, trade, all]);

  // Draw the pins and the circle whenever the results change.
  useEffect(() => {
    const m = map.current;
    const group = layer.current;
    if (!m || !group) return;
    group.clearLayers();
    markers.current.clear();
    if (!view) return;
    if (view.centre) {
      L.circle([view.centre.lat, view.centre.lon], {
        radius: radius * 1609.34, color: "#7c5cff", weight: 1.5, fillColor: "#7c5cff", fillOpacity: 0.06,
      }).addTo(group);
    }
    for (const i of view.items) {
      const marker = L.circleMarker([i.lat, i.lon], {
        radius: 6, color: "#0b0d14", weight: 1.5, fillColor: pinColour(i), fillOpacity: 0.95,
      }).bindPopup(() => popup(i), { closeButton: false, maxWidth: 280 });
      marker.on("click", () => setPicked(i));
      marker.addTo(group);
      markers.current.set(i, marker);
    }
    if (view.centre) {
      m.fitBounds(L.latLng(view.centre.lat, view.centre.lon).toBounds(radius * 3219), { padding: [20, 20] });
    } else if (view.items.length) {
      m.fitBounds(L.latLngBounds(view.items.map((i) => [i.lat, i.lon] as [number, number])), { padding: [30, 30], maxZoom: 14 });
    }
  }, [view]);

  const show = (i: Item) => {
    setPicked(i);
    const marker = markers.current.get(i);
    if (map.current && marker) {
      map.current.setView([i.lat, i.lon], Math.max(map.current.getZoom(), 15));
      marker.openPopup();
    }
  };
  const toggle = (v: string) => setHas(has.includes(v) ? has.filter((x) => x !== v) : [...has, v]);
  const switchTo = (s: string) => { setSource(s); setHas([]); };
  const filters = source === "trades" ? TRADE_FILTERS : ALL_FILTERS;
  const exportUrl = source === "trades" ? api.mapExportUrl(query) : api.masterExportUrl(query);

  return (
    <div className="mapview">
      <aside className="map-side">
        <div className="seg map-source">
          <button className={source === "trades" ? "on" : ""} onClick={() => switchTo("trades")}>
            <PoundSterling size={13} /> UK trades, with money
          </button>
          <button className={source === "all" ? "on" : ""} onClick={() => switchTo("all")}>
            <Layers size={13} /> Every register, UK and US
          </button>
        </div>
        <form className="map-search" onSubmit={(e) => { e.preventDefault(); setNear(typed); setQ(qTyped); }}>
          {source === "all" && (
            <div className="search" style={{ gridColumn: "1 / -1" }}>
              <Search size={16} />
              <input className="input" value={qTyped} onChange={(e) => setQTyped(e.target.value)} placeholder="What kind? For example dentists, or care home" />
            </div>
          )}
          <div className="search">
            <MapPin size={16} />
            <input className="input" value={typed} onChange={(e) => setTyped(e.target.value)}
              placeholder={source === "all" && group === "us" ? "ZIP code or town, for example Austin, TX" : "Postcode or town, for example BN1 or Leeds"} />
          </div>
          <button className="btn primary" type="submit" aria-label="Search"><Search size={15} /></button>
        </form>
        <div className="row" style={{ gap: 6 }}>
          <span className="small muted">Within</span>
          <div className="seg small">
            {RADII.map((r) => (
              <button key={r} className={radius === r ? "on" : ""} onClick={() => setRadius(r)}>{r} {r === 1 ? "mile" : "mi"}</button>
            ))}
          </div>
        </div>
        {source === "trades" ? (
          <>
            <select className="input select" value={trades[0] ?? ""} onChange={(e) => setTrades(e.target.value ? [e.target.value] : [])}>
              <option value="">Every trade</option>
              {allTrades.map((t) => <option key={t.trade} value={t.trade}>{tradeName(t.trade)}</option>)}
            </select>
            <div className="row" style={{ gap: 6 }}>
              <div className="seg small">
                {SIZES.map(([v, label]) => <button key={label} className={size === v ? "on" : ""} onClick={() => setSize(v)}>{label}</button>)}
              </div>
              <div className="seg small">
                {WORTH.map(([v, label]) => <button key={label} className={worth === v ? "on" : ""} onClick={() => setWorth(v)}>{label}</button>)}
              </div>
            </div>
          </>
        ) : (
          <div className="seg small" style={{ alignSelf: "flex-start" }}>
            {[["uk", "🇬🇧 United Kingdom"], ["us", "🇺🇸 United States"]].map(([v, label]) => (
              <button key={v} className={group === v ? "on" : ""} onClick={() => { setGroup(v); setNear(""); setTyped(""); setArea(""); }}>{label}</button>
            ))}
          </div>
        )}
        <div className="chips">
          {[["", "Everyone"], ["can email", "Can email"], ["post only", "Post only"]].map(([v, label]) => (
            <button key={label} className={`chip ${rule === v ? "on" : ""}`} onClick={() => setRule(v)}>{label}</button>
          ))}
          {filters.map(([v, label, Icon]) => (
            <button key={v} className={`chip ${has.includes(v) ? "on" : ""}`} onClick={() => toggle(v)}>
              <Icon size={13} /> {label}
            </button>
          ))}
        </div>

        {source === "all" && area && !near.trim() && (
          <div className="chips">
            <button className="chip on" onClick={() => setArea("")}>Only {area.replaceAll("-", " ")} <X size={12} /></button>
          </div>
        )}
        {error && <div className="notice bad">{error}</div>}
        {needsMore && <div className="notice">Type a place, a kind of business, or both.</div>}
        {source === "trades" && trade && !trade.available && (
          <div className="notice warn">The trade lists aren't on this computer yet, so there's nothing to map.</div>
        )}

        {view && !needsMore && (
          <>
            <div className="map-stats" style={{ opacity: busy ? 0.5 : 1 }}>
              <div><b>{fmt(view.total)}</b><span>found{view.centre ? ` within ${radius} ${radius === 1 ? "mile" : "miles"} of ${view.centre.label}` : ""}</span></div>
              <div className="green"><b>{fmt(view.may)}</b><span>can email</span></div>
              <div className="blue"><b>{fmt(view.email)}</b><span>have an email</span></div>
              <div className="pink"><b>{fmt(view.fourth[0])}</b><span>{view.fourth[1]}</span></div>
            </div>
            {source === "trades" && trade?.money.available && (
              <div className="small muted">
                <PoundSterling size={13} style={{ verticalAlign: -2 }} /> {fmt(trade.money.registered)} registered companies ({pct(trade.money.registered ?? 0, trade.money.total ?? 0)}),{" "}
                {fmt(trade.money.with_net_assets)} show their net worth, {fmt(trade.money.publishes_turnover)} their turnover.
              </div>
            )}
            {source === "all" && (
              <div className="small faint">
                Each pin sits at the middle of its {group === "us" ? "ZIP code" : "postcode"}.{" "}
                {view.mapped < view.total ? `${fmt(view.mapped)} of ${fmt(view.total)} have one we can place.` : ""}
              </div>
            )}
            <div className="spread">
              <span className="small faint">
                {view.items.length < view.mapped ? `${view.centre ? "Nearest" : "Best"} ${fmt(view.items.length)} shown. ` : ""}
                <span className="legend-dot" style={{ background: GREEN }} /> can email
                <span className="legend-dot" style={{ background: AMBER, marginLeft: 10 }} /> post only
              </span>
              <a className="btn small" href={exportUrl}><Download size={14} /> Download</a>
            </div>
            <div className="map-list">
              {view.items.map((i, n) => (
                <button key={`${i.name}-${n}`} className={`map-item ${picked === i ? "on" : ""}`} onClick={() => show(i)}>
                  <span className="pin" style={{ background: pinColour(i) }} />
                  <span className="map-item-body">
                    <b>{i.name}</b>
                    <span className="cell-sub">
                      {[i.what, i.postcode, distance(i.miles)].filter(Boolean).join(" · ")}
                    </span>
                    <span className="map-item-icons">
                      {i.email && <Mail size={13} />}
                      {(i.phone || i.mobile) && <Phone size={13} />}
                      {i.website && <Globe size={13} />}
                      {i.turnover ? <span className="badge green-soft">turnover {money(i.turnover)}</span>
                        : i.netAssets ? <span className="badge grey" style={{ padding: "0 7px", fontSize: 11 }}>worth {money(i.netAssets)}</span> : null}
                      {/^(micro|small|medium|large)/.test(i.size) && <span className="faint small">{i.size}</span>}
                    </span>
                  </span>
                </button>
              ))}
              {!view.items.length && <div className="empty">Nothing here. Try a wider circle or fewer filters.</div>}
            </div>
          </>
        )}
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
            <RuleBadge rule={picked.rule} />
            <dl className="kv">
              {picked.what && (<><dt>What</dt><dd>{picked.what}</dd></>)}
              {picked.email && (<><dt>Email</dt><dd>{picked.email} <span className="faint small">{picked.emailType}</span></dd></>)}
              {picked.phone && (<><dt>Phone</dt><dd>{picked.phone}</dd></>)}
              {picked.mobile && picked.mobile !== picked.phone && (<><dt>Mobile</dt><dd>{picked.mobile}</dd></>)}
              {picked.website && (<><dt>Website</dt><dd><a href={link(picked.website)} target="_blank" rel="noreferrer" style={{ color: "var(--accent-2)" }}>{picked.website.replace(/^https?:\/\/(www\.)?/, "")}</a></dd></>)}
              {(picked.company || picked.companyType) && (<><dt>Company</dt><dd>{picked.company} {picked.companyType && <span className="faint small">{picked.companyType}</span>}</dd></>)}
              {picked.size && (<><dt>Size</dt><dd>{picked.size}{picked.staff ? `, ${picked.staff} staff` : ""}</dd></>)}
              {picked.netAssets && (<><dt>Net worth</dt><dd>{money(picked.netAssets)}{picked.accountsTo ? ` (accounts to ${picked.accountsTo})` : ""}</dd></>)}
              {picked.turnover && (<><dt>Turnover</dt><dd>{money(picked.turnover)}</dd></>)}
              {picked.sources && (<><dt>Found in</dt><dd className="small">{picked.sources.split(";").map((s) => s.trim()).filter(Boolean).join(", ")}</dd></>)}
            </dl>
          </div>
        )}
      </div>
    </div>
  );
}
