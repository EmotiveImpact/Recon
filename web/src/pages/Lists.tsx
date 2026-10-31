import { useEffect, useState } from "react";
import { ArrowLeft, Download, ListChecks, Map as MapIcon, Phone, PhoneOff, Plus, Trash2, X } from "lucide-react";
import { crm, type Blocked, type Business, type ListDetail, type SavedList } from "../api";
import { fmt, go, Modal, pct, RuleBadge, toast } from "../ui";
import { LogOutcome, ScreeningBadge, StatusBadge, when } from "../crm";

// Saved lists: the businesses Edem has picked out from the map or Find, each
// with its status and notes, and the one do-not-contact list.

export default function Lists({ id }: { id?: string }) {
  if (id) return <ListPage id={Number(id)} />;
  return <AllLists />;
}

function AllLists() {
  const [lists, setLists] = useState<SavedList[] | null>(null);
  const [blocked, setBlocked] = useState<Blocked[]>([]);
  const [error, setError] = useState("");
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const load = () => {
    crm.lists().then(setLists, (e) => setError(e.message));
    crm.blocked().then(setBlocked, () => setBlocked([]));
  };
  useEffect(load, []);
  const create = async () => {
    try {
      const made = await crm.createList({ name });
      setAdding(false);
      setName("");
      go(`/lists/${made.id}`);
    } catch (e) {
      toast((e as Error).message);
    }
  };
  return (
    <div className="page">
      <div className="spread">
        <div>
          <h1>Lists</h1>
          <p className="muted">Businesses you have picked out, with where each one has got to. Make a list from the map or Find businesses with "Save as list".</p>
        </div>
        <div className="row">
          <a className="btn" href="#/calls"><Phone size={15} /> Today's calls</a>
          <button className="btn primary" onClick={() => setAdding(true)}><Plus size={15} /> New list</button>
        </div>
      </div>
      {error && <div className="notice bad">{error}</div>}
      {lists && lists.length === 0 && (
        <div className="card empty-card">
          <ListChecks size={22} />
          <h2>No lists yet</h2>
          <p className="muted">Search on the <a href="#/map">map</a> or in <a href="#/find">Find businesses</a>, then press "Save as list".</p>
        </div>
      )}
      {lists && lists.length > 0 && (
        <div className="grid">
          {lists.map((l) => (
            <a key={l.id} className="card hover list-card" href={`#/lists/${l.id}`}>
              <div className="spread">
                <h2>{l.name}</h2>
                {l.project && <span className="badge grey">{l.project}</span>}
              </div>
              <div className="list-nums">
                <div><b>{fmt(l.businesses)}</b><span>businesses</span></div>
                <div><b>{fmt(l.with_phone)}</b><span>with a phone</span></div>
                <div><b>{fmt(l.may_email)}</b><span>may email</span></div>
                <div><b>{pct(l.contacted, l.businesses)}</b><span>contacted</span></div>
              </div>
              <div className="progress"><i style={{ width: pct(l.contacted, l.businesses) }} /></div>
              <div className="cell-sub">Updated {when(l.updated)}</div>
            </a>
          ))}
        </div>
      )}

      <section className="panel" style={{ marginTop: 32 }}>
        <div className="panel-head">
          <div>
            <h2><PhoneOff size={16} /> Do not contact</h2>
            <p className="muted">Anyone here never appears in Today's calls or any export again. One list, shared by everything.</p>
          </div>
          <AddBlocked onAdded={setBlocked} />
        </div>
        {blocked.length === 0 ? (
          <div className="muted">Nobody yet.</div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Name</th><th>Phone</th><th>Email</th><th>Why</th><th>When</th><th /></tr></thead>
              <tbody>
                {blocked.map((b) => (
                  <tr key={b.id}>
                    <td>{b.name || <span className="faint">{b.business}</span>}</td>
                    <td>{b.phone}</td><td>{b.email}</td><td>{b.reason}</td><td>{when(b.at)}</td>
                    <td><button className="btn ghost small" title="Remove" onClick={() => crm.unblock(b.id).then(() => crm.blocked().then(setBlocked))}><X size={13} /></button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {adding && (
        <Modal title="New list" onClose={() => setAdding(false)}>
          <div className="field"><label>Name</label>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="For example: Dentists in Bristol" autoFocus onKeyDown={(e) => e.key === "Enter" && name.trim() && create()} />
          </div>
          <div className="row" style={{ justifyContent: "flex-end", marginTop: 16 }}>
            <button className="btn ghost" onClick={() => setAdding(false)}>Cancel</button>
            <button className="btn primary" onClick={create} disabled={!name.trim()}>Make the list</button>
          </div>
        </Modal>
      )}
    </div>
  );
}

function AddBlocked({ onAdded }: { onAdded: (b: Blocked[]) => void }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", phone: "", email: "", reason: "" });
  const save = async () => {
    try {
      onAdded(await crm.block(form));
      setOpen(false);
      setForm({ name: "", phone: "", email: "", reason: "" });
      toast("Added to do not contact");
    } catch (e) {
      toast((e as Error).message);
    }
  };
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });
  return (
    <>
      <button className="btn small" onClick={() => setOpen(true)}><Plus size={14} /> Add a number or address</button>
      {open && (
        <Modal title="Do not contact" onClose={() => setOpen(false)}>
          <p className="muted">A phone number or email address blocks every business that carries it.</p>
          <div className="field"><label>Name (optional)</label><input className="input" value={form.name} onChange={set("name")} /></div>
          <div className="field"><label>Phone</label><input className="input" value={form.phone} onChange={set("phone")} placeholder="01273 123456" /></div>
          <div className="field"><label>Email</label><input className="input" value={form.email} onChange={set("email")} /></div>
          <div className="field"><label>Why</label><input className="input" value={form.reason} onChange={set("reason")} placeholder="Asked us to stop" /></div>
          <div className="row" style={{ justifyContent: "flex-end", marginTop: 16 }}>
            <button className="btn ghost" onClick={() => setOpen(false)}>Cancel</button>
            <button className="btn primary" onClick={save} disabled={!form.phone.trim() && !form.email.trim()}>Block</button>
          </div>
        </Modal>
      )}
    </>
  );
}

function ListPage({ id }: { id: number }) {
  const [list, setList] = useState<ListDetail | null>(null);
  const [error, setError] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [editing, setEditing] = useState(false);
  const load = () => { crm.list(id).then(setList, (e) => setError(e.message)); };
  useEffect(load, [id]);
  if (error) return <div className="notice bad">{error}</div>;
  if (!list) return <div className="muted">Loading…</div>;
  const items = list.items.filter((i) => !filter || (filter === "todo" ? i.status === "new" && !i.blocked : i.status === filter));
  const mapLink = Object.keys(list.query).length ? `#/map?${new URLSearchParams(Object.entries(list.query).flatMap(([k, v]) => v.map((x) => [k, x])))}` : "";
  const remove = async (business: string) => {
    await crm.removeItem(id, business);
    load();
  };
  const del = async () => {
    if (!window.confirm(`Delete the list "${list.name}"? The businesses' notes and statuses are kept.`)) return;
    await crm.deleteList(id);
    go("/lists");
  };
  const counts = (s: string) => list.items.filter((i) => i.status === s).length;
  return (
    <div className="page">
      <a className="back" href="#/lists"><ArrowLeft size={14} /> All lists</a>
      <div className="spread">
        <div>
          <h1>{list.name}</h1>
          <p className="muted">{fmt(list.items.length)} businesses{list.project ? ` for ${list.project}` : ""}. {list.notes}</p>
        </div>
        <div className="row">
          {mapLink && <a className="btn" href={mapLink}><MapIcon size={15} /> Open the search</a>}
          <a className="btn" href={`#/calls?list=${id}`}><Phone size={15} /> Today's calls from this list</a>
          <a className="btn" href={crm.exportUrl(id)}><Download size={15} /> Download</a>
          <button className="btn ghost" onClick={() => setEditing(true)}>Rename</button>
          <button className="btn ghost danger" onClick={del} title="Delete the list"><Trash2 size={15} /></button>
        </div>
      </div>
      <div className="chips" style={{ marginTop: 12 }}>
        {[["", "Everyone", list.items.length], ["todo", "Not contacted", list.items.filter((i) => i.status === "new" && !i.blocked).length],
          ["call back", "Call back", counts("call back")], ["interested", "Interested", counts("interested")], ["customer", "Customers", counts("customer")],
          ["not interested", "Not interested", counts("not interested")]].map(([v, label, n]) => (
          <button key={String(v)} className={`chip ${filter === v ? "on" : ""}`} onClick={() => setFilter(String(v))}>{label} <b>{fmt(Number(n))}</b></button>
        ))}
      </div>
      <div className="table-wrap" style={{ marginTop: 14 }}>
        <table className="list-table">
          <thead><tr><th style={{ width: "24%" }}>Business</th><th style={{ width: "14%" }}>Where</th><th style={{ width: "12%" }}>Phone</th><th style={{ width: "18%" }}>Email</th><th style={{ width: "10%" }}>May we email?</th><th style={{ width: "10%" }}>Status</th><th>Note</th><th style={{ width: 40 }} /></tr></thead>
          <tbody>
            {items.map((i) => (
              <tr key={i.id} onClick={() => setOpen(i.id)} className="click">
                <td><b>{i.name}</b><div className="cell-sub">{i.kind}</div></td>
                <td>{[i.town, i.postcode].filter(Boolean).join(" ")}</td>
                <td>{i.phone || i.mobile}</td>
                <td className="small">{i.email}</td>
                <td><RuleBadge rule={i.rule} /></td>
                <td><StatusBadge status={i.status} blocked={i.blocked} />{i.call_back && <div className="cell-sub">call back {i.call_back}</div>}</td>
                <td className="small note-cell">{i.note}</td>
                <td><button className="btn ghost small" title="Take off this list" onClick={(e) => { e.stopPropagation(); remove(i.id); }}><X size={13} /></button></td>
              </tr>
            ))}
            {!items.length && <tr><td colSpan={8} className="muted">Nobody here.</td></tr>}
          </tbody>
        </table>
      </div>
      {open && <BusinessModal id={open} onClose={() => { setOpen(null); load(); }} />}
      {editing && (
        <Modal title="Rename the list" onClose={() => setEditing(false)}>
          <RenameForm list={list} onDone={(l) => { setList({ ...list, ...l }); setEditing(false); }} />
        </Modal>
      )}
    </div>
  );
}

function RenameForm({ list, onDone }: { list: ListDetail; onDone: (l: Partial<ListDetail>) => void }) {
  const [name, setName] = useState(list.name);
  const [project, setProject] = useState(list.project);
  const [notes, setNotes] = useState(list.notes);
  const save = async () => {
    try {
      const l = await crm.updateList(list.id, { name, project, notes });
      onDone(l);
    } catch (e) {
      toast((e as Error).message);
    }
  };
  return (
    <>
      <div className="field"><label>Name</label><input className="input" value={name} onChange={(e) => setName(e.target.value)} /></div>
      <div className="field"><label>Project</label><input className="input" value={project} onChange={(e) => setProject(e.target.value)} placeholder="SALEANE" /></div>
      <div className="field"><label>Notes</label><textarea className="input" rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} /></div>
      <div className="row" style={{ justifyContent: "flex-end", marginTop: 16 }}>
        <button className="btn primary" onClick={save} disabled={!name.trim()}>Save</button>
      </div>
    </>
  );
}

// One business: its details, its history and the outcome buttons.
export function BusinessModal({ id, onClose }: { id: string; onClose: () => void }) {
  const [b, setB] = useState<Business | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    crm.business(id).then(setB, (e) => setError(e.message));
  }, [id]);
  return (
    <Modal title={b?.name ?? "Business"} onClose={onClose}>
      {error && <div className="notice bad">{error}</div>}
      {b && (
        <div className="biz">
          <div className="row">
            <RuleBadge rule={b.rule} />
            <StatusBadge status={b.status} blocked={b.blocked} />
            <ScreeningBadge value={b.screening} />
          </div>
          <dl className="kv">
            <dt>What</dt><dd>{b.kind || "Not known"}</dd>
            <dt>Address</dt><dd>{[b.address, b.town, b.postcode].filter(Boolean).join(", ") || "Not known"}</dd>
            {(b.phone || b.mobile) && <><dt>Phone</dt><dd>{[b.phone, b.mobile].filter((x, n, a) => x && a.indexOf(x) === n).join(", ")}</dd></>}
            {b.email && <><dt>Email</dt><dd>{b.email}</dd></>}
            {b.website && <><dt>Website</dt><dd><a href={/^https?:/.test(b.website) ? b.website : `https://${b.website}`} target="_blank" rel="noreferrer" className="link">{b.website.replace(/^https?:\/\/(www\.)?/, "")}</a></dd></>}
            {b.lists.length > 0 && <><dt>On lists</dt><dd>{b.lists.map((l) => <a key={l.id} href={`#/lists/${l.id}`} className="link" style={{ marginRight: 8 }}>{l.name}</a>)}</dd></>}
            {b.call_back && <><dt>Call back</dt><dd>{b.call_back}</dd></>}
            {b.note && <><dt>Notes</dt><dd className="pre">{b.note}</dd></>}
          </dl>
          <LogOutcome business={b.id} onLogged={setB} />
          {b.history.length > 0 && (
            <div className="history">
              <div className="nav-label">History</div>
              {b.history.map((h) => (
                <div key={h.id} className="history-row">
                  <span className="faint">{when(h.at)}</span>
                  <span>{h.outcome ? <StatusBadge status={h.outcome} /> : <span className="badge grey">{h.kind}</span>}</span>
                  <span>{h.note}{h.seconds != null && h.kind === "call" && !h.note.includes("seconds") ? ` (${h.seconds}s)` : ""}{h.recording && <> <a className="link" href={h.recording} target="_blank" rel="noreferrer">recording</a></>}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}
