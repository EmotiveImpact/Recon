import { useEffect, useState, type ReactNode } from "react";
import { BookOpen, FolderKanban, History, LayoutDashboard, Map as MapIcon, Plus, Search, Sparkles } from "lucide-react";
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
import Ask from "./pages/Ask";

const COLOURS = ["#c9ccd6", "#7fd1ae", "#8b90a0", "#d9c9a3", "#a3b4d9", "#c9a3b4"];
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
  else if (section === "ask") page = <Ask />;
  else page = <Dashboard />;

  const current = section === "p" ? id : section === "t" ? projects.find((p) => p.targets.some((t) => t.slug === id))?.slug : "";
  const title =
    { map: "Map", find: "Find businesses", ask: "Ask Recon", projects: "Projects", runs: "Runs" }[section ?? ""] ??
    (section === "p" ? projects.find((p) => p.slug === id)?.name ?? "Project" : section === "t" ? "Target list" : "Dashboard");
  const link = (href: string, on: boolean, icon: ReactNode, label: string) => (
    <a href={href} className={on ? "on" : ""}>
      {icon} {label}
    </a>
  );
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
          <div className="nav-label">Find</div>
          {link("#/", !section, <LayoutDashboard size={16} />, "Dashboard")}
          {link("#/map", section === "map", <MapIcon size={16} />, "Map")}
          {link("#/find", section === "find", <Search size={16} />, "Find businesses")}
          {link("#/ask", section === "ask", <Sparkles size={16} />, "Ask Recon")}
          <div className="nav-label">Work</div>
          {link("#/projects", section === "projects", <FolderKanban size={16} />, "All projects")}
          {link("#/runs", section === "runs", <History size={16} />, "Runs")}
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
          <b>Open data only</b>
          Recon finds; it never sends. Overture Maps, OpenStreetMap, Companies House and 60 more open registers.
        </div>
      </aside>
      <div className="frame">
        <header className="topbar">
          <span className="topbar-title">
            Recon <i>/</i> <b>{title}</b>
          </span>
          <span className="topbar-links">
            <a href="#/ask"><Sparkles size={14} /> Ask</a>
            <a href="#/find"><Search size={14} /> Search</a>
            <a href="https://github.com/EmotiveImpact/Recon/tree/main/docs" target="_blank" rel="noreferrer">
              <BookOpen size={14} /> Rules and notes
            </a>
          </span>
        </header>
        <main className={section === "map" || section === "ask" ? "main flush" : "main"}>
          {error && <div className="notice bad" style={{ margin: section === "map" ? 16 : "0 0 20px" }}>{error}</div>}
          {page}
        </main>
      </div>
      <Toaster />
    </div>
  );
}
