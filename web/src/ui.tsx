import { useEffect, useState, type ReactNode } from "react";
import { X } from "lucide-react";

// The page address after the #, split into parts: #/t/saleane-uk -> ["t", "saleane-uk"].
export function useRoute() {
  const read = () => {
    const [path, query = ""] = window.location.hash.replace(/^#\/?/, "").split("?");
    return { parts: path.split("/").filter(Boolean).map(decodeURIComponent), query: new URLSearchParams(query) };
  };
  const [route, setRoute] = useState(read);
  useEffect(() => {
    const changed = () => {
      setRoute(read());
      window.scrollTo(0, 0);
    };
    window.addEventListener("hashchange", changed);
    return () => window.removeEventListener("hashchange", changed);
  }, []);
  return route;
}

export const go = (path: string) => {
  window.location.hash = path;
};

export const fmt = (n: number | undefined | null) => (n ?? 0).toLocaleString("en-GB");

export const pct = (part: number, whole: number) =>
  whole ? `${Math.round((part / whole) * 100)}%` : "0%";

export const FLAGS: Record<string, string> = { GB: "🇬🇧", US: "🇺🇸", IE: "🇮🇪" };

export function RuleBadge({ rule }: { rule: string }) {
  if (rule === "can email") return <span className="badge can">✓ Can email</span>;
  if (rule === "post only") return <span className="badge post">✉ Post only</span>;
  if (rule) return <span className="badge check">Check local rules</span>;
  return <span className="badge grey">Not checked yet</span>;
}

export function Score({ value }: { value: string }) {
  if (value === "" || value === undefined) return null;
  const n = Number(value);
  const kind = n >= 70 ? "hi" : n >= 40 ? "mid" : "lo";
  return (
    <span className={`score ${kind}`} title={`Confidence ${n} out of 100. 70 or more is ready to use.`}>
      {n}
    </span>
  );
}

// Recon labels each address: shared inbox, named person, personal (Gmail and so on), other domain.
export function EmailKind({ kind }: { kind: string }) {
  if (!kind) return null;
  const k = kind.toLowerCase();
  const style = k.includes("personal") ? "pink" : k.includes("person") ? "blue" : k.includes("shared") ? "grey" : "grey";
  return <span className={`badge ${style}`}>{kind}</span>;
}

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  return (
    <>
      <div className="scrim" onClick={onClose} />
      <div className="modal" onClick={onClose}>
        <div className="modal-box" onClick={(e) => e.stopPropagation()}>
          <div className="spread">
            <h2>{title}</h2>
            <button className="btn ghost small" onClick={onClose} aria-label="Close">
              <X size={16} />
            </button>
          </div>
          {children}
        </div>
      </div>
    </>
  );
}

let showToast: (text: string) => void = () => {};
export const toast = (text: string) => showToast(text);

export function Toaster() {
  const [text, setText] = useState("");
  useEffect(() => {
    let timer: number;
    showToast = (t) => {
      setText(t);
      clearTimeout(timer);
      timer = window.setTimeout(() => setText(""), 3200);
    };
  }, []);
  return text ? <div className="toast">{text}</div> : null;
}

// Splits Recon's "a; b; c" style lists. Each item may carry a label in brackets.
export const splitList = (value: string) =>
  (value || "")
    .split(/[;|\n]+/)
    .map((s) => s.trim())
    .filter(Boolean);
