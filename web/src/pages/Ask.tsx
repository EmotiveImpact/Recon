import { useEffect, useRef, useState } from "react";
import { ArrowUp, Map as MapIcon, MessageSquarePlus, Sparkles } from "lucide-react";
import { api, type Answer } from "../api";
import { fmt } from "../ui";

// Ask Recon: type a question in plain words, get counts from the sector index
// and a link to the same businesses on the map. Read with simple rules, no AI service.

const EXAMPLES = [
  "Hair salons in Leeds I can email",
  "Plumbers near BN1 within 10 miles with a phone",
  "Dentists in Manchester",
  "Accountants in Bristol with an email",
];

type Turn = { question: string; answer?: Answer; error?: string };

export default function Ask() {
  const [text, setText] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => end.current?.scrollIntoView({ behavior: "smooth" }), [turns]);

  const ask = async (question: string) => {
    question = question.trim();
    if (!question || busy) return;
    setText("");
    setBusy(true);
    setTurns((t) => [...t, { question }]);
    const done = (turn: Partial<Turn>) =>
      setTurns((t) => t.map((x, i) => (i === t.length - 1 ? { ...x, ...turn } : x)));
    try {
      done({ answer: await api.ask(question) });
    } catch (e) {
      done({ error: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="ask-wrap">
    <div className="ask">
      <div className="ask-body">
        {turns.length === 0 ? (
          <div className="ask-empty">
            <Sparkles size={20} />
            <h2>Ask Recon</h2>
            <p>Ask about any kind of UK business in a town or postcode. Recon counts them, says how many you may email, and opens them on the map.</p>
            <div className="ask-examples">
              {EXAMPLES.map((e) => (
                <button key={e} onClick={() => ask(e)}>{e}</button>
              ))}
            </div>
          </div>
        ) : (
          <div className="ask-turns">
            {turns.map((t, i) => (
              <div key={i} className="ask-turn">
                <div className="ask-q">{t.question}</div>
                {t.error ? (
                  <div className="ask-a bad">{t.error}</div>
                ) : !t.answer ? (
                  <div className="ask-a muted">Counting…</div>
                ) : (
                  <AnswerCard answer={t.answer} />
                )}
              </div>
            ))}
            <div ref={end} />
          </div>
        )}
      </div>
      <form
        className="ask-input"
        onSubmit={(e) => {
          e.preventDefault();
          ask(text);
        }}
      >
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="For example: hair salons in Leeds I can email"
          maxLength={300}
          autoFocus
        />
        <button type="submit" disabled={!text.trim() || busy} aria-label="Ask">
          <ArrowUp size={16} />
        </button>
      </form>
    </div>
      <aside className="ask-side">
        <button className="btn ask-new" onClick={() => setTurns([])} disabled={!turns.length}>
          <MessageSquarePlus size={14} /> New conversation
        </button>
        {turns.length > 0 && (
          <div className="ask-history">
            <div className="nav-label">This conversation</div>
            {turns.map((t, i) => (
              <span key={i}>{t.question}</span>
            ))}
          </div>
        )}
      </aside>
    </div>
  );
}

function AnswerCard({ answer }: { answer: Answer }) {
  const f = answer.figures;
  const link = answer.map ? new URLSearchParams(Object.entries(answer.map).flatMap(([k, v]) => v.map((x) => [k, x]))) : null;
  return (
    <div className="ask-a">
      {answer.answer.split("\n").map((line, i) => (
        <p key={i}>{line}</p>
      ))}
      {f && f.total > 0 && (
        <div className="ask-figures">
          <div><b>{fmt(f.total)}</b><span>found</span></div>
          <div><b>{fmt(f.may_email)}</b><span>may email</span></div>
          <div><b>{fmt(f.with_email)}</b><span>have an email</span></div>
          <div><b>{fmt(f.with_phone)}</b><span>have a phone</span></div>
        </div>
      )}
      {link && f && f.total > 0 && (
        <a className="btn" href={`#/map?${link}`}>
          <MapIcon size={15} /> Show on the map
        </a>
      )}
    </div>
  );
}
