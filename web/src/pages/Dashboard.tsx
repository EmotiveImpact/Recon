import { useEffect, useState } from "react";
import { ArrowDownRight, ArrowRight, ArrowUpRight, Database, Map as MapIcon, PoundSterling, Search, Sparkles } from "lucide-react";
import { api, type Overview, type AreaCounts, type Growth, type SectorTree } from "../api";
import { fmt, go, pct } from "../ui";

// The front page: what's in Recon's database at a glance, and where to go next.

const AREA_NAMES: Record<string, string> = {
  england: "England", scotland: "Scotland", wales: "Wales", "northern-ireland": "Northern Ireland",
  "crown-dependencies": "Channel Islands and Isle of Man", unknown: "Place not known",
  ca: "California", tx: "Texas", ny: "New York", fl: "Florida", il: "Illinois", pa: "Pennsylvania", oh: "Ohio",
  ga: "Georgia", nc: "North Carolina", mi: "Michigan", nj: "New Jersey", va: "Virginia", wa: "Washington",
  az: "Arizona", ma: "Massachusetts", tn: "Tennessee", in: "Indiana", mo: "Missouri", md: "Maryland",
  wi: "Wisconsin", co: "Colorado", mn: "Minnesota", sc: "South Carolina", al: "Alabama", la: "Louisiana",
  ky: "Kentucky", or: "Oregon", ok: "Oklahoma", ct: "Connecticut", ut: "Utah", ia: "Iowa", nv: "Nevada",
  ar: "Arkansas", ms: "Mississippi", ks: "Kansas", nm: "New Mexico", ne: "Nebraska", id: "Idaho",
  wv: "West Virginia", hi: "Hawaii", nh: "New Hampshire", me: "Maine", mt: "Montana", ri: "Rhode Island",
  de: "Delaware", sd: "South Dakota", nd: "North Dakota", ak: "Alaska", dc: "District of Columbia",
  vt: "Vermont", wy: "Wyoming", pr: "Puerto Rico",
};
const areaName = (a: string) => AREA_NAMES[a] ?? a.replaceAll("-", " ");
const tradeName = (t: string) => (t.charAt(0).toUpperCase() + t.slice(1)).replaceAll("-", " ");

const SCOPES: [string, string][] = [["all", "UK and US"], ["uk", "🇬🇧 UK"], ["us", "🇺🇸 US"]];

function short(n: number) {
  if (n >= 1e6) return `${(n / 1e6).toFixed(n >= 1e7 ? 1 : 2)}m`;
  if (n >= 1e4) return `${Math.round(n / 1e3)}k`;
  return fmt(n);
}

// One cell of the headline strip: a figure, what it is, and a small note or change.
function Stat({ label, value, note, change }: { label: string; value: string; note?: string; change?: number }) {
  return (
    <div className="stat-cell">
      <span className="stat-label">{label}</span>
      <b>{value}</b>
      {change !== undefined ? (
        <span className="stat-note">
          <span className={`delta ${change >= 0 ? "up" : "down"}`}>
            {change >= 0 ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}{Math.abs(change).toFixed(1)}%
          </span>{" "}{note}
        </span>
      ) : <span className="stat-note">{note}</span>}
    </div>
  );
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const monthName = (m: string, year = false) => `${MONTHS[Number(m.slice(5, 7)) - 1]}${year ? ` ${m.slice(0, 4)}` : ""}`;

// New companies each month as a soft area, with the month under the pointer picked out.
function AreaChart({ months }: { months: { month: string; count: number }[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const w = 720, h = 220, padL = 44, padB = 26, padT = 10;
  const top = Math.max(1, ...months.map((m) => m.count));
  const step = Math.pow(10, Math.floor(Math.log10(top)));
  const ceil = Math.ceil(top / step) * step;
  const x = (i: number) => padL + (i / Math.max(1, months.length - 1)) * (w - padL - 8);
  const y = (v: number) => padT + (1 - v / ceil) * (h - padT - padB);
  const line = months.map((m, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(m.count).toFixed(1)}`).join("");
  const at = hover ?? months.length - 1;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => ceil * f);
  return (
    <svg className="area-chart" viewBox={`0 0 ${w} ${h}`} role="img" aria-label="New companies each month"
      onMouseLeave={() => setHover(null)}
      onMouseMove={(e) => {
        const r = e.currentTarget.getBoundingClientRect();
        const px = ((e.clientX - r.left) / r.width) * w;
        setHover(Math.max(0, Math.min(months.length - 1, Math.round(((px - padL) / (w - padL - 8)) * (months.length - 1)))));
      }}>
      <defs>
        <linearGradient id="area-fill" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor="#ffffff" stopOpacity="0.14" />
          <stop offset="1" stopColor="#ffffff" stopOpacity="0" />
        </linearGradient>
      </defs>
      {ticks.map((t) => (
        <g key={t}>
          <line x1={padL} x2={w - 8} y1={y(t)} y2={y(t)} className="grid" />
          <text x={padL - 8} y={y(t) + 4} textAnchor="end" className="axis">{short(t)}</text>
        </g>
      ))}
      <path d={`${line}L${x(months.length - 1)},${y(0)}L${x(0)},${y(0)}Z`} fill="url(#area-fill)" />
      <path d={line} className="area-line" />
      {months.map((m, i) => (i % 4 === 0 || i === months.length - 1) && (
        <text key={m.month} x={x(i)} y={h - 6} textAnchor="middle" className="axis">{monthName(m.month)}</text>
      ))}
      <line x1={x(at)} x2={x(at)} y1={padT} y2={y(0)} className="cursor" />
      <circle cx={x(at)} cy={y(months[at].count)} r="4" className="dot" />
      <g transform={`translate(${Math.min(x(at) + 10, w - 150)}, ${padT + 4})`}>
        <rect width="140" height="44" rx="8" className="tip-box" />
        <text x="10" y="18" className="tip-sub">{monthName(months[at].month, true)}</text>
        <text x="10" y="35" className="tip-main">{fmt(months[at].count)} new</text>
      </g>
    </svg>
  );
}

// A ring of short ticks, lit up to the share given.
function Gauge({ part, whole, label }: { part: number; whole: number; label: string }) {
  const n = 48, share = whole ? part / whole : 0;
  return (
    <div className="gauge">
      <svg viewBox="0 0 200 200" role="img" aria-label={`${pct(part, whole)} ${label}`}>
        {Array.from({ length: n }, (_, i) => {
          const a = (-225 + (i / (n - 1)) * 270) * (Math.PI / 180);
          const r1 = 70, r2 = i / (n - 1) <= share ? 92 : 84;
          return <line key={i} x1={100 + r1 * Math.cos(a)} y1={100 + r1 * Math.sin(a)} x2={100 + r2 * Math.cos(a)} y2={100 + r2 * Math.sin(a)}
            className={i / (n - 1) <= share ? "on" : ""} />;
        })}
      </svg>
      <div className="gauge-mid">
        <span className="stat-label">{label}</span>
        <b>{pct(part, whole)}</b>
        <span className="stat-note">{fmt(part)}</span>
      </div>
    </div>
  );
}

// A row of thin bars, lit up to the share given.
function TickMeter({ share }: { share: number }) {
  const n = 60;
  return (
    <div className="tick-meter">
      {Array.from({ length: n }, (_, i) => <i key={i} className={i / n < share ? "on" : ""} />)}
    </div>
  );
}

// Horizontal bars, one row per item; the bar shows the total and its darker
// inner part the share that may be emailed.
function Bars({ rows, onPick }: {
  rows: { key: string; label: string; total: number; part: number; partLabel: string }[];
  onPick?: (key: string) => void;
}) {
  const top = Math.max(1, ...rows.map((r) => r.total));
  return (
    <div className="hbars">
      {rows.map((r) => (
        <button key={r.key} className="hbar" onClick={() => onPick?.(r.key)} disabled={!onPick}
          title={`${r.label}: ${fmt(r.total)} in all, ${fmt(r.part)} ${r.partLabel}`}>
          <span className="hbar-label">{r.label}</span>
          <span className="hbar-track">
            <i style={{ width: `${(r.total / top) * 100}%` }}>
              <em style={{ width: pct(r.part, r.total) }} />
            </i>
          </span>
          <span className="hbar-value">{short(r.total)}</span>
        </button>
      ))}
    </div>
  );
}

export default function Dashboard() {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState("");
  const [scope, setScope] = useState("all");
  const [typed, setTyped] = useState("");
  const [place, setPlace] = useState("");
  const [growth, setGrowth] = useState<Growth | null>(null);
  const [tree, setTree] = useState<SectorTree | null>(null);

  useEffect(() => {
    api.overview().then(setData, (e) => setError(e.message));
    api.growth().then(setGrowth, () => setGrowth(null));
    api.sectors("uk").then(setTree, () => setTree(null));
  }, []);

  if (error) return <div className="notice bad">{error}</div>;
  if (!data) return <div className="empty">Loading the dashboard…</div>;
  if (!data.available) {
    return <div className="card empty">The master database isn't on this computer yet, so there's nothing to show.</div>;
  }

  const countries = data.countries ?? {};
  const groups = scope === "all" ? ["uk", "us"] : [scope];
  const sum = (key: keyof AreaCounts) => groups.reduce((n, g) => n + ((countries[g]?.totals?.[key as never] as number) ?? 0), 0);
  const total = sum("organisations");
  const areas = groups.flatMap((g) => (countries[g]?.areas ?? []).map((a) => ({ ...a, group: g }))).filter((a) => a.area !== "unknown");
  areas.sort((a, b) => b.organisations - a.organisations);
  const trades = [...(data.trades ?? [])].sort((a, b) => b.businesses - a.businesses);
  const tradeTotal = trades.reduce((n, t) => n + t.businesses, 0);
  const sources = [...(data.sources ?? [])].filter((s) => groups.some((g) => (g === "uk" ? "GB" : "US") === s.country))
    .sort((a, b) => b.records - a.records);
  const money = data.money;

  const change = growth?.available && growth.prior_30 ? ((growth.last_30! - growth.prior_30) / growth.prior_30) * 100 : undefined;
  const months = growth?.months ?? [];
  const sectors = [...(tree?.sectors ?? [])].sort((a, b) => b.count - a.count);
  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
  const busiest = [...months].sort((a, b) => b.count - a.count)[0];
  const bestArea = [...areas].sort((a, b) => b.may_email - a.may_email)[0];

  // Plain sentences drawn from the figures above, for a quick read.
  const insights: string[] = [];
  if (change !== undefined) {
    insights.push(`${fmt(growth!.last_30)} new UK companies registered in the last 30 days, ${change >= 0 ? "up" : "down"} ${Math.abs(change).toFixed(1)}% on the 30 days before.`);
  }
  if (sectors[0]) insights.push(`${sectors[0].name} is the biggest UK sector, with ${short(sectors[0].count)} organisations.`);
  if (bestArea) insights.push(`${areaName(bestArea.area)} has the most organisations you may email: ${short(bestArea.may_email)}.`);
  if (busiest) insights.push(`The busiest month for new companies was ${monthName(busiest.month, true)}, with ${fmt(busiest.count)}.`);

  return (
    <div className="dash">
      <div className="dash-head">
        <div>
          <h1>{greeting}</h1>
          <p className="lede">
            {fmt((countries.uk?.totals.organisations ?? 0) + (countries.us?.totals.organisations ?? 0))} organisations from{" "}
            {data.sources?.length ?? 0} open registers.
          </p>
        </div>
        <div className="seg">
          {SCOPES.map(([v, label]) => (
            <button key={v} className={scope === v ? "on" : ""} onClick={() => setScope(v)}>{label}</button>
          ))}
        </div>
      </div>

      <div className="quick">
        <form className="quick-card" onSubmit={(e) => { e.preventDefault(); go(`/find?q=${encodeURIComponent(typed)}`); }}>
          <span className="quick-icon"><Search size={18} /></span>
          <div className="quick-body">
            <b>Find a kind of business</b>
            <input className="input" placeholder="For example dentists, or care homes" value={typed} onChange={(e) => setTyped(e.target.value)} />
          </div>
          <button className="btn primary" type="submit"><ArrowRight size={16} /></button>
        </form>
        <form className="quick-card" onSubmit={(e) => { e.preventDefault(); go(`/map?near=${encodeURIComponent(place)}`); }}>
          <span className="quick-icon teal"><MapIcon size={18} /></span>
          <div className="quick-body">
            <b>See businesses on a map</b>
            <input className="input" placeholder="A postcode or town, for example BN1 or Leeds" value={place} onChange={(e) => setPlace(e.target.value)} />
          </div>
          <button className="btn go" type="submit"><ArrowRight size={16} /></button>
        </form>
      </div>

      <div className="overview">
        <section className="card calm overview-main">
          <div className="stat-strip">
            <Stat label="Organisations" value={short(total)} note={scope === "all" ? "UK and US" : scope === "uk" ? "in the UK" : "in the US"} />
            <Stat label="Have a phone" value={short(sum("with_phone"))} note={`${pct(sum("with_phone"), total)} of all`} />
            <Stat label="Have an email" value={short(sum("with_email"))} note={`${pct(sum("with_email"), total)} of all`} />
            {change !== undefined && (
              <Stat label="New UK companies, 30 days" value={fmt(growth!.last_30)} change={change} note="vs the 30 days before" />
            )}
          </div>
          {months.length > 1 && (
            <div className="chart-block">
              <div className="chart-head">
                <div>
                  <b className="chart-big">{short(months[months.length - 1].count)}</b>
                  <span className="stat-label">New UK companies in {monthName(months[months.length - 1].month, true)}</span>
                </div>
                <span className="stat-note">Companies House, companies still open today</span>
              </div>
              <AreaChart months={months} />
            </div>
          )}
        </section>

        <section className="card calm overview-side">
          <Gauge part={sum("may_email")} whole={total} label="May be emailed" />
          <p className="small muted center">Registered companies and similar. Sole traders are phone or post only.</p>
          <div className="side-split">
            <span className="stat-label">Have a website</span>
            <div className="spread"><b className="chart-big">{short(sum("with_website"))}</b><span className="stat-note">{pct(sum("with_website"), total)}</span></div>
            <TickMeter share={total ? sum("with_website") / total : 0} />
          </div>
        </section>

        {insights.length > 0 && (
          <section className="card calm insights">
            <h3><Sparkles size={15} /> What stands out</h3>
            <p className="insight-lead">{insights[0]}</p>
            <ul>{insights.slice(1).map((t) => <li key={t}>{t}</li>)}</ul>
          </section>
        )}

        {sectors.length > 0 && (
          <section className="card calm span-2">
            <div className="panel-head">
              <div>
                <h3>UK sectors</h3>
                <p className="small muted">Darker part: may be emailed. Click one to see it across the country.</p>
              </div>
              <button className="btn small" onClick={() => go("/map")}><MapIcon size={14} /> Open the map</button>
            </div>
            <Bars
              rows={sectors.map((x) => ({ key: x.sector, label: x.name, total: x.count, part: x.may_email, partLabel: "may be emailed" }))}
              onPick={(key) => go(`/map?source=all&group=uk&sector=${key}`)}
            />
          </section>
        )}
      </div>

      <div className="dash-grid">
        <section className="card panel span-2">
          <div className="panel-head">
            <div>
              <h3>Where they are</h3>
              <p className="small muted">Darker part: may be emailed. Click a place to search it.</p>
            </div>
          </div>
          <Bars
            rows={areas.slice(0, 12).map((a) => ({ key: `${a.group}/${a.area}`, label: areaName(a.area), total: a.organisations, part: a.may_email, partLabel: "may be emailed" }))}
            onPick={(key) => { const [g, a] = key.split("/"); go(`/find?group=${g}&area=${a}&q=`); }}
          />
        </section>

        <section className="card panel">
          <div className="panel-head">
            <div>
              <h3><PoundSterling size={15} style={{ verticalAlign: -2 }} /> Who publishes their money</h3>
              <p className="small muted">From the accounts each UK trade company files at Companies House ({fmt(tradeTotal)} trade businesses).</p>
            </div>
          </div>
          {money?.available && money.registered ? (
            <>
              <div className="donut-wrap">
                <Donut part={money.with_net_assets ?? 0} whole={money.registered} />
                <div>
                  <b className="big-num">{fmt(money.with_net_assets)}</b>
                  <div className="small muted">of {fmt(money.registered)} registered companies show what they're worth</div>
                </div>
              </div>
              <div className="money-facts">
                <div><b>{fmt(money.with_staff)}</b><span>give a staff count</span></div>
                <div><b>{fmt(money.publishes_turnover)}</b><span>publish their turnover</span></div>
              </div>
              <div className="section-title" style={{ marginTop: 4 }}>Company size (click to map)</div>
              <Bars
                rows={sizeRows(money.size_bands ?? []).map((b) => ({ key: b.key, label: b.label, total: b.count, part: 0, partLabel: "" }))}
                onPick={(key) => key && go(`/map?source=trades&size=${key}`)}
              />
            </>
          ) : (
            <div className="soon">
              <PoundSterling size={22} />
              <p>Turnover, staff numbers and company size aren't in the trade lists on this computer yet.</p>
            </div>
          )}
        </section>

        <section className="card panel span-3">
          <div className="panel-head">
            <div>
              <h3><Database size={15} style={{ verticalAlign: -2 }} /> Biggest sources</h3>
              <p className="small muted">Every source is open data. Darker part: records with an email.</p>
            </div>
            <button className="btn small" onClick={() => go("/find")}>Search them all</button>
          </div>
          <div className="two-col">
            <Bars rows={sources.slice(0, 8).map((s) => ({ key: s.name, label: s.title, total: s.records, part: s.with_email, partLabel: "with an email" }))} />
            <Bars rows={sources.slice(8, 16).map((s) => ({ key: s.name, label: s.title, total: s.records, part: s.with_email, partLabel: "with an email" }))} />
          </div>
        </section>
      </div>
    </div>
  );
}

// The trade lists' size bands, folded into the ones worth showing.
function sizeRows(bands: { band: string; count: number }[]) {
  const count = (test: (b: string) => boolean) => bands.filter((b) => test(b.band)).reduce((n, b) => n + b.count, 0);
  return [
    { key: "micro", label: "Micro (up to 10 staff)", count: count((b) => b.startsWith("micro")) },
    { key: "small", label: "Small (up to 50)", count: count((b) => b.startsWith("small")) },
    { key: "medium-large", label: "Medium or large", count: count((b) => b.startsWith("medium") || b.startsWith("large")) },
    { key: "", label: "Dormant or no accounts yet", count: count((b) => b.startsWith("dormant") || b.startsWith("no accounts")) },
  ];
}

function Donut({ part, whole }: { part: number; whole: number }) {
  const r = 34;
  const c = 2 * Math.PI * r;
  const share = whole ? part / whole : 0;
  return (
    <svg width="92" height="92" viewBox="0 0 92 92" role="img" aria-label={`${pct(part, whole)} publish their turnover`}>
      <circle cx="46" cy="46" r={r} fill="none" stroke="var(--panel-2)" strokeWidth="10" />
      <circle cx="46" cy="46" r={r} fill="none" stroke="var(--green)" strokeWidth="10" strokeLinecap="round"
        strokeDasharray={`${c * share} ${c}`} transform="rotate(-90 46 46)" />
      <text x="46" y="51" textAnchor="middle" fontSize="15" fontWeight="700" fill="var(--text)">{pct(part, whole)}</text>
    </svg>
  );
}
