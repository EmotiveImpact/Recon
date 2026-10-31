import { useEffect, useState } from "react";
import { ChevronRight, Globe, Mail, Phone, PhoneCall, ShieldAlert, ShieldCheck, Upload } from "lucide-react";
import { crm, type Business, type Call, type CallingSetup, type SavedList } from "../api";
import { fmt, Modal, RuleBadge, toast } from "../ui";
import { LogOutcome, SCREENING_WORDS, ScreeningBadge, StatusBadge, when } from "../crm";

// Today's calls: the next businesses to ring from a list, best prospects first,
// with a Call button (VoIPstudio, once switched on), the reasons, past notes
// and the outcome buttons. Nobody blocked or unscreened gets dialled.

export default function Calls({ initial }: { initial: URLSearchParams }) {
  const [lists, setLists] = useState<SavedList[]>([]);
  const [list, setList] = useState<number | null>(initial.get("list") ? Number(initial.get("list")) : null);
  const [count, setCount] = useState(10);
  const [queue, setQueue] = useState<Call[] | null>(null);
  const [at, setAt] = useState(0);
  const [setup, setSetup] = useState<CallingSetup | null>(null);
  const [error, setError] = useState("");
  const [calling, setCalling] = useState(false);
  const [screenBox, setScreenBox] = useState(false);
  const [history, setHistory] = useState<Business | null>(null);

  const load = () => {
    setQueue(null);
    crm.today(list, count).then((q) => { setQueue(q); setAt(0); }, (e) => setError(e.message));
  };
  useEffect(() => {
    crm.lists().then(setLists, () => setLists([]));
    crm.callingSetup().then(setSetup, () => setSetup(null));
  }, []);
  useEffect(load, [list, count]);
  const current = queue?.[at] ?? null;
  useEffect(() => {
    setHistory(null);
    if (current) crm.business(current.id).then(setHistory, () => setHistory(null));
  }, [current?.id]);

  const next = () => setAt((n) => Math.min(n + 1, (queue?.length ?? 1) - 1));
  const logged = () => {
    // The business just logged leaves today's queue; move on.
    if (!queue) return;
    const rest = queue.filter((_, n) => n !== at);
    setQueue(rest);
    setAt((n) => Math.min(n, Math.max(rest.length - 1, 0)));
  };
  const call = async () => {
    if (!current) return;
    setCalling(true);
    try {
      const r = await crm.startCall(current.id);
      toast(`Ringing ${r.to}. Your VoIPstudio phone rings first.`);
    } catch (e) {
      toast((e as Error).message);
    } finally {
      setCalling(false);
    }
  };
  const canCall = current && setup?.configured && !current.blocked && current.screening === "clear";
  const why = !current ? "" : current.blocked ? "This business asked not to be contacted." : current.screening !== "clear"
    ? SCREENING_WORDS[current.screening] : !setup?.configured ? "Calling is not switched on yet." : "";

  return (
    <div className="page calls">
      <div className="spread">
        <div>
          <h1>Today's calls</h1>
          <p className="muted">Your next calls, best prospects first: call-backs due today, then companies with a website and an email. Nobody on the do-not-contact list, and nobody whose number hasn't been checked, is dialled.</p>
        </div>
        <div className="row">
          <select className="input select" value={list ?? ""} onChange={(e) => setList(e.target.value ? Number(e.target.value) : null)} style={{ width: 240 }}>
            <option value="">Every list</option>
            {lists.map((l) => <option key={l.id} value={l.id}>{l.name} ({l.businesses})</option>)}
          </select>
          <div className="seg small">
            {[5, 10, 20].map((n) => <button key={n} className={count === n ? "on" : ""} onClick={() => setCount(n)}>{n}</button>)}
          </div>
        </div>
      </div>
      {error && <div className="notice bad">{error}</div>}

      <div className="calls-grid">
        <section className="card calls-queue">
          <div className="spread"><h3>Up next</h3><span className="faint small">{queue ? `${queue.length} to go` : ""}</span></div>
          {queue && queue.length === 0 && (
            <div className="muted small">Nothing to call{list ? " from this list" : ""}. Save a list with phone numbers, or come back when a call-back is due.</div>
          )}
          <div className="queue">
            {(queue ?? []).map((c, n) => (
              <button key={c.id} className={`queue-item ${n === at ? "on" : ""}`} onClick={() => setAt(n)}>
                <span className="n">{n + 1}</span>
                <span className="body"><b>{c.name}</b><span className="cell-sub">{[c.kind, c.postcode].filter(Boolean).join(" · ")}</span></span>
                <span className={`dot ${c.screening}`} title={SCREENING_WORDS[c.screening]} />
              </button>
            ))}
          </div>
        </section>

        <section className="card calls-main">
          {!current ? (
            <div className="empty-card">
              <PhoneCall size={22} />
              <h2>All done for now</h2>
              <p className="muted">Pick another list, or save more businesses from the map.</p>
            </div>
          ) : (
            <>
              <div className="spread" style={{ alignItems: "flex-start" }}>
                <div>
                  <h2>{current.name}</h2>
                  <div className="muted">{[current.kind, current.address, current.town, current.postcode].filter(Boolean).join(", ")}</div>
                </div>
                <div className="row">
                  <RuleBadge rule={current.rule} />
                  <StatusBadge status={current.status} blocked={current.blocked} />
                </div>
              </div>
              <div className="dial">
                <div className="dial-number">
                  <Phone size={18} />
                  <b>{current.phone || current.mobile}</b>
                  {current.mobile_number && <span className="badge grey">mobile</span>}
                  <ScreeningBadge value={current.screening} />
                </div>
                <div className="row">
                  <button className={`btn ${canCall ? "go" : ""}`} disabled={!canCall || calling} onClick={call} title={why || "Ring this business"}>
                    <PhoneCall size={15} /> {calling ? "Ringing…" : "Call"}
                  </button>
                  <a className="btn" href={`tel:${current.dial}`}><Phone size={15} /> Call from this device</a>
                  <button className="btn ghost" onClick={next} disabled={at >= (queue?.length ?? 0) - 1}>Skip <ChevronRight size={15} /></button>
                </div>
                {why && <div className="notice small">{why}</div>}
              </div>
              <div className="why">
                <div className="nav-label">Why this one</div>
                <div>{current.why.charAt(0).toUpperCase() + current.why.slice(1)}.{current.lists ? ` On: ${current.lists}.` : ""}</div>
                <div className="row" style={{ marginTop: 6 }}>
                  {current.email && <span className="chip"><Mail size={12} /> {current.email}</span>}
                  {current.website && <a className="chip" href={/^https?:/.test(current.website) ? current.website : `https://${current.website}`} target="_blank" rel="noreferrer"><Globe size={12} /> {current.website.replace(/^https?:\/\/(www\.)?/, "")}</a>}
                  {current.calls > 0 && <span className="chip">{current.calls} earlier {current.calls === 1 ? "call" : "calls"}, last {when(current.last_call)}</span>}
                </div>
              </div>
              {current.note && <div className="past-note"><div className="nav-label">Notes so far</div><div className="pre">{current.note}</div></div>}
              <div className="nav-label">What happened</div>
              <LogOutcome business={current.id} onLogged={logged} />
              {history && history.history.length > 0 && (
                <div className="history">
                  <div className="nav-label">History</div>
                  {history.history.slice(0, 6).map((h) => (
                    <div key={h.id} className="history-row">
                      <span className="faint">{when(h.at)}</span>
                      <span>{h.outcome ? <StatusBadge status={h.outcome} /> : <span className="badge grey">{h.kind}</span>}</span>
                      <span>{h.note}</span>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </section>

        <aside className="calls-side">
          <section className="card">
            <h3>{setup?.configured ? <><ShieldCheck size={15} /> Calling is on</> : <><ShieldAlert size={15} /> Calling is off</>}</h3>
            {setup && !setup.configured && (
              <>
                <p className="muted small">Prepared for {setup.provider}. Nothing is dialled until you sign up and set the keys. Until then "Call from this device" uses your own phone.</p>
                <ol className="steps small">
                  {setup.steps.map((s) => <li key={s}>{s}</li>)}
                </ol>
              </>
            )}
            {setup?.configured && (
              <p className="muted small">Calls go through {setup.provider}{setup.caller_id ? ` showing ${setup.caller_id}` : ""}. {setup.webhook_protected ? "Call results come back by webhook." : "Set RECON_WEBHOOK_KEY so only VoIPstudio can report calls."}</p>
            )}
          </section>
          <section className="card">
            <h3>Do-not-call check</h3>
            <p className="muted small">UK law: numbers must be checked against the TPS and CTPS within 28 days before a sales call. {setup ? <><b>{fmt(setup.unscreened)}</b> saved numbers still need a check.</> : null}</p>
            <div className="row">
              <a className="btn small" href="https://www.tpsservices.co.uk" target="_blank" rel="noreferrer">TPS Services</a>
              <button className="btn small" onClick={() => setScreenBox(true)}><Upload size={13} /> Enter results</button>
            </div>
            <p className="faint small" style={{ marginTop: 8 }}>Get the numbers with <code>python -m recon.crm unscreened</code>, check them, then paste the results here or run <code>python -m recon.crm screen results.csv</code>.</p>
          </section>
        </aside>
      </div>
      {screenBox && <ScreeningBox onClose={() => { setScreenBox(false); crm.callingSetup().then(setSetup, () => null); load(); }} />}
    </div>
  );
}

// Paste TPS/CTPS results: one number a line, with "clear", "tps" or "ctps" after it.
function ScreeningBox({ onClose }: { onClose: () => void }) {
  const [text, setText] = useState("");
  const [source, setSource] = useState("tps-services");
  const save = async () => {
    const rows = text.split("\n").map((l) => l.trim()).filter(Boolean).map((l) => {
      const parts = l.split(/[,\t;]+|\s{2,}|\s+(?=(clear|tps|ctps|ok|listed|yes|no)$)/i).filter(Boolean);
      return { phone: parts[0], result: (parts[1] ?? "clear").toLowerCase() };
    });
    try {
      const r = await crm.recordScreening(rows, source);
      toast(`${r.saved} numbers recorded`);
      onClose();
    } catch (e) {
      toast((e as Error).message);
    }
  };
  return (
    <Modal title="Do-not-call check results" onClose={onClose}>
      <p className="muted">One number a line, then a space or comma and the result: <code>clear</code>, <code>tps</code> or <code>ctps</code>. A number on its own counts as clear.</p>
      <textarea className="input" rows={8} value={text} onChange={(e) => setText(e.target.value)} placeholder={"01273 123456, clear\n07700 900123, tps"} />
      <div className="field" style={{ marginTop: 10 }}><label>Checked with</label><input className="input" value={source} onChange={(e) => setSource(e.target.value)} /></div>
      <div className="row" style={{ justifyContent: "flex-end", marginTop: 16 }}>
        <button className="btn ghost" onClick={onClose}>Cancel</button>
        <button className="btn primary" onClick={save} disabled={!text.trim()}>Save results</button>
      </div>
    </Modal>
  );
}
