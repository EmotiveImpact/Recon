import { useEffect, useState, type ReactNode } from "react";
import { ArrowUpRight, FolderKanban, History, LayoutDashboard, ListChecks, Map as MapIcon, PhoneCall, Plus, Search, ShieldCheck, Sparkles } from "lucide-react";
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
import Lists from "./pages/Lists";
import Calls from "./pages/Calls";

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
  else if (section === "lists") page = <Lists id={id} />;
  else if (section === "calls") page = <Calls initial={query} />;
  else page = <Dashboard />;

  const current = section === "p" ? id : section === "t" ? projects.find((p) => p.targets.some((t) => t.slug === id))?.slug : "";
  const title =
    { map: "Map", find: "Find businesses", ask: "Ask Recon", lists: "Lists", calls: "Today's calls", projects: "Projects", runs: "Runs" }[section ?? ""] ??
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
          <span>Recon</span>
        </a>
        <nav className="nav">
          {link("#/", !section, <LayoutDashboard size={16} />, "Dashboard")}
          {link("#/map", section === "map", <MapIcon size={16} />, "Map")}
          {link("#/find", section === "find", <Search size={16} />, "Find businesses")}
          {link("#/ask", section === "ask", <Sparkles size={16} />, "Ask Recon")}
          <div className="nav-group">
            <div className="nav-label">Work</div>
            {link("#/calls", section === "calls", <PhoneCall size={16} />, "Today's calls")}
            {link("#/lists", section === "lists", <ListChecks size={16} />, "Lists")}
            {link("#/projects", section === "projects", <FolderKanban size={16} />, "All projects")}
            {link("#/runs", section === "runs", <History size={16} />, "Runs")}
          </div>
          <div className="nav-group">
            <div className="nav-label">Projects</div>
            {projects.map((p, i) => (
              <a key={p.slug} href={`#/p/${p.slug}`} className={current === p.slug ? "on" : ""}>
                <span className="dot" style={{ background: colourFor(i) }} /> {p.name}
              </a>
            ))}
            <a href="#/projects?new=1">
              <Plus size={16} /> New project
            </a>
          </div>
        </nav>
        <div className="side-foot" title="Open data only. Recon finds; it never sends. Overture Maps, OpenStreetMap, Companies House and 60 more open registers.">
          <span className="avatar">EI</span>
          <span className="side-foot-name">Emotive Impact</span>
          <ShieldCheck size={14} />
        </div>
      </aside>
      <div className="frame">
        <header className="topbar">
          <span className="topbar-title">
            <a href="#/">Recon</a>
            <i>/</i>
            <b>{title}</b>
          </span>
          <span className="topbar-links">
            <a className="text" href="https://github.com/EmotiveImpact/Recon/blob/main/docs/RULES.md" target="_blank" rel="noreferrer">
              Rules <ArrowUpRight size={13} />
            </a>
            <a className="text" href="https://github.com/EmotiveImpact/Recon/tree/main/docs" target="_blank" rel="noreferrer">
              Notes <ArrowUpRight size={13} />
            </a>
            <span className="topbar-rule" />
            <a className="round" href="#/find" aria-label="Search" title="Find businesses"><Search size={16} /></a>
            <a className="round" href="#/ask" aria-label="Ask Recon" title="Ask Recon"><Sparkles size={16} /></a>
            <span className="topbar-chip">🇬🇧 UK</span>
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
