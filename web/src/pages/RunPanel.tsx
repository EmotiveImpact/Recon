import { useEffect, useRef, useState } from "react";
import { CheckCircle2, Loader2, Play, Square, XCircle } from "lucide-react";
import { api, type Run, type Setup, type TargetCard } from "../api";
import { go, Modal, toast } from "../ui";

const STEPS: [string, string][] = [
  ["run", "Everything, start to finish"],
  ["places", "1. Find businesses on the map"],
  ["companies", "2. Match to Companies House"],
  ["rules", "3. Work out who may be emailed"],
  ["people", "4. Name a director"],
  ["emails", "5. Look for emails on their websites"],
  ["verify", "6. Check the emails"],
  ["export", "7. Make the spreadsheet"],
];

export function RunLog({ runId, onDone }: { runId: string; onDone?: (run: Run) => void }) {
  const [run, setRun] = useState<Run | null>(null);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let stop = false;
    const tick = async () => {
      const r = await api.run(runId).catch(() => null);
      if (stop || !r) return;
      setRun(r);
      if (r.status === "running") setTimeout(tick, 1500);
      else onDone?.(r);
    };
    tick();
    return () => {
      stop = true;
    };
  }, [runId]);
  useEffect(() => {
    box.current?.scrollTo(0, box.current.scrollHeight);
  }, [run?.log]);
  if (!run) return null;
  return (
    <div className="stack">
      <div className="spread">
        <div className="row">
          {run.status === "running" && <Loader2 size={16} className="spin" />}
          {run.status === "finished" && <CheckCircle2 size={16} color="var(--green)" />}
          {(run.status === "failed" || run.status === "stopped") && <XCircle size={16} color="var(--red)" />}
          <b>
            {run.status === "running" ? "Running…" : run.status === "finished" ? "Finished" : run.status === "stopped" ? "Stopped" : "Something went wrong"}
          </b>
        </div>
        {run.status === "running" && (
          <button className="btn small danger" onClick={() => api.stopRun(run.id)}>
            <Square size={13} /> Stop
          </button>
        )}
      </div>
      <div className="log" ref={box}>{run.log || "Starting…"}</div>
    </div>
  );
}

export default function RunPanel({ target, onClose }: { target: TargetCard; onClose: () => void }) {
  const [setup, setSetup] = useState<Setup | null>(null);
  const [step, setStep] = useState("run");
  const [chFile, setChFile] = useState("");
  const [skipOsm, setSkipOsm] = useState(false);
  const [canEmailOnly, setCanEmailOnly] = useState(false);
  const [runId, setRunId] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    api.setup().then((s) => {
      setSetup(s);
      setChFile(s.companies_house_files.at(-1) ?? "");
    });
  }, []);
  const start = async () => {
    setError("");
    try {
      const run = await api.startRun(target.slug, step, {
        companies_house: chFile ? [chFile] : [],
        skip_osm: skipOsm,
        can_email_only: canEmailOnly,
      });
      setRunId(run.id);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const uk = target.country === "GB";
  return (
    <Modal title={`Run ${target.name}`} onClose={onClose}>
      {runId ? (
        <>
          <RunLog runId={runId} onDone={(r) => r.status === "finished" && toast("Run finished")} />
          <div className="row" style={{ justifyContent: "flex-end" }}>
            <button className="btn" onClick={onClose}>Close</button>
            <button className="btn primary" onClick={() => go(`/t/${target.slug}`)}>See results</button>
          </div>
        </>
      ) : (
        <>
          <p className="muted small">
            Recon will find these businesses in open map data, work out who may be emailed, and look for emails on
            their own websites. A full UK run can take a few hours; you can close this and come back.
          </p>
          <label className="field">
            What to run
            <select className="input select" value={step} onChange={(e) => setStep(e.target.value)}>
              {STEPS.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
            </select>
          </label>
          {uk && (
            <label className="field">
              Companies House file (decides who may be emailed in the UK)
              <select className="input select" value={chFile} onChange={(e) => setChFile(e.target.value)}>
                <option value="">None: everyone stays "post only"</option>
                {setup?.companies_house_files.map((f) => <option key={f} value={f}>{f}</option>)}
              </select>
            </label>
          )}
          {uk && setup && !setup.companies_house_files.length && (
            <div className="notice warn small">
              No Companies House file found in the data folder yet. Without it, every UK business is marked post only.
            </div>
          )}
          <label className="row small">
            <input type="checkbox" checked={skipOsm} onChange={(e) => setSkipOsm(e.target.checked)} />
            Skip OpenStreetMap (use when its server can't be reached)
          </label>
          <label className="row small">
            <input type="checkbox" checked={canEmailOnly} onChange={(e) => setCanEmailOnly(e.target.checked)} />
            Only visit websites of businesses we may email (quicker)
          </label>
          {setup && !setup.duckdb && (
            <div className="notice warn small">DuckDB isn't installed, so Overture Maps can't be read on this computer.</div>
          )}
          {error && <div className="notice bad small">{error}</div>}
          <div className="row" style={{ justifyContent: "flex-end" }}>
            <button className="btn ghost" onClick={onClose}>Cancel</button>
            <button className="btn go" onClick={start}><Play size={15} /> Start run</button>
          </div>
        </>
      )}
    </Modal>
  );
}
