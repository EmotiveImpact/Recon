import { useEffect, useState } from "react";
import { FolderKanban, History, LayoutDashboard, Map as MapIcon, Plus, Search } from "lucide-react";
import { api, type Project } from "./api";
import { Toaster, useRoute } from "./ui";
import Projects from "./pages/Projects";
import ProjectPage from "./pages/Project";
import TargetEditor from "./pages/TargetEditor";
import Results from "./pages/Results";
import Runs from "./pages/Runs";
import Find from "./pages/Find";
import Dashboard from "./pages/Dashboard";
import MapView from "./pages/MapView";

const COLOURS = ["#7c5cff", "#22d3ee", "#34d399", "#f472b6", "#fbbf24", "#60a5fa"];
export const colourFor = (i: number) => COLOURS[i % COLOURS.length];

export default function App() {
  const { parts, query } = useRoute();
  const [projects, setProjects] = useState<Project[]>([]);
  const [error, setError] = useState("");
  const refresh = () =>
    api.projects().then(setProjects, (e) => setError(`Can't reach Recon's server: ${e.message}`));
  useEffect(() => {
    refresh();
  }, [parts.join("/")]);

  let page;
  const [section, id, action] = parts;
  if (section === "p" && id) page = <ProjectPage slug={id} projects={projects} refresh={refresh} />;
  else if (section === "t" && id === "new") page = <TargetEditor project={query.get("project") || ""} projects={projects} />;
  else if (section === "t" && id && action === "edit") page = <TargetEditor slug={id} projects={projects} />;
  else if (section === "t" && id) page = <Results slug={id} projects={projects} />;
  else if (section === "runs") page = <Runs />;
  else if (section === "projects") page = <Projects projects={projects} refresh={refresh} />;
  else if (section === "find") page = <Find key={query.toString()} initial={query} />;
  else if (section === "map") page = <MapView initial={query} />;
  else page = <Dashboard />;

  const current = section === "p" ? id : section === "t" ? projects.find((p) => p.targets.some((t) => t.slug === id))?.slug : "";
  return (
    <div className="shell">
      <aside className="side">
        <a className="brand" href="#/">
          <img src="/favicon.svg" alt="" />
          <span>
            Recon
            <small>Outreach finder</small>
          </span>
        </a>
        <nav className="nav">
          <a href="#/" className={!section ? "on" : ""}>
            <LayoutDashboard size={17} /> Dashboard
          </a>
          <a href="#/map" className={section === "map" ? "on" : ""}>
            <MapIcon size={17} /> Map
          </a>
          <a href="#/find" className={section === "find" ? "on" : ""}>
            <Search size={17} /> Find businesses
          </a>
          <a href="#/projects" className={section === "projects" ? "on" : ""}>
            <FolderKanban size={17} /> All projects
          </a>
          <a href="#/runs" className={section === "runs" ? "on" : ""}>
            <History size={17} /> Runs
          </a>
          <div className="nav-label">Projects</div>
          {projects.map((p, i) => (
            <a key={p.slug} href={`#/p/${p.slug}`} className={current === p.slug ? "on" : ""}>
              <span className="dot" style={{ background: colourFor(i) }} /> {p.name}
            </a>
          ))}
          <a href="#/projects?new=1">
            <Plus size={16} /> New project
          </a>
        </nav>
        <div className="side-foot">
          Open data only. Recon finds; it never sends.
          <br />
          Overture Maps · OpenStreetMap · Companies House · 60 more open registers
        </div>
      </aside>
      <main className={section === "map" ? "main flush" : "main"}>
        {error && <div className="notice bad" style={{ marginBottom: 20 }}>{error}</div>}
        {page}
      </main>
      <Toaster />
    </div>
  );
}
