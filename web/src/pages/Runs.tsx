import { useEffect, useState } from "react";
import { api, type Run } from "../api";
import { RunLog } from "./RunPanel";

const when = (t: number) => new Date(t * 1000).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" });

export default function Runs() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [open, setOpen] = useState("");
  useEffect(() => {
    const load = () => api.runs().then(setRuns);
    load();
    const timer = setInterval(load, 3000);
    return () => clearInterval(timer);
  }, []);
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Runs</h1>
          <p className="lede">Searches started from this website since Recon's server was last started.</p>
        </div>
      </div>
      {!runs.length && <div className="card empty">No runs yet. Open a target list and press Run.</div>}
      <div className="stack">
        {runs.map((run) => (
          <div key={run.id} className="card stack">
            <div className="spread" onClick={() => setOpen(open === run.id ? "" : run.id)} style={{ cursor: "pointer" }}>
              <div>
                <h3><a href={`#/t/${run.target}`}>{run.target}</a> · {run.step === "run" ? "full run" : run.step}</h3>
                <div className="faint small">Started {when(run.started)}{run.finished ? `, ended ${when(run.finished)}` : ""}</div>
              </div>
              <span className={`badge ${run.status === "running" ? "live" : run.status === "finished" ? "can" : "red"}`}>
                {run.status}
              </span>
            </div>
            {open === run.id && <RunLog runId={run.id} />}
          </div>
        ))}
      </div>
    </>
  );
}
