import { useEffect, useState } from "react";
import { ArrowRight, Building2, Database, Globe, Mail, MailCheck, Map as MapIcon, Phone, PoundSterling, Search } from "lucide-react";
import { api, type Overview, type AreaCounts } from "../api";
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

function Kpi({ icon: Icon, label, value, of, tone, note }: {
  icon: typeof Mail; label: string; value: number; of?: number; tone: string; note?: string;
}) {
  return (
    <div className={`kpi ${tone}`}>
      <div className="kpi-top">
        <span className="kpi-icon"><Icon size={16} /></span>
        <span>{label}</span>
      </div>
      <b title={fmt(value)}>{short(value)}</b>
      {of ? (
        <>
          <div className="meter"><i style={{ width: pct(value, of) }} /></div>
          <span className="kpi-note">{pct(value, of)} of all {note ?? ""}</span>
        </>
      ) : <span className="kpi-note">{note}</span>}
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

  useEffect(() => {
    api.overview().then(setData, (e) => setError(e.message));
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

  const funnel = [
    { label: "Organisations", value: total },
    { label: "Have a phone", value: sum("with_phone") },
    { label: "Have an email", value: sum("with_email") },
    { label: "May be emailed", value: sum("may_email") },
  ];

  return (
    <div className="dash">
      <div className="dash-head">
        <div>
          <div className="eyebrow">Recon dashboard</div>
          <h1>Everything Recon has found</h1>
          <p className="lede">
            {fmt((countries.uk?.totals.organisations ?? 0) + (countries.us?.totals.organisations ?? 0))} organisations from{" "}
            {data.sources?.length ?? 0} open registers. Pick a trade or a place to start.
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

      <div className="kpis">
        <Kpi icon={Building2} label="Organisations" value={total} tone="violet" note={scope === "all" ? "UK and US" : scope === "uk" ? "in the UK" : "in the US"} />
        <Kpi icon={Phone} label="Have a phone" value={sum("with_phone")} of={total} tone="pink" />
        <Kpi icon={Globe} label="Have a website" value={sum("with_website")} of={total} tone="cyan" />
        <Kpi icon={Mail} label="Have an email" value={sum("with_email")} of={total} tone="blue" />
        <Kpi icon={MailCheck} label="May be emailed" value={sum("may_email")} of={total} tone="green" />
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
          <div className="panel-head"><h3>From found to contactable</h3></div>
          <div className="funnel">
            {funnel.map((f, i) => (
              <div key={f.label} className="funnel-row" title={`${f.label}: ${fmt(f.value)}`}>
                <div className="funnel-bar" style={{ width: `${Math.max(4, (f.value / Math.max(1, total)) * 100)}%`, opacity: 1 - i * 0.12 }} />
                <div className="funnel-text"><span>{f.label}</span><b>{fmt(f.value)}</b></div>
              </div>
            ))}
          </div>
          <p className="small muted">
            "May be emailed" means a registered company or similar. Sole traders and partnerships are post or phone only.
          </p>
        </section>

        <section className="card panel span-2">
          <div className="panel-head">
            <div>
              <h3>UK trades with full contact details</h3>
              <p className="small muted">{fmt(tradeTotal)} businesses checked one by one, each with a map position. Click one to see it on the map.</p>
            </div>
            <button className="btn small" onClick={() => go("/map")}><MapIcon size={14} /> Open the map</button>
          </div>
          <div className="trade-table">
            <div className="trade-row head"><span>Trade</span><span>Businesses</span><span>Email</span><span>May email</span><span /></div>
            {trades.map((t) => (
              <button key={t.trade} className="trade-row" onClick={() => go(`/map?trade=${t.trade}`)}>
                <span className="name">{tradeName(t.trade)}</span>
                <span>
                  <span className="mini-bar"><i style={{ width: `${(t.businesses / trades[0].businesses) * 100}%` }} /></span>
                  {fmt(t.businesses)}
                </span>
                <span>{pct(t["with email"], t.businesses)}</span>
                <span className="green-text">{fmt(t["may email and has email"] ?? t["may email"])}</span>
                <ArrowRight size={14} className="faint" />
              </button>
            ))}
          </div>
        </section>

        <section className="card panel">
          <div className="panel-head">
            <div>
              <h3><PoundSterling size={15} style={{ verticalAlign: -2 }} /> Who publishes their money</h3>
              <p className="small muted">From the accounts each company files at Companies House.</p>
            </div>
          </div>
          {money?.available ? (
            <>
              <div className="donut-wrap">
                <Donut part={money.publishes_turnover ?? 0} whole={money.total ?? 0} />
                <div>
                  <b className="big-num">{fmt(money.publishes_turnover)}</b>
                  <div className="small muted">of {fmt(money.total)} trade businesses publish their turnover</div>
                </div>
              </div>
              <div className="section-title" style={{ marginTop: 6 }}>By size</div>
              <Bars rows={(money.size_bands ?? []).map((b) => ({ key: b.band, label: b.band, total: b.count, part: 0, partLabel: "" }))} />
            </>
          ) : (
            <div className="soon">
              <PoundSterling size={22} />
              <p>Turnover, staff numbers and company size are being added to the trade lists now. They'll appear here as soon as they land.</p>
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
