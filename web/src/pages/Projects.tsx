import { useEffect, useState } from "react";
import { ArrowRight, Plus } from "lucide-react";
import { api, type Project } from "../api";
import { fmt, go, Modal, toast, useRoute } from "../ui";

export function totals(project: Project) {
  const sum = (key: "total" | "can_email" | "with_email" | "ready") =>
    project.targets.reduce((n, t) => n + (t.results?.[key] ?? 0), 0);
  return { total: sum("total"), canEmail: sum("can_email"), withEmail: sum("with_email"), ready: sum("ready") };
}

export function ProjectForm({ project, onDone }: { project?: Project; onDone: (slug?: string) => void }) {
  const [name, setName] = useState(project?.name ?? "");
  const [description, setDescription] = useState(project?.description ?? "");
  const [error, setError] = useState("");
  const save = async () => {
    try {
      const { slug } = project
        ? await api.saveProject(project.slug, { name, description })
        : await api.createProject({ name, description });
      toast(project ? "Project saved" : `${name} created`);
      onDone(slug);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <Modal title={project ? "Edit project" : "New project"} onClose={() => onDone()}>
      <p className="muted small">
        A project is a product you want customers for. It holds the lists of businesses to reach.
      </p>
      <label className="field">
        Name
        <input className="input" autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="SALEANE" />
      </label>
      <label className="field">
        What it is, and who it's for
        <textarea className="input" rows={3} value={description} onChange={(e) => setDescription(e.target.value)} />
      </label>
      {error && <div className="notice bad">{error}</div>}
      <div className="row" style={{ justifyContent: "flex-end" }}>
        <button className="btn ghost" onClick={() => onDone()}>Cancel</button>
        <button className="btn primary" onClick={save} disabled={!name.trim()}>
          {project ? "Save" : "Create project"}
        </button>
      </div>
    </Modal>
  );
}

export default function Projects({ projects, refresh }: { projects: Project[]; refresh: () => void }) {
  const { query } = useRoute();
  const [adding, setAdding] = useState(false);
  useEffect(() => setAdding(query.get("new") === "1"), [query.get("new")]);
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Projects</h1>
          <p className="lede">
            Each project is a product you're finding customers for. Open one to see its lists of businesses, run a
            search, and browse who you may email and who should get post.
          </p>
        </div>
        <button className="btn primary" onClick={() => setAdding(true)}>
          <Plus size={16} /> New project
        </button>
      </div>
      <div className="grid">
        {projects.map((p) => {
          const t = totals(p);
          return (
            <a key={p.slug} href={`#/p/${p.slug}`} className="card hover project-card stack">
              <div className="row" style={{ gap: 14 }}>
                <div className="project-mark">{p.name.slice(0, 1)}</div>
                <div style={{ minWidth: 0 }}>
                  <h2>{p.name}</h2>
                  <div className="muted small">
                    {p.targets.length} target list{p.targets.length === 1 ? "" : "s"}
                  </div>
                </div>
              </div>
              {p.description && <p className="muted small">{p.description}</p>}
              <div className="mini-stats">
                <div><b>{fmt(t.total)}</b><span>businesses</span></div>
                <div><b style={{ color: "var(--green)" }}>{fmt(t.canEmail)}</b><span>can email</span></div>
                <div><b style={{ color: "var(--accent-2)" }}>{fmt(t.withEmail)}</b><span>emails found</span></div>
              </div>
              <div className="row muted small">Open <ArrowRight size={14} /></div>
            </a>
          );
        })}
        <button className="card new-card" onClick={() => setAdding(true)}>
          <div className="stack" style={{ alignItems: "center" }}>
            <Plus size={26} />
            <div>Start a new project</div>
          </div>
        </button>
      </div>
      {adding && (
        <ProjectForm
          onDone={(slug) => {
            setAdding(false);
            refresh();
            if (slug) go(`/p/${slug}`);
            else if (query.get("new")) go("/projects");
          }}
        />
      )}
    </>
  );
}
