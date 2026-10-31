import { useEffect, useState } from "react";
import { BookmarkPlus, Check, PhoneMissed, PhoneOff, ThumbsDown, ThumbsUp, Trophy, UserCheck, Voicemail, CalendarClock } from "lucide-react";
import { crm, type Business, type Row, type SavedList } from "./api";
import { Modal, toast } from "./ui";

// Shared pieces of the small CRM: the outcome buttons, the status badge and
// the "save as list" box, used on the map, in Find, on lists and on Today's calls.

export const OUTCOMES: [string, string, typeof Check][] = [
  ["no answer", "No answer", PhoneMissed],
  ["voicemail", "Voicemail", Voicemail],
  ["call back", "Call back", CalendarClock],
  ["spoke", "Spoke", UserCheck],
  ["interested", "Interested", ThumbsUp],
  ["not interested", "Not interested", ThumbsDown],
  ["customer", "Customer", Trophy],
  ["do not contact", "Do not contact", PhoneOff],
];

const STATUS_STYLE: Record<string, string> = {
  new: "grey", "no answer": "grey", "call back": "blue", spoke: "blue", interested: "can",
  "not interested": "red", customer: "live", "do not contact": "red",
};

export function StatusBadge({ status, blocked }: { status: string; blocked?: boolean | number }) {
  if (blocked) return <span className="badge red">Do not contact</span>;
  if (!status || status === "new") return <span className="badge grey">Not contacted</span>;
  return <span className={`badge ${STATUS_STYLE[status] ?? "grey"}`}>{status.charAt(0).toUpperCase() + status.slice(1)}</span>;
}

export const SCREENING_WORDS: Record<string, string> = {
  clear: "Checked, may be called",
  tps: "On the TPS: do not call",
  ctps: "On the CTPS: do not call",
  stale: "Check is over 28 days old",
  unknown: "Not checked against TPS/CTPS yet",
  "no phone": "No phone number",
};

export function ScreeningBadge({ value }: { value: string }) {
  const style = value === "clear" ? "can" : value === "tps" || value === "ctps" ? "red" : value === "no phone" ? "grey" : "post";
  return <span className={`badge ${style}`} title={SCREENING_WORDS[value] ?? value}>{SCREENING_WORDS[value] ?? value}</span>;
}

// A row from the map or Find, turned into what the CRM saves. It carries the
// id the master database gave the business, or the trade list's details.
export const toRow = (item: Record<string, unknown>): Row =>
  Object.fromEntries(Object.entries(item).filter(([, v]) => v !== null && v !== undefined).map(([k, v]) => [k, String(v)]));

// The outcome buttons: one tap logs a call and moves the status on. "Call back"
// asks for a day; a note can go with anything.
export function LogOutcome({ business, onLogged, compact }: { business: string; onLogged?: (b: Business) => void; compact?: boolean }) {
  const [note, setNote] = useState("");
  const [callBack, setCallBack] = useState("");
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState("");
  const tomorrow = () => {
    const d = new Date();
    d.setDate(d.getDate() + 1);
    return d.toISOString().slice(0, 10);
  };
  const send = async (outcome: string) => {
    if (outcome === "call back" && !callBack) {
      setAsking(true);
      setCallBack(tomorrow());
      return;
    }
    setBusy(outcome);
    try {
      const b = await crm.log(business, { outcome, note, call_back: outcome === "call back" ? callBack : undefined });
      setNote("");
      setCallBack("");
      setAsking(false);
      toast(outcome === "note" ? "Note saved" : `Logged: ${outcome}`);
      onLogged?.(b);
    } catch (e) {
      toast((e as Error).message);
    } finally {
      setBusy("");
    }
  };
  return (
    <div className={`outcomes ${compact ? "compact" : ""}`}>
      <div className="outcome-grid">
        {OUTCOMES.map(([v, label, Icon]) => (
          <button key={v} className={`outcome ${v.replace(/ /g, "-")} ${busy === v ? "busy" : ""}`} disabled={!!busy} onClick={() => send(v)} title={label}>
            <Icon size={14} /> <span>{label}</span>
          </button>
        ))}
      </div>
      {asking && (
        <div className="row">
          <input className="input" type="date" value={callBack} onChange={(e) => setCallBack(e.target.value)} style={{ width: 170 }} />
          <button className="btn small primary" onClick={() => send("call back")} disabled={!callBack}>Save call back</button>
          <button className="btn small ghost" onClick={() => setAsking(false)}>Cancel</button>
        </div>
      )}
      <div className="row" style={{ gap: 6 }}>
        <input className="input" value={note} onChange={(e) => setNote(e.target.value)} placeholder="A note, if you like" maxLength={2000}
          onKeyDown={(e) => { if (e.key === "Enter" && note.trim()) send("note"); }} />
        <button className="btn small" onClick={() => send("note")} disabled={!note.trim() || !!busy}>Save note</button>
      </div>
    </div>
  );
}

// "Save as list": a new list with a name, or added to one that exists.
export function SaveToList({ rows, query, title, onClose, onSaved }: {
  rows: Row[]; query?: Record<string, string[]>; title?: string; onClose: () => void; onSaved?: (id: number) => void;
}) {
  const [lists, setLists] = useState<SavedList[]>([]);
  const [existing, setExisting] = useState<number | "">("");
  const [name, setName] = useState(title ?? "");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    crm.lists().then(setLists, () => setLists([]));
  }, []);
  const save = async () => {
    setBusy(true);
    try {
      if (existing) {
        const r = await crm.addItems(Number(existing), rows);
        toast(`${r.added} added to ${r.list.name}`);
        onSaved?.(Number(existing));
      } else {
        const made = await crm.createList({ name, query, items: rows });
        toast(`Saved ${rows.length} to the list ${made.name}`);
        onSaved?.(made.id);
      }
      onClose();
    } catch (e) {
      toast((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal title="Save as a list" onClose={onClose}>
      <p className="muted">{rows.length.toLocaleString("en-GB")} businesses will be saved with what Recon knows about them. The list keeps the businesses, not just the search, so it stays the same tomorrow.</p>
      <div className="field" style={{ marginTop: 14 }}>
        <label>New list</label>
        <input className="input" value={name} onChange={(e) => { setName(e.target.value); setExisting(""); }} placeholder="For example: Salons in Leeds, can email" autoFocus />
      </div>
      {lists.length > 0 && (
        <div className="field">
          <label>Or add to a list you have</label>
          <select className="input select" value={existing} onChange={(e) => setExisting(e.target.value ? Number(e.target.value) : "")}>
            <option value="">Make a new list</option>
            {lists.map((l) => <option key={l.id} value={l.id}>{l.name} ({l.businesses})</option>)}
          </select>
        </div>
      )}
      <div className="row" style={{ justifyContent: "flex-end", marginTop: 16 }}>
        <button className="btn ghost" onClick={onClose}>Cancel</button>
        <button className="btn primary" onClick={save} disabled={busy || (!existing && !name.trim()) || !rows.length}>
          <BookmarkPlus size={15} /> {existing ? "Add to list" : "Save list"}
        </button>
      </div>
    </Modal>
  );
}

export const when = (iso: string | null | undefined) => {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
};
