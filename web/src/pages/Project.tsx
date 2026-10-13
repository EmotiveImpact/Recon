import { useState } from "react";
import { Pencil, Play, Plus, Table2 } from "lucide-react";
import type { Project, TargetCard } from "../api";
import { FLAGS, fmt, go, pct } from "../ui";
import { ProjectForm, totals } from "./Projects";
import RunPanel from "./RunPanel";

function TargetTile({ target, onRun }: { target: TargetCard; onRun: () => void }) {
  const r = target.results;
  return (
    <div className="card hover stack">
      <div className="spread" style={{ alignItems: "flex-start" }}>
        <a href={`#/t/${target.slug}`} style={{ minWidth: 0 }}>
          <h2>
            <span style={{ marginRight: 8 }}>{FLAGS[target.country] ?? "🌍"}</span>
            {target.name}
          </h2>
          {target.notes && <p className="muted small" style={{ marginTop: 4 }}>{target.notes}</p>}
        </a>
        {target.running && <span className="badge live">Running</span>}
      </div>
      <div className="chips">
        {target.sectors.map((s) => (
          <span key={s} className="badge grey">{s}</span>
        ))}
      </div>
      {r ? (
        <>
          <div className="mini-stats">
            <div><b>{fmt(r.total)}</b><span>businesses</span></div>
            <div><b style={{ color: "var(--green)" }}>{fmt(r.can_email)}</b><span>can email</span></div>
            <div><b style={{ color: "var(--amber)" }}>{fmt(r.post_only)}</b><span>post only</span></div>
            <div><b style={{ color: "var(--accent-2)" }}>{fmt(r.with_email)}</b><span>emails found</span></div>
          </div>
          <div className="bar" title={`${pct(r.can_email, r.total)} may be emailed`}>
            <i style={{ width: pct(r.can_email, r.total), background: "var(--green)" }} />
            <i style={{ width: pct(r.post_only, r.total), background: "var(--amber)" }} />
          </div>
          <div className="faint small">Last results {r.updated}</div>
        </>
      ) : (
        <div className="notice small">No results yet. Press Run to search for these businesses.</div>
      )}
      <div className="row">
        <button className="btn go small" onClick={onRun} disabled={target.running}>
          <Play size={14} /> Run
        </button>
        <a className="btn small" href={`#/t/${target.slug}`}>
          <Table2 size={14} /> Results
        </a>
        <a className="btn small ghost" href={`#/t/${target.slug}/edit`}>
          <Pencil size={14} /> Edit list
        </a>
      </div>
    </div>
  );
}

export default function ProjectPage({ slug, projects, refresh }: { slug: string; projects: Project[]; refresh: () => void }) {
  const project = projects.find((p) => p.slug === slug);
  const [editing, setEditing] = useState(false);
  const [running, setRunning] = useState<TargetCard | null>(null);
  if (!project) return <div className="empty">Loading…</div>;
  const t = totals(project);
  return (
    <>
      <div className="page-head">
        <div>
          <div className="crumbs"><a href="#/">Projects</a> / {project.name}</div>
          <h1>{project.name}</h1>
          {project.description && <p className="lede">{project.description}</p>}
        </div>
        <div className="row">
          <button className="btn" onClick={() => setEditing(true)}><Pencil size={15} /> Edit project</button>
          <a className="btn primary" href={`#/t/new?project=${encodeURIComponent(project.name)}`}>
            <Plus size={16} /> New target list
          </a>
        </div>
      </div>
      <div className="stats" style={{ marginBottom: 26 }}>
        <div className="stat"><b>{fmt(t.total)}</b><span>businesses found</span></div>
        <div className="stat green"><b>{fmt(t.canEmail)}</b><span>may be emailed</span></div>
        <div className="stat blue"><b>{fmt(t.withEmail)}</b><span>have an email</span></div>
        <div className="stat pink"><b>{fmt(t.ready)}</b><span>emails ready to use</span></div>
        <div className="stat"><b>{project.targets.length}</b><span>target lists</span></div>
      </div>
      <h2 style={{ marginBottom: 14 }}>Target lists</h2>
      <div className="grid">
        {project.targets.map((target) => (
          <TargetTile key={target.slug} target={target} onRun={() => setRunning(target)} />
        ))}
        <a className="card new-card" href={`#/t/new?project=${encodeURIComponent(project.name)}`}>
          <div className="stack" style={{ alignItems: "center" }}>
            <Plus size={26} />
            <div>Add a list of new business types</div>
          </div>
        </a>
      </div>
      {editing && (
        <ProjectForm
          project={project}
          onDone={(newSlug) => {
            setEditing(false);
            refresh();
            if (newSlug && newSlug !== slug) go(`/p/${newSlug}`);
          }}
        />
      )}
      {running && (
        <RunPanel
          target={running}
          onClose={() => {
            setRunning(null);
            refresh();
          }}
        />
      )}
    </>
  );
}
