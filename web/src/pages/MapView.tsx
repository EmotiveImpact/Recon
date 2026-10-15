import { useEffect, useMemo, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { Building2, Download, Globe, Layers, Mail, MapPin, Phone, PoundSterling, Search, SlidersHorizontal, Smartphone, X } from "lucide-react";
import { api, type Heat, type MapResults, type MasterResults, type Row, type SectorTree } from "../api";
import { fmt, RuleBadge, splitList } from "../ui";

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
const GREEN = "#2dd4bf";
const AMBER = "#a78bfa";

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
// Purple where few may be emailed, teal where many may.
const shade = (share: number) => {
  const t = Math.max(0, Math.min(1, share / 0.3));
  const mix = (a: number, b: number) => Math.round(a + (b - a) * t);
  return `rgb(${mix(124, 45)}, ${mix(92, 212)}, ${mix(255, 191)})`;
};
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

// Keep what's found in the gap between the side panels on a wide screen.
const clear = (): L.FitBoundsOptions => (window.innerWidth > 860
  ? { paddingTopLeft: [400, 30], paddingBottomRight: [350, 70] } : { padding: [20, 20] });

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
  const [source, setSource] = useState(initial.get("source") === "trades" ? "trades" : "all");
  const start = initial.get("near") ?? "";
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
  const [sector, setSector] = useState(initial.get("sector") ?? "");
  const [industry, setIndustry] = useState(initial.get("industry") ?? "");
  const [niche, setNiche] = useState(initial.get("niche") ?? "");
  const [tree, setTree] = useState<SectorTree | null>(null);
  const [trade, setTrade] = useState<MapResults | null>(null);
  const [heat, setHeat] = useState<Heat | null>(null);
  const [all, setAll] = useState<MasterResults | null>(null);
  const [allTrades, setAllTrades] = useState<{ trade: string; name: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [picked, setPicked] = useState<Item | null>(null);
  const mapBox = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const layer = useRef<L.LayerGroup | null>(null);
  const label = useRef<L.Tooltip | null>(null);
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
      if (sector) p.set("sector", sector);
      if (industry) p.set("industry", industry);
      if (niche) p.set("niche", niche);
    }
    return p;
  }, [source, near, radius, trades, rule, has, size, worth, group, q, area, sector, industry, niche]);

  // With no place chosen, the map shows the whole country area by area:
  // the trade lists, or every organisation in the chosen sector.
  const sectorHeat = source === "all" && !near.trim() && !q.trim() && !area && !!tree?.available;
  const heatMode = (source === "trades" && !near.trim()) || sectorHeat;
  const needsMore = source === "all" && !near.trim() && !q.trim() && !area && !sectorHeat;

  useEffect(() => {
    setTree(null);
    api.sectors(group).then(setTree, () => setTree(null));
  }, [group]);
  const chosen = tree?.sectors.find((s) => s.sector === sector);
  const chosenIndustry = chosen?.industries.find((i) => i.industry === industry);
  const chosenNiche = chosenIndustry?.niches.find((n) => n.niche === niche);
  const pickSector = (v: string) => { setSector(v); setIndustry(""); setNiche(""); };
  const pickIndustry = (v: string) => { setIndustry(v); setNiche(""); };
  const path = [chosen?.name, chosenIndustry?.name, chosenNiche?.name].filter(Boolean) as string[];

  useEffect(() => {
    if (!mapBox.current || map.current) return;
    const m = L.map(mapBox.current, { preferCanvas: true, zoomControl: false, worldCopyJump: true, zoomSnap: 0.25 }).setView([54.5, -2.5], 6);
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
    if (sectorHeat) {
      api.sectorHeat(query).then((d) => { setHeat(d); setAll(null); done(); }, failed);
    } else if (heatMode) {
      api.heat(query).then((d) => { setHeat(d); setTrade(null); if (d.trades?.length) setAllTrades(d.trades); done(); }, failed);
    } else if (source === "trades") {
      api.map(query).then((d) => { setTrade(d); if (d.trades?.length) setAllTrades(d.trades); done(); }, failed);
    } else {
      api.masterSearch(query).then((d) => { setAll(d); done(); }, failed);
    }
  }, [query, needsMore, heatMode, sectorHeat]);

  // What's on show, in one shape whichever list it came from.
  const view = useMemo(() => {
    if (heatMode && heat?.available) {
      const total = heat.districts.reduce((n, d) => n + d.count, 0);
      const may = heat.districts.reduce((n, d) => n + d.may_email, 0);
      const email = heat.districts.reduce((n, d) => n + (d.with_email ?? 0), 0);
      const phone = heat.districts.reduce((n, d) => n + (d.with_phone ?? 0), 0);
      const fourth = (sectorHeat ? [phone, "have a phone"] : [heat.districts.length, "postcode areas"]) as [number, string];
      return { items: [] as Item[], centre: null, total, may, email, fourth, mapped: total };
    }
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
  }, [source, trade, all, heat, heatMode, sectorHeat]);

  // Draw the pins and the circle whenever the results change.
  useEffect(() => {
    const m = map.current;
    const group = layer.current;
    if (!m || !group) return;
    group.clearLayers();
    markers.current.clear();
    if (!view) return;
    if (heatMode && heat?.available) {
      const top = Math.max(1, ...heat.districts.map((d) => d.count));
      for (const d of heat.districts) {
        L.circleMarker([d.lat, d.lon], {
          radius: 2 + Math.sqrt(d.count / top) * 9, stroke: false,
          fillColor: shade(d.count ? d.may_email / d.count : 0), fillOpacity: 0.6,
        })
          .bindTooltip(`<b>${d.district}</b><br>${fmt(d.count)} businesses, ${fmt(d.may_email)} can email`, { direction: "top", className: "heat-tip" })
          .on("click", () => goTo(d.district))
          .addTo(group);
      }
      m.fitBounds([[49.9, -7.6], [58.7, 1.8]], clear());
      return;
    }
    if (view.centre) {
      L.circle([view.centre.lat, view.centre.lon], {
        radius: radius * 1609.34, color: "#22d3ee", weight: 1.5, dashArray: "4 6", fillColor: "#22d3ee", fillOpacity: 0.05,
      }).addTo(group);
    }
    for (const i of view.items) {
      L.circleMarker([i.lat, i.lon], { radius: 8, stroke: false, fillColor: pinColour(i), fillOpacity: 0.06, interactive: false }).addTo(group);
    }
    for (const i of view.items) {
      const marker = L.circleMarker([i.lat, i.lon], {
        radius: 4.5, color: "#0b0d14", weight: 1, opacity: 0.8, fillColor: pinColour(i), fillOpacity: 0.9,
      }).bindPopup(() => popup(i), { closeButton: false, maxWidth: 280 });
      marker.on("click", () => setPicked(i));
      marker.addTo(group);
      markers.current.set(i, marker);
    }
    if (view.centre) {
      m.fitBounds(L.latLng(view.centre.lat, view.centre.lon).toBounds(radius * 3219), clear());
    } else if (view.items.length) {
      m.fitBounds(L.latLngBounds(view.items.map((i) => [i.lat, i.lon] as [number, number])), { ...clear(), maxZoom: 14 });
    }
  }, [view]);

  // Write the chosen business's name on the map beside its pin.
  useEffect(() => {
    label.current?.remove();
    label.current = null;
    if (picked && map.current) {
      label.current = L.tooltip({ permanent: true, direction: "right", offset: [8, 0], className: "pin-label" })
        .setLatLng([picked.lat, picked.lon]).setContent(picked.name.replace(/[<>&]/g, "")).addTo(map.current);
    }
  }, [picked]);

  // The ranking down the left: trades for the trade lists, kinds of organisation otherwise.
  const ranking = useMemo((): { label: string; count: number; pick?: () => void }[] => {
    if (sectorHeat && tree) {
      if (chosenIndustry) return chosenIndustry.niches.map((n) => ({ label: n.name, count: n.count, pick: chosenNiche ? undefined : () => setNiche(n.niche) }));
      if (chosen) return chosen.industries.map((i) => ({ label: i.name, count: i.count, pick: () => pickIndustry(i.industry) }));
      return [...tree.sectors].sort((a, b) => b.count - a.count).map((s) => ({ label: s.name, count: s.count, pick: () => pickSector(s.sector) }));
    }
    if (source === "trades" && trade?.available) return trade.by_trade.map((t) => ({ label: t.name, count: t.count }));
    const counts = new Map<string, number>();
    for (const i of view?.items ?? []) {
      // "company; dental clinic; dental practice" counts as a dental clinic.
      const kind = i.what.split(";").map((k) => k.trim()).find((k) => k && k !== "company") ?? "";
      if (kind) {
        const label = kind.charAt(0).toUpperCase() + kind.slice(1);
        counts.set(label, (counts.get(label) ?? 0) + 1);
      }
    }
    return [...counts].sort((a, b) => b[1] - a[1]).map(([label, count]) => ({ label, count }));
  }, [source, trade, view, sectorHeat, tree, chosen, chosenIndustry, chosenNiche]);

  // The right-hand money panels: the richest businesses here, and how their net worth spreads.
  const richest = useMemo(() => (view?.items ?? [])
    .filter((i) => i.netAssets && !Number.isNaN(Number(i.netAssets)))
    .sort((a, b) => Number(b.netAssets) - Number(a.netAssets)).slice(0, 5), [view]);
  const spread = useMemo(() => {
    const bands = [["Under £10k", -Infinity, 1e4], ["£10k to £100k", 1e4, 1e5], ["£100k to £1m", 1e5, 1e6], ["£1m or more", 1e6, Infinity]] as const;
    const worths = (view?.items ?? []).filter((i) => i.netAssets !== "").map((i) => Number(i.netAssets)).filter((n) => !Number.isNaN(n));
    return bands.map(([label, lo, hi]) => ({ label, count: worths.filter((n) => n >= lo && n < hi).length }));
  }, [view]);

  const show = (i: Item) => {
    setPicked(i);
    const marker = markers.current.get(i);
    if (map.current && marker) {
      map.current.setView([i.lat, i.lon], Math.max(map.current.getZoom(), 15));
      marker.openPopup();
    }
  };
  const goTo = (place: string) => { setTyped(place); setNear(place); };
  const toggle = (v: string) => setHas(has.includes(v) ? has.filter((x) => x !== v) : [...has, v]);
  const switchTo = (s: string) => { setSource(s); setHas([]); };
  const filters = source === "trades" ? TRADE_FILTERS : ALL_FILTERS;
  const exportUrl = source === "trades" ? api.mapExportUrl(query) : api.masterExportUrl(query);
  const [more, setMore] = useState(false);
  const place = view?.centre?.label || (area ? area.replaceAll("-", " ") : "");
  const top = Math.max(1, ...ranking.slice(0, 6).map((r) => r.count));
  const spreadTop = Math.max(1, ...spread.map((s) => s.count));
  const areas = heatMode ? [...(heat?.districts ?? [])].sort((a, b) => b.may_email - a.may_email) : trade?.by_district ?? [];
  const areaTop = Math.max(1, ...areas.slice(0, 6).map((a) => a.may_email));
  const founded = (heatMode ? heat?.founded : source === "trades" ? trade?.founded : []) ?? [];
  const extra = (source === "trades" ? (size ? 1 : 0) + (worth ? 1 : 0) : 0) + has.length;

  return (
    <div className="mapview">
      <div className="map-wrap">
        <div ref={mapBox} className="map" />
        {busy && <div className="map-busy">Looking…</div>}
      </div>

      <div className="hud hud-left">
        <section className="hud-panel hud-title">
          <h1>{place ? `Businesses near ${place}` : heatMode ? (path.at(-1) ?? "The whole country") : "Business map"}</h1>
          <div className="hud-en">{source === "trades" ? "UK trades, with company money" : `Every organisation, ${group === "us" ? "United States" : "United Kingdom"}`}</div>
          <div className="hud-tabs">
            <button className={source === "all" ? "on" : ""} onClick={() => switchTo("all")}><Layers size={13} /> Every organisation</button>
            <button className={source === "trades" ? "on" : ""} onClick={() => switchTo("trades")}><PoundSterling size={13} /> Trades with money</button>
          </div>
          <form className="map-search" onSubmit={(e) => { e.preventDefault(); setNear(typed); setQ(qTyped); }}>
            {source === "all" && (
              <div className="search" style={{ gridColumn: "1 / -1" }}>
                <Search size={15} />
                <input className="input" value={qTyped} onChange={(e) => setQTyped(e.target.value)} placeholder="What kind? For example dentists" />
              </div>
            )}
            <div className="search">
              <MapPin size={15} />
              <input className="input" value={typed} onChange={(e) => setTyped(e.target.value)}
                placeholder={source === "all" && group === "us" ? "ZIP code or town, e.g. Austin, TX" : "Postcode or town, e.g. BN1 or Leeds"} />
            </div>
            <button className="btn primary" type="submit" aria-label="Search"><Search size={15} /></button>
          </form>
          <div className="hud-row">
            <div className="seg small radii">
              {RADII.map((r) => (
                <button key={r} className={radius === r ? "on" : ""} onClick={() => setRadius(r)}>{r} mi</button>
              ))}
            </div>
            <button className={`btn small ghost ${more || extra ? "lit" : ""}`} onClick={() => setMore(!more)}>
              <SlidersHorizontal size={13} /> Filters{extra ? ` (${extra})` : ""}
            </button>
          </div>
          {source === "trades" ? (
            <select className="input select" value={trades[0] ?? ""} onChange={(e) => setTrades(e.target.value ? [e.target.value] : [])}>
              <option value="">Every trade</option>
              {allTrades.map((t) => <option key={t.trade} value={t.trade}>{tradeName(t.trade)}</option>)}
            </select>
          ) : (
            <div className="seg small" style={{ alignSelf: "flex-start" }}>
              {[["uk", "🇬🇧 United Kingdom"], ["us", "🇺🇸 United States"]].map(([v, label]) => (
                <button key={v} className={group === v ? "on" : ""} onClick={() => { setGroup(v); setNear(""); setTyped(""); setArea(""); pickSector(""); }}>{label}</button>
              ))}
            </div>
          )}
          {source === "all" && tree?.available && (
            <div className="sector-pick">
              <div className="sector-path">
                <button className={path.length ? "" : "on"} onClick={() => pickSector("")}>All sectors</button>
                {path.map((name, n) => (
                  <button key={name} className={n === path.length - 1 ? "on" : ""}
                    onClick={() => (n === 0 ? pickIndustry("") : setNiche(""))}>{name}</button>
                ))}
              </div>
              <select className="input select" value={sector} onChange={(e) => pickSector(e.target.value)} aria-label="Sector">
                <option value="">Every sector</option>
                {tree.sectors.map((s) => <option key={s.sector} value={s.sector}>{s.name} ({fmt(s.count)})</option>)}
              </select>
              {chosen && (
                <select className="input select" value={industry} onChange={(e) => pickIndustry(e.target.value)} aria-label="Industry">
                  <option value="">Every industry</option>
                  {chosen.industries.map((i) => <option key={i.industry} value={i.industry}>{i.name} ({fmt(i.count)})</option>)}
                </select>
              )}
              {chosenIndustry && (
                <select className="input select" value={niche} onChange={(e) => setNiche(e.target.value)} aria-label="Niche">
                  <option value="">Every niche</option>
                  {chosenIndustry.niches.map((n) => <option key={n.niche} value={n.niche}>{n.name} ({fmt(n.count)})</option>)}
                </select>
              )}
            </div>
          )}
          {more && (
            <div className="hud-more">
              {source === "trades" && (
                <>
                  <div className="seg small">
                    {SIZES.map(([v, label]) => <button key={label} className={size === v ? "on" : ""} onClick={() => setSize(v)}>{label}</button>)}
                  </div>
                  <div className="seg small">
                    {WORTH.map(([v, label]) => <button key={label} className={worth === v ? "on" : ""} onClick={() => setWorth(v)}>{label}</button>)}
                  </div>
                </>
              )}
              <div className="chips">
                {filters.map(([v, label, Icon]) => (
                  <button key={v} className={`chip ${has.includes(v) ? "on" : ""}`} onClick={() => toggle(v)}><Icon size={13} /> {label}</button>
                ))}
              </div>
            </div>
          )}
          {source === "all" && area && !near.trim() && (
            <div className="chips"><button className="chip on" onClick={() => setArea("")}>Only {area.replaceAll("-", " ")} <X size={12} /></button></div>
          )}
          {error && <div className="notice bad">{error}</div>}
          {needsMore && <div className="notice">Type a place, a kind of business, or both.</div>}
          {source === "trades" && trade && !trade.available && (
            <div className="notice warn">The trade lists aren't on this computer yet, so there's nothing to map.</div>
          )}
        </section>

        {view && !needsMore && (
          <>
            <section className="hud-panel hud-split" style={{ opacity: busy ? 0.5 : 1 }}>
              <div>
                <h3 className="hud-h">Businesses found</h3>
                <div className="hud-big">{fmt(view.total)}</div>
                <div className="hud-note">{view.centre ? `within ${radius} ${radius === 1 ? "mile" : "miles"}` : heatMode ? "across the UK" : "in this search"}</div>
                <div className="hud-mini">
                  {(!heatMode || sectorHeat) && <span><b className="t-blue">{fmt(view.email)}</b> have an email</span>}
                  <span><b className="t-pink">{fmt(view.fourth[0])}</b> {view.fourth[1]}</span>
                </div>
              </div>
              <div className="hud-ring">
                <h3 className="hud-h">Can email</h3>
                <Ring part={view.may} whole={view.total} />
              </div>
            </section>

            {ranking.length > 0 && (
              <section className="hud-panel">
                <h3 className="hud-h">{source === "trades" ? "Trades here" : sectorHeat ? (chosenIndustry ? "Niches" : chosen ? "Industries" : "Sectors") : "Kinds here"}</h3>
                <ol className="hud-rank">
                  {ranking.slice(0, 6).map((r, n) => (
                    <li key={r.label} className={r.pick ? "click" : ""} onClick={r.pick} title={r.pick ? `Narrow to ${r.label}` : undefined}>
                      <span className="n">{n + 1}</span>
                      <span className="l">{r.label}</span>
                      <span className="hud-track"><i style={{ width: `${(r.count / top) * 100}%` }} /></span>
                      <b>{fmt(r.count)}</b>
                    </li>
                  ))}
                </ol>
              </section>
            )}

            {heatMode && areas.length > 1 && (
              <section className="hud-panel">
                <h3 className="hud-h">{heatMode ? "Best areas to email" : "Areas here"}</h3>
                <ol className="hud-rank">
                  {areas.slice(0, 6).map((a, n) => (
                    <li key={a.district} className="click" onClick={() => goTo(a.district)} title={`Show ${a.district}`}>
                      <span className="n">{n + 1}</span>
                      <span className="l">{a.district}</span>
                      <span className="hud-track"><i style={{ width: `${(a.may_email / areaTop) * 100}%` }} /></span>
                      <b>{fmt(a.may_email)}</b>
                    </li>
                  ))}
                </ol>
                <div className="hud-note">Number you can email in each postcode area. Click one to look there.</div>
              </section>
            )}

            {heatMode ? (
              <section className="hud-panel hud-hint">
                <MapPin size={16} /> Bigger circles hold more businesses; teal ones have more you can email. Click one, or type a place, to see the businesses.
              </section>
            ) : (
            <section className="hud-panel hud-list">
              <div className="spread">
                <h3 className="hud-h">{view.items.length < view.mapped ? `Nearest ${fmt(view.items.length)}` : "The list"}</h3>
                <a className="btn small ghost" href={exportUrl}><Download size={13} /> Download</a>
              </div>
              <div className="map-list">
                {view.items.map((i, n) => (
                  <button key={`${i.name}-${n}`} className={`map-item ${picked === i ? "on" : ""}`} onClick={() => show(i)}>
                    <span className="pin" style={{ background: pinColour(i) }} />
                    <span className="map-item-body">
                      <b>{i.name}</b>
                      <span className="cell-sub">{[i.what, i.postcode, distance(i.miles)].filter(Boolean).join(" · ")}</span>
                    </span>
                    <span className="map-item-icons">
                      {i.email && <Mail size={12} />}
                      {(i.phone || i.mobile) && <Phone size={12} />}
                      {i.website && <Globe size={12} />}
                    </span>
                  </button>
                ))}
                {!view.items.length && <div className="empty">Nothing here. Try a wider circle or fewer filters.</div>}
              </div>
            </section>
            )}
          </>
        )}
      </div>

      {view && !needsMore && (
        <div className="hud hud-right">
          {heatMode ? null : picked ? (
            <section className="hud-panel">
              <div className="spread" style={{ alignItems: "flex-start" }}>
                <div className="hud-pick">
                  <span className="hud-logo"><Building2 size={18} /></span>
                  <div>
                    <b>{picked.name}</b>
                    <div className="cell-sub">{picked.what}</div>
                  </div>
                </div>
                <button className="btn ghost small" onClick={() => setPicked(null)} aria-label="Close"><X size={14} /></button>
              </div>
              <RuleBadge rule={picked.rule} />
              <dl className="kv">
                <dt>Address</dt><dd>{[picked.address, picked.town, picked.postcode].filter(Boolean).join(", ") || "Not known"}</dd>
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
            </section>
          ) : (
            <section className="hud-panel hud-hint">
              <MapPin size={16} /> Click a pin or a name to see the business here.
            </section>
          )}

          {richest.length > 0 && (
            <section className="hud-panel">
              <h3 className="hud-h">Richest here, by net worth</h3>
              <div className="hud-top">
                {richest.map((i, n) => (
                  <button key={`${i.name}-${n}`} onClick={() => show(i)}>
                    <span className="dot" style={{ background: n === 0 ? GREEN : n === 1 ? "#22d3ee" : AMBER }} />
                    <span className="l"><b>{i.name}</b><span>{i.size || i.what}{i.staff ? `, ${i.staff} staff` : ""}</span></span>
                    <span className="v">{money(i.netAssets)}</span>
                  </button>
                ))}
              </div>
            </section>
          )}

{!heatMode && areas.length > 1 && (
            <section className="hud-panel">
              <h3 className="hud-h">{heatMode ? "Best areas to email" : "Areas here"}</h3>
              <ol className="hud-rank">
                {areas.slice(0, 6).map((a, n) => (
                  <li key={a.district} className="click" onClick={() => goTo(a.district)} title={`Show ${a.district}`}>
                    <span className="n">{n + 1}</span>
                    <span className="l">{a.district}</span>
                    <span className="hud-track"><i style={{ width: `${(a.may_email / areaTop) * 100}%` }} /></span>
                    <b>{fmt(a.may_email)}</b>
                  </li>
                ))}
              </ol>
              <div className="hud-note">Number you can email in each postcode area. Click one to look there.</div>
            </section>
          )}

          {founded.length > 2 && (
            <section className="hud-panel">
              <div className="spread">
                <h3 className="hud-h">Companies started each year</h3>
                <span className="hud-note">{founded[0].year} to {founded[founded.length - 1].year}</span>
              </div>
              <Trend points={founded} />
              <div className="hud-note">When the registered companies {heatMode ? "on the map" : "here"} were set up, from Companies House.</div>
            </section>
          )}

          {source === "trades" && trade?.money.available && (
            <section className="hud-panel">
              <h3 className="hud-h">Money they publish</h3>
              <div className="hud-bars">
                {spread.map((s) => (
                  <div key={s.label}>
                    <span>{s.label}</span>
                    <span className="hud-track"><i style={{ width: `${(s.count / spreadTop) * 100}%` }} /></span>
                    <b>{fmt(s.count)}</b>
                  </div>
                ))}
              </div>
              <div className="hud-note" style={{ marginTop: 8 }}>
                {fmt(trade.money.registered)} registered companies here. {fmt(trade.money.with_net_assets)} show their net worth
                and {fmt(trade.money.publishes_turnover)} publish their turnover.
              </div>
            </section>
          )}
          {source === "all" && (
            <section className="hud-panel hud-note">
              Each pin sits at the middle of its {group === "us" ? "ZIP code" : "postcode"}.{" "}
              {view.mapped < view.total ? `${fmt(view.mapped)} of ${fmt(view.total)} have one we can place.` : ""}
            </section>
          )}
        </div>
      )}

      {view && !needsMore && (
        <div className="hud-bottom">
          {[["", "Everyone", "#e5e7eb"], ["can email", "Can email", GREEN], ["post only", "Post only", AMBER]].map(([v, label, colour]) => (
            <button key={label} className={rule === v ? "on" : ""} onClick={() => setRule(v)}>
              <span className="radio" style={{ borderColor: colour, background: rule === v ? colour : "transparent" }} /> {label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// A small line chart: companies started each year.
function Trend({ points }: { points: { year: number; count: number }[] }) {
  const w = 280, h = 90, pad = 4;
  const top = Math.max(1, ...points.map((p) => p.count));
  const xy = points.map((p, n) => [pad + (n / (points.length - 1)) * (w - pad * 2), h - 14 - (p.count / top) * (h - 26)]);
  const line = xy.map(([x, y], n) => `${n ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const last = points[points.length - 1];
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="trend" role="img" aria-label="Companies started each year">
      <defs>
        <linearGradient id="trend-fill" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor="#ffffff" stopOpacity="0.12" />
          <stop offset="1" stopColor="#ffffff" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={`${line} L${xy[xy.length - 1][0]},${h - 14} L${xy[0][0]},${h - 14} Z`} fill="url(#trend-fill)" />
      <path d={line} fill="none" stroke="#c9ccd6" strokeWidth="1.4" />
      {xy.map(([x, y], n) => <circle key={n} cx={x} cy={y} r="1.8" fill="#c9ccd6"><title>{`${points[n].year}: ${points[n].count}`}</title></circle>)}
      <text x={pad} y={h - 2} className="trend-l">{points[0].year}</text>
      <text x={w - pad} y={h - 2} textAnchor="end" className="trend-l">{last.year}: {fmt(last.count)}</text>
    </svg>
  );
}

function Ring({ part, whole }: { part: number; whole: number }) {
  const share = whole ? part / whole : 0;
  const r = 34;
  const around = 2 * Math.PI * r;
  return (
    <svg viewBox="0 0 90 90" className="ring">
      <circle cx="45" cy="45" r={r} fill="none" stroke="#ffffff" strokeOpacity="0.1" strokeWidth="5" />
      <circle cx="45" cy="45" r={r} fill="none" stroke="#e5e7eb" strokeWidth="5" strokeLinecap="round"
        strokeDasharray={`${share * around} ${around}`} transform="rotate(-90 45 45)" />
      <text x="45" y="46" textAnchor="middle" className="ring-v">{(share * 100).toFixed(1)}%</text>
      <text x="45" y="60" textAnchor="middle" className="ring-l">{fmt(part)}</text>
    </svg>
  );
}
