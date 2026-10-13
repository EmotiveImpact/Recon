import { useEffect, useMemo, useState } from "react";
import { ChevronDown, ChevronRight, Loader2, Plus, Save, Search, Sparkles, Trash2, X } from "lucide-react";
import { api, type Project, type Sector, type Setup, type TargetList } from "../api";
import { LIBRARY } from "../library";
import { fmt, go, toast } from "../ui";
import categoryData from "../categories.json";

type CategoryFile = { release: string; counts: Record<string, Record<string, number>> };
const CATEGORIES = categoryData as CategoryFile;

const empty = (): Sector => ({ overture: [], osm: [], sic: [] });

function Tags({ values, kind, onRemove, stale }: { values: string[]; kind?: string; onRemove: (v: string) => void; stale?: (v: string) => boolean }) {
  return (
    <div className="chips">
      {values.map((v) => (
        <span key={v} className={`tag ${kind ?? ""} ${stale?.(v) ? "stale" : ""}`}
          title={stale?.(v) ? `Overture's ${CATEGORIES.release} list has no "${v}", so it finds nothing. It may have been renamed.` : undefined}>
          {v}
          <button onClick={() => onRemove(v)} aria-label={`Remove ${v}`}><X size={12} /></button>
        </span>
      ))}
    </div>
  );
}

function CategoryPicker({ country, chosen, onAdd }: { country: string; chosen: string[]; onAdd: (c: string) => void }) {
  const [text, setText] = useState("");
  const [focus, setFocus] = useState(false);
  const [live, setLive] = useState<{ category: string; places: number }[] | null>(null);
  const [busy, setBusy] = useState(false);
  const counts = CATEGORIES.counts[country] ?? CATEGORIES.counts.GB ?? {};
  const matches = useMemo(() => {
    const words = text.toLowerCase().split(/\s+/).filter(Boolean);
    if (!words.length) return [];
    return Object.entries(counts)
      .filter(([c]) => !chosen.includes(c) && words.some((w) => c.replaceAll("_", " ").includes(w)))
      .sort((a, b) => b[1] - a[1])
      .slice(0, 12);
  }, [text, counts, chosen]);
  const searchLive = async () => {
    setBusy(true);
    try {
      setLive(await api.categories(country, text.split(/[\s,]+/)));
    } catch (e) {
      toast((e as Error).message);
    }
    setBusy(false);
  };
  const add = (c: string) => {
    onAdd(c);
    setText("");
  };
  return (
    <div className="stack" style={{ gap: 8 }}>
      <div className="add-inline">
        <div className="suggest">
          <input className="input" placeholder="Type a word, such as dentist or yoga" value={text}
            onChange={(e) => { setText(e.target.value); setLive(null); }}
            onFocus={() => setFocus(true)} onBlur={() => setTimeout(() => setFocus(false), 150)}
            onKeyDown={(e) => { if (e.key === "Enter" && matches[0]) add(matches[0][0]); }} />
          {focus && matches.length > 0 && (
            <div className="suggest-list">
              {matches.map(([c, n]) => (
                <button key={c} onMouseDown={() => add(c)}>
                  <span>{c.replaceAll("_", " ")}</span>
                  <span className="faint">{fmt(n)} places</span>
                </button>
              ))}
            </div>
          )}
        </div>
        <button className="btn small" disabled={!text.trim() || busy} onClick={searchLive}
          title="Ask Overture's newest data directly. Needs the internet and takes a minute.">
          {busy ? <Loader2 size={13} className="spin" /> : <Search size={13} />} Search live
        </button>
      </div>
      {text && !matches.length && !live && (
        <div className="faint small">Nothing new matches in the saved list. Try another word, or Search live.</div>
      )}
      {live && (
        <div className="chips">
          {live.length ? live.slice(0, 20).map((c) => (
            <button key={c.category} className="chip" onClick={() => add(c.category)}>
              <Plus size={12} /> {c.category.replaceAll("_", " ")} <span className="faint">{fmt(c.places)}</span>
            </button>
          )) : <span className="faint small">Overture has no category with those words.</span>}
        </div>
      )}
    </div>
  );
}

function SectorCard({ name, sector, country, onRename, onChange, onDelete }: {
  name: string; sector: Sector; country: string;
  onRename: (n: string) => void; onChange: (s: Sector) => void; onDelete: () => void;
}) {
  const [open, setOpen] = useState(true);
  const [title, setTitle] = useState(name);
  const [osm, setOsm] = useState("");
  const [sic, setSic] = useState("");
  const counts = CATEGORIES.counts[country] ?? {};
  const known = sector.overture.reduce((n, c) => n + (counts[c] ?? 0), 0);
  const stale = sector.overture.filter((c) => !(c in counts));
  const addOsm = () => {
    const [k, v] = osm.split("=").map((s) => s.trim());
    if (k && v && !sector.osm.some(([a, b]) => a === k && b === v)) onChange({ ...sector, osm: [...sector.osm, [k, v]] });
    setOsm("");
  };
  const addSic = () => {
    const codes = sic.split(/[\s,]+/).filter((c) => /^\d{4,5}$/.test(c) && !sector.sic.includes(c));
    if (codes.length) onChange({ ...sector, sic: [...sector.sic, ...codes] });
    setSic("");
  };
  return (
    <div className="sector">
      <div className="sector-head">
        <button className="btn ghost small" onClick={() => setOpen(!open)} aria-label="Open or close">
          {open ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        </button>
        <input value={title} onChange={(e) => setTitle(e.target.value)} onBlur={() => title.trim() && title !== name ? onRename(title.trim()) : setTitle(name)} />
        {known > 0 && <span className="badge grey" title={`Places in Overture ${CATEGORIES.release} with these categories`}>about {fmt(known)} on the map</span>}
        <button className="btn ghost small danger" onClick={onDelete} aria-label="Remove this kind of business"><Trash2 size={15} /></button>
      </div>
      {open && (
        <div className="sector-body">
          <div className="sector-part">
            <div>Overture Maps categories (the main source)</div>
            <Tags values={sector.overture} stale={(c) => !(c in counts)} onRemove={(v) => onChange({ ...sector, overture: sector.overture.filter((x) => x !== v) })} />
            {stale.length > 0 && (
              <div className="notice warn small">
                {stale.length === 1 ? "One category is" : `${stale.length} categories are`} not in Overture's newest list
                ({stale.join(", ")}), so {stale.length === 1 ? "it finds" : "they find"} nothing. Overture renames categories now and then: search for the new name below.
              </div>
            )}
            <CategoryPicker country={country} chosen={sector.overture} onAdd={(c) => onChange({ ...sector, overture: [...sector.overture, c] })} />
          </div>
          <div className="sector-part">
            <div>OpenStreetMap tags, written key=value (fills gaps)</div>
            <Tags kind="osm" values={sector.osm.map(([k, v]) => `${k}=${v}`)}
              onRemove={(t) => onChange({ ...sector, osm: sector.osm.filter(([k, v]) => `${k}=${v}` !== t) })} />
            <div className="add-inline">
              <input className="input" placeholder="shop=florist" value={osm} onChange={(e) => setOsm(e.target.value)} onKeyDown={(e) => e.key === "Enter" && addOsm()} />
              <button className="btn small" onClick={addOsm}><Plus size={13} /> Add</button>
            </div>
          </div>
          {country === "GB" && (
            <div className="sector-part">
              <div>Companies House trade (SIC) codes, UK only (finds which are limited companies)</div>
              <Tags kind="sic" values={sector.sic} onRemove={(v) => onChange({ ...sector, sic: sector.sic.filter((x) => x !== v) })} />
              <div className="add-inline">
                <input className="input" placeholder="96020" value={sic} onChange={(e) => setSic(e.target.value)} onKeyDown={(e) => e.key === "Enter" && addSic()} />
                <button className="btn small" onClick={addSic}><Plus size={13} /> Add</button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function TargetEditor({ slug, project, projects }: { slug?: string; project?: string; projects: Project[] }) {
  const [target, setTarget] = useState<TargetList | null>(slug ? null : { name: "", project: project ?? "", country: "GB", notes: "", sectors: {} });
  const [setup, setSetup] = useState<Setup | null>(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [order, setOrder] = useState<string[]>([]);

  useEffect(() => {
    api.setup().then(setSetup);
    if (slug) api.target(slug).then((t) => { setTarget(t); setOrder(Object.keys(t.sectors)); }, (e) => setError(e.message));
  }, [slug]);

  if (!target) return <div className="empty">{error || "Loading…"}</div>;
  const update = (patch: Partial<TargetList>) => setTarget({ ...target, ...patch });
  const names = order.filter((n) => n in target.sectors);

  const addSector = (name: string, sector: Sector) => {
    let unique = name;
    for (let i = 2; unique in target.sectors; i++) unique = `${name} ${i}`;
    update({ sectors: { ...target.sectors, [unique]: sector } });
    setOrder([...names, unique]);
  };
  const rename = (from: string, to: string) => {
    if (to in target.sectors) return toast("There's already a kind of business with that name");
    const sectors: Record<string, Sector> = {};
    for (const n of names) sectors[n === from ? to : n] = target.sectors[n];
    update({ sectors });
    setOrder(names.map((n) => (n === from ? to : n)));
  };
  const remove = (name: string) => {
    const { [name]: _, ...rest } = target.sectors;
    update({ sectors: rest });
  };
  const save = async () => {
    setSaving(true);
    setError("");
    const sectors: Record<string, Sector> = {};
    for (const n of names) sectors[n] = target.sectors[n];
    try {
      const result = slug ? await api.saveTarget(slug, { ...target, sectors }) : await api.createTarget({ ...target, sectors });
      toast("Target list saved");
      go(`/t/${result.slug}`);
    } catch (e) {
      setError((e as Error).message);
    }
    setSaving(false);
  };
  const owner = projects.find((p) => p.name === target.project);
  const used = new Set(Object.values(target.sectors).flatMap((s) => s.overture));

  return (
    <>
      <div className="page-head">
        <div>
          <div className="crumbs">
            <a href="#/projects">Projects</a> /
            {owner && <a href={`#/p/${owner.slug}`}>{owner.name}</a>} / {slug ? "Edit target list" : "New target list"}
          </div>
          <h1>{slug ? target.name || "Target list" : "New target list"}</h1>
          <p className="lede">Choose the kinds of business to look for and the country. Recon then finds every one on the open map data.</p>
        </div>
        <button className="btn primary" onClick={save} disabled={saving || !target.name.trim() || !names.length}>
          <Save size={15} /> {slug ? "Save changes" : "Save target list"}
        </button>
      </div>
      {error && <div className="notice bad" style={{ marginBottom: 16 }}>{error}</div>}
      <div className="card" style={{ display: "grid", gap: 16, gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", marginBottom: 24 }}>
        <label className="field">
          Name
          <input className="input" value={target.name} onChange={(e) => update({ name: e.target.value })} placeholder="SALEANE: UK dentists" />
        </label>
        <label className="field">
          Project
          <select className="input select" value={target.project} onChange={(e) => update({ project: e.target.value })}>
            <option value="">No project</option>
            {projects.map((p) => <option key={p.slug}>{p.name}</option>)}
          </select>
        </label>
        <label className="field">
          Country
          <select className="input select" value={target.country} onChange={(e) => update({ country: e.target.value })}>
            {(setup?.countries ?? [{ code: "GB", name: "United Kingdom" }]).map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}
          </select>
        </label>
        <label className="field" style={{ gridColumn: "1 / -1" }}>
          Notes
          <input className="input" value={target.notes} onChange={(e) => update({ notes: e.target.value })} placeholder="Who these businesses are, in a sentence" />
        </label>
        {target.box && (
          <div className="small muted" style={{ gridColumn: "1 / -1" }}>
            Only searching a smaller area: {target.box.join(", ")} (west, south, east, north).
          </div>
        )}
      </div>

      <div className="spread" style={{ marginBottom: 12 }}>
        <h2>Kinds of business</h2>
        <button className="btn small" onClick={() => addSector("New kind of business", empty())}><Plus size={14} /> Add your own</button>
      </div>
      <div className="stack" style={{ marginBottom: 30 }}>
        {names.map((n) => (
          <SectorCard key={n} name={n} sector={target.sectors[n]} country={target.country}
            onRename={(to) => rename(n, to)} onDelete={() => remove(n)}
            onChange={(s) => update({ sectors: { ...target.sectors, [n]: s } })} />
        ))}
        {!names.length && <div className="card empty">Pick a kind of business below, or add your own.</div>}
      </div>

      <div className="row" style={{ marginBottom: 12 }}>
        <Sparkles size={17} color="var(--accent-2)" />
        <h2>Quick add</h2>
        <span className="muted small">Ready-made kinds of business with their map categories and trade codes filled in.</span>
      </div>
      <div className="library">
        {LIBRARY.map((p) => {
          const added = p.sector.overture.every((c) => used.has(c));
          return (
            <button key={p.name} disabled={added} onClick={() => addSector(p.name, structuredClone(p.sector))}>
              <span className="emoji">{p.emoji}</span>
              <span>
                <b>{p.name}</b>
                <div className="faint small">{added ? "Already added" : p.hint}</div>
              </span>
            </button>
          );
        })}
      </div>
    </>
  );
}
