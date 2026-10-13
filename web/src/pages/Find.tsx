import { useEffect, useMemo, useState } from "react";
import { Database, Download, ExternalLink, Globe, Mail, Map as MapIcon, MapPin, Navigation, Phone, Search, User, X } from "lucide-react";
import { api, type MasterResults, type MasterStatus, type Row } from "../api";
import { fmt, pct, RuleBadge, splitList } from "../ui";
import ResultsMap from "./ResultsMap";

// Ready-made searches. Commas mean "or"; words are matched on their stem,
// so "plumbers" also finds "plumbing".
const PICKS: [string, string][] = [
  ["Plumbers", "plumbers"],
  ["Electricians", "electrician, electrical installation"],
  ["Builders", "builders, construction of domestic buildings"],
  ["Roofers", "roofing, roofer"],
  ["Cleaners", "cleaning"],
  ["Hair salons", "hairdressing, hair salon, hairdresser"],
  ["Beauty salons", "beauty"],
  ["Barbers", "barber"],
  ["Dentists", "dental, dentist"],
  ["Care homes", "care home, residential care, nursing home"],
  ["Garages", "garage, motor vehicles repair, MOT"],
  ["Cafés and restaurants", "cafe, restaurant"],
  ["Accountants", "accounting, bookkeeping, accountant"],
  ["Solicitors", "legal activities, solicitor, law firm"],
  ["Estate agents", "real estate agencies, estate agent, letting"],
  ["Gyms", "fitness facilities, gym"],
  ["Childcare", "child day-care, child care, nursery"],
  ["Vets", "veterinary"],
  ["Florists", "florist, flowers"],
  ["Photographers", "photographic, photographer"],
];

const COUNTRIES: [string, string][] = [["uk", "🇬🇧 United Kingdom"], ["us", "🇺🇸 United States"], ["other", "🌍 Elsewhere"]];

const UK_AREAS: Record<string, string> = {
  england: "England", scotland: "Scotland", wales: "Wales", "northern-ireland": "Northern Ireland",
  "crown-dependencies": "Channel Islands and Isle of Man", unknown: "Place not known",
};
const US_STATES: Record<string, string> = {
  al: "Alabama", ak: "Alaska", az: "Arizona", ar: "Arkansas", ca: "California", co: "Colorado", ct: "Connecticut",
  de: "Delaware", dc: "District of Columbia", fl: "Florida", ga: "Georgia", hi: "Hawaii", id: "Idaho", il: "Illinois",
  in: "Indiana", ia: "Iowa", ks: "Kansas", ky: "Kentucky", la: "Louisiana", me: "Maine", md: "Maryland",
  ma: "Massachusetts", mi: "Michigan", mn: "Minnesota", ms: "Mississippi", mo: "Missouri", mt: "Montana",
  ne: "Nebraska", nv: "Nevada", nh: "New Hampshire", nj: "New Jersey", nm: "New Mexico", ny: "New York",
  nc: "North Carolina", nd: "North Dakota", oh: "Ohio", ok: "Oklahoma", or: "Oregon", pa: "Pennsylvania",
  ri: "Rhode Island", sc: "South Carolina", sd: "South Dakota", tn: "Tennessee", tx: "Texas", ut: "Utah",
  vt: "Vermont", va: "Virginia", wa: "Washington", wv: "West Virginia", wi: "Wisconsin", wy: "Wyoming",
  pr: "Puerto Rico", gu: "Guam", vi: "US Virgin Islands", as: "American Samoa", mp: "Northern Mariana Islands",
  unknown: "Place not known",
};

const areaName = (group: string, area: string) =>
  group === "uk" ? UK_AREAS[area] ?? area : group === "us" ? US_STATES[area] ?? area.toUpperCase() : area.replaceAll("-", " ");

const HAS: [string, string][] = [["email", "Has an email"], ["phone", "Has a phone"], ["website", "Has a website"], ["person", "Named person"]];
const RULES: [string, string][] = [["", "Everyone"], ["can email", "Can email"], ["post only", "Post only"]];
const MILES = ["1", "3", "5", "10", "25", "50"];
// Distances need postcode positions, which Recon has for the UK and the US.
const MAPPED = ["uk", "us"];
const miles = (m: string) => `${Number(m) < 10 ? Number(m).toFixed(1) : Math.round(Number(m))} miles`;

function Details({ row, group, onClose }: { row: Row; group: string; onClose: () => void }) {
  const list = (v: string) => splitList(v);
  return (
    <>
      <div className="scrim" onClick={onClose} />
      <aside className="drawer">
        <div className="spread" style={{ alignItems: "flex-start" }}>
          <div>
            <h2 style={{ fontSize: 22 }}>{row.name}</h2>
            <div className="muted small">{row.kind}{row.legal_form ? ` · ${row.legal_form}` : ""}</div>
          </div>
          <button className="btn ghost small" onClick={onClose} aria-label="Close"><X size={16} /></button>
        </div>
        <div className={`notice ${row.can_email === "can email" ? "good" : "warn"}`}>
          <div>
            <RuleBadge rule={row.can_email} />
            <p className="small" style={{ marginTop: 6 }}>
              {row.can_email === "can email"
                ? "You may email this organisation, with a clear way to opt out."
                : "Possibly a sole trader or partnership. Write by post, or email only with their consent."}
            </p>
          </div>
        </div>
        {[["Emails", row.emails, Mail], ["Phones", row.phones, Phone], ["Websites", row.website, Globe], ["People", row.people, User]].map(
          ([title, value, Icon]) => {
            const items = list(value as string);
            const I = Icon as typeof Mail;
            return (
              <div key={title as string}>
                <div className="section-title">{title as string}</div>
                {items.length ? (
                  <div className="list">
                    {items.map((item) => (
                      <div key={item} className="list-item">
                        <span className="row" style={{ gap: 8, minWidth: 0 }}>
                          <I size={14} className="faint" />
                          {title === "Websites" ? (
                            <a href={item.startsWith("http") ? item : `https://${item}`} target="_blank" rel="noreferrer" style={{ color: "var(--accent-2)", wordBreak: "break-all" }}>{item}</a>
                          ) : <span style={{ wordBreak: "break-all" }}>{item}</span>}
                        </span>
                      </div>
                    ))}
                  </div>
                ) : <p className="faint small">None listed.</p>}
              </div>
            );
          },
        )}
        {row.socials && (
          <div>
            <div className="section-title">Social links</div>
            <div className="chips">
              {list(row.socials).map((s) => (
                <a key={s} className="chip" href={s} target="_blank" rel="noreferrer">{s.replace(/^https?:\/\/(www\.)?/, "").split("/")[0]} <ExternalLink size={12} /></a>
              ))}
            </div>
          </div>
        )}
        <div>
          <div className="section-title">Organisation</div>
          <dl className="kv">
            <dt>Address</dt>
            <dd>{[row.address, row.town, row.region, row.postcode].filter(Boolean).join(", ") || "Not known"}</dd>
            <dt>Area</dt>
            <dd>{areaName(group, row.area)}</dd>
            {row.miles !== "" && row.miles != null && (<><dt>Distance</dt><dd>{miles(row.miles)} away</dd></>)}
            {row.category && (<><dt>What it does</dt><dd className="small">{row.category.length > 600 ? row.category.slice(0, 600) + "…" : row.category}</dd></>)}
            <dt>Found in</dt>
            <dd>{row.sources.split(";").map((s) => s.trim()).filter(Boolean).join(", ")}</dd>
          </dl>
        </div>
      </aside>
    </>
  );
}

export default function Find({ initial }: { initial?: URLSearchParams }) {
  const [status, setStatus] = useState<MasterStatus | null>(null);
  const [group, setGroup] = useState(initial?.get("group") || "uk");
  const [area, setArea] = useState(initial?.get("area") || "");
  const [typed, setTyped] = useState(initial?.get("q") ?? "plumbers");
  const [q, setQ] = useState(initial?.get("q") ?? "plumbers");
  const [rule, setRule] = useState("");
  const [has, setHas] = useState<string[]>([]);
  const [kind, setKind] = useState("");
  const [kinds, setKinds] = useState<{ kind: string; count: number }[]>([]);
  const [town, setTown] = useState("");
  const [nearTyped, setNearTyped] = useState("");
  const [near, setNear] = useState("");
  const [radius, setRadius] = useState("5");
  const [mapData, setMapData] = useState<MasterResults | null>(null);
  const [showMap, setShowMap] = useState(true);
  const [page, setPage] = useState(1);
  const [data, setData] = useState<MasterResults | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [open, setOpen] = useState<Row | null>(null);
  const [showSources, setShowSources] = useState(false);

  useEffect(() => {
    api.master().then(setStatus, (e) => setError(e.message));
  }, []);
  useEffect(() => {
    setNear("");
    setNearTyped("");
    setKind("");
    if (status?.available) api.masterKinds(group).then(setKinds, () => setKinds([]));
  }, [group, status?.available]);

  const query = useMemo(() => {
    const p = new URLSearchParams({ group });
    if (area) p.set("area", area);
    if (q.trim()) p.set("q", q.trim());
    if (rule) p.set("rule", rule);
    if (kind) p.set("kind", kind);
    if (town.trim() && !MAPPED.includes(group)) p.set("town", town.trim());
    if (near.trim() && MAPPED.includes(group)) {
      p.set("near", near.trim());
      p.set("miles", radius);
    }
    has.forEach((h) => p.append("has", h));
    return p;
  }, [group, area, q, rule, kind, town, near, radius, has]);

  useEffect(() => setPage(1), [query]);
  useEffect(() => {
    if (!status?.available) return;
    const p = new URLSearchParams(query);
    p.set("page", String(page));
    setBusy(true);
    api.masterSearch(p).then(
      (d) => {
        setData(d);
        if (d.page === 1) setMapData(d); // The map only comes with the first page.
        setError("");
        setBusy(false);
      },
      (e) => { setError(e.message); setBusy(false); },
    );
  }, [query, page, status?.available]);

  const areas = (status?.groups?.[group] ?? []).filter((a) => a.area !== "counts");
  const totalOrgs = Object.values(status?.groups ?? {}).flat().reduce((n, a) => n + (a.organisations ?? 0), 0);
  const pages = data ? Math.max(1, Math.ceil(data.total / data.size)) : 1;
  const toggle = (h: string) => setHas((now) => (now.includes(h) ? now.filter((x) => x !== h) : [...now, h]));
  const search = (text: string) => { setTyped(text); setQ(text); };
  const mapped = MAPPED.includes(group);

  if (status && !status.available) {
    return (
      <>
        <div className="page-head"><div><h1>Find businesses</h1></div></div>
        <div className="card empty">
          The master database isn't on this computer yet. Build it with <code>python3 -m recon.master build</code>, or start the
          website with <code>--master</code> pointing at its folder.
        </div>
      </>
    );
  }

  return (
    <>
      <div className="hero">
        <div className="hero-top">
          <div>
            <h1>Find businesses</h1>
            <p className="lede">
              Search {totalOrgs ? fmt(totalOrgs) : "millions of"} organisations from {status?.sources?.length ?? "the"} open registers
              in the UK, the US and beyond. Every row says whether you may email it and where it came from.
            </p>
          </div>
          <button className="btn ghost small" onClick={() => setShowSources(!showSources)}>
            <Database size={14} /> {showSources ? "Hide" : "Show"} the sources
          </button>
        </div>
        <form className="hero-search" onSubmit={(e) => { e.preventDefault(); setQ(typed); setNear(nearTyped); }}>
          <div className="search big">
            <Search size={20} />
            <input className="input" value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="What kind of business? For example plumbers, or dental, dentist" />
          </div>
          <select className="input select" value={group} onChange={(e) => { setGroup(e.target.value); setArea(""); }}>
            {COUNTRIES.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
          </select>
          <select className="input select" value={area} onChange={(e) => setArea(e.target.value)}>
            <option value="">{group === "uk" ? "All of the UK" : group === "us" ? "Every state" : "Every country"}</option>
            {[...areas].sort((a, b) => areaName(group, a.area).localeCompare(areaName(group, b.area))).map((a) => (
              <option key={a.area} value={a.area}>{areaName(group, a.area)}</option>
            ))}
          </select>
          <button className="btn primary" type="submit"><Search size={16} /> Search</button>
          {mapped && (
            <>
              <div className="search">
                <Navigation size={16} />
                <input className="input" value={nearTyped} onChange={(e) => setNearTyped(e.target.value)}
                  placeholder={group === "uk" ? "Near a postcode or town (optional), for example BS1 4DJ or Bath" : "Near a ZIP code or town (optional), for example 78701 or Austin, TX"} />
              </div>
              <select className="input select" value={radius} onChange={(e) => setRadius(e.target.value)} aria-label="How far">
                {MILES.map((m) => <option key={m} value={m}>Within {m} {m === "1" ? "mile" : "miles"}</option>)}
              </select>
              {near && (
                <button className="btn ghost" type="button" onClick={() => { setNear(""); setNearTyped(""); }}>
                  <X size={15} /> Anywhere
                </button>
              )}
            </>
          )}
        </form>
        <div className="chips">
          {PICKS.map(([label, words]) => (
            <button key={label} className={`chip ${q === words ? "on" : ""}`} onClick={() => search(words)}>{label}</button>
          ))}
        </div>
      </div>

      {showSources && status?.sources && (
        <div className="card" style={{ marginBottom: 20 }}>
          <h3 style={{ marginBottom: 10 }}>{status.sources.length} open sources</h3>
          <div className="table-wrap" style={{ maxHeight: 360 }}>
            <table>
              <thead><tr><th>Source</th><th>Country</th><th>Records</th><th>With email</th><th>Licence</th></tr></thead>
              <tbody>
                {status.sources.map((s) => (
                  <tr key={s.name} onClick={() => window.open(s.url, "_blank")}>
                    <td><div className="name">{s.title}</div><div className="cell-sub">{s.name}</div></td>
                    <td>{s.country}</td>
                    <td>{fmt(Number(s.records))}</td>
                    <td>{fmt(Number(s.with_email))}</td>
                    <td className="small muted">{s.licence}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {error && <div className="notice bad" style={{ marginBottom: 16 }}>{error}</div>}

      {data && (
        <>
          <div className="stats" style={{ marginBottom: 18, opacity: busy ? 0.5 : 1 }}>
            <div className="stat"><b>{fmt(data.total)}</b><span>organisations found</span></div>
            <div className="stat green"><b>{fmt(data.may_email)}</b><span>may be emailed ({pct(data.may_email, data.total)})</span></div>
            <div className="stat amber"><b>{fmt(data.total - data.may_email)}</b><span>post only</span></div>
            <div className="stat blue"><b>{fmt(data.with_email)}</b><span>have an email</span></div>
            <div className="stat pink"><b>{fmt(data.with_phone)}</b><span>have a phone</span></div>
            <div className="stat"><b>{fmt(data.with_website)}</b><span>have a website</span></div>
          </div>

          {mapped && mapData && (
            <div className="card stack" style={{ marginBottom: 18 }}>
              <div className="spread">
                <div>
                  <h3>
                    {mapData.circle ? `Within ${mapData.circle.miles} ${mapData.circle.miles === 1 ? "mile" : "miles"} of ${mapData.circle.label}` : "On the map"}
                  </h3>
                  <p className="small muted">
                    {mapData.placed > mapData.points.length
                      ? `Showing the best ${fmt(mapData.points.length)} of ${fmt(mapData.placed)}, those you may email first. Pick a postcode or town above to see every one nearby.`
                      : `${fmt(mapData.placed)} of ${fmt(mapData.total)} have a postcode we can place.`}
                    {" "}Each pin sits at the middle of the postcode. Click one for the phone, email and website.
                  </p>
                </div>
                <button className="btn ghost small" onClick={() => setShowMap(!showMap)}>
                  <MapIcon size={14} /> {showMap ? "Hide" : "Show"} the map
                </button>
              </div>
              {showMap && <ResultsMap data={mapData} group={group} onOpen={setOpen} />}
            </div>
          )}

          <div className="two-up" style={{ marginBottom: 18 }}>
            <div className="card stack">
              <h3>Where they are</h3>
              <div className="stack" style={{ gap: 8 }}>
                {data.by_area.slice(0, 8).map((a) => (
                  <button key={a.area} className="btn ghost bar-row" onClick={() => setArea(area === a.area ? "" : a.area)}>
                    <span style={{ color: area === a.area ? "var(--text)" : undefined }}>{areaName(group, a.area)}</span>
                    <span className="bar" style={{ alignSelf: "center" }}>
                      <i style={{ width: pct(a.count, data.by_area[0].count), background: "linear-gradient(90deg, var(--accent), var(--accent-2))" }} />
                    </span>
                    <span className="small" style={{ textAlign: "right" }}>{fmt(a.count)}</span>
                  </button>
                ))}
                {!data.by_area.length && <span className="faint small">Nothing found.</span>}
              </div>
            </div>
            <div className="card stack">
              <h3>Which registers they come from</h3>
              <div className="chips">
                {data.by_source.map((s) => (
                  <span key={s.source} className="badge grey" style={{ padding: "4px 10px" }}>{s.source} <b style={{ marginLeft: 4 }}>{fmt(s.count)}</b></span>
                ))}
              </div>
              {data.total > 0 && data.with_email < data.total / 10 && (
                <p className="small muted">
                  Most of these come from registers that list an address but no email, such as Companies House. They're ready for post,
                  or for Recon's email finder to look up on their websites.
                </p>
              )}
            </div>
          </div>

          <div className="stack" style={{ marginBottom: 14 }}>
            <div className="row">
              <div className="chips">
                {RULES.map(([v, label]) => (
                  <button key={label} className={`chip ${rule === v ? "on" : ""}`} onClick={() => setRule(v)}>{label}</button>
                ))}
              </div>
              <span className="faint">|</span>
              <div className="chips">
                {HAS.map(([v, label]) => (
                  <button key={v} className={`chip ${has.includes(v) ? "on" : ""}`} onClick={() => toggle(v)}>{label}</button>
                ))}
              </div>
            </div>
            <div className="row">
              <select className="input select" style={{ width: 240 }} value={kind} onChange={(e) => setKind(e.target.value)}>
                <option value="">Every kind of organisation</option>
                {kinds.map((k) => <option key={k.kind} value={k.kind}>{k.kind} ({fmt(k.count)})</option>)}
              </select>
              {!mapped && (
                <div className="search" style={{ width: 260 }}>
                  <MapPin size={16} />
                  <input className="input" placeholder="Town or postcode start" value={town} onChange={(e) => setTown(e.target.value)} />
                </div>
              )}
              <div style={{ flex: 1 }} />
              <a className="btn primary" href={api.masterExportUrl(query)}>
                <Download size={15} /> Download {fmt(Math.min(data.total, 1000000))} as a spreadsheet
              </a>
            </div>
          </div>

          <div className="table-wrap" style={{ opacity: busy ? 0.5 : 1 }}>
            <table>
              <thead>
                <tr><th>Organisation</th><th>Where</th>{data.circle && <th>Distance</th>}<th>May we email?</th><th>Email</th><th>Phone</th><th>Found in</th></tr>
              </thead>
              <tbody>
                {data.rows.map((row, i) => {
                  const emails = splitList(row.emails);
                  const phones = splitList(row.phones);
                  return (
                    <tr key={`${row.name}-${row.postcode}-${i}`} onClick={() => setOpen(row)}>
                      <td>
                        <div className="name">{row.name}</div>
                        <div className="cell-sub">{row.kind}</div>
                      </td>
                      <td>
                        {row.town || <span className="faint">-</span>}
                        <div className="cell-sub">{[row.postcode, areaName(group, row.area)].filter(Boolean).join(" · ")}</div>
                      </td>
                      {data.circle && <td style={{ whiteSpace: "nowrap" }}>{row.miles !== "" ? miles(row.miles) : "-"}</td>}
                      <td><RuleBadge rule={row.can_email} /></td>
                      <td>
                        {emails[0] ? <span style={{ wordBreak: "break-all" }}>{emails[0]}</span> : <span className="faint">None listed</span>}
                        {emails.length > 1 && <div className="cell-sub">+{emails.length - 1} more</div>}
                      </td>
                      <td style={{ whiteSpace: "nowrap" }}>{phones[0] || <span className="faint">-</span>}</td>
                      <td className="small muted">{row.sources.split(";").map((s) => s.trim()).filter(Boolean).join(", ")}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {data.rows.length === 0 && <div className="empty">Nothing matches. Try fewer filters or another word.</div>}
          </div>
          <div className="pager">
            <span>Page {fmt(page)} of {fmt(pages)}</span>
            <button className="btn small" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button>
            <button className="btn small" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</button>
          </div>
        </>
      )}
      {!data && !error && <div className="empty">Searching…</div>}
      {open && <Details row={open} group={group} onClose={() => setOpen(null)} />}
    </>
  );
}
