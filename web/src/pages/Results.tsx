import { useEffect, useMemo, useState } from "react";
import {
  ArrowDown, ArrowUp, Building2, Download, ExternalLink, Globe, Mail, MapPin, Pencil, Phone, Play, Search,
  Smartphone, User, X,
} from "lucide-react";
import { api, type Project, type Results as ResultsData, type Row } from "../api";
import { EmailKind, FLAGS, fmt, pct, RuleBadge, Score, splitList } from "../ui";
import RunPanel from "./RunPanel";

const HAS: [string, string][] = [
  ["email", "Has an email"],
  ["ready", "Email ready to use"],
  ["person", "Named person"],
  ["phone", "Has a phone"],
  ["mobile", "Has a mobile"],
  ["socials", "Has socials"],
  ["website", "Has a website"],
  ["company", "Registered company"],
];

const RULES: [string, string][] = [
  ["", "Everyone"],
  ["can email", "Can email"],
  ["post only", "Post only"],
  ["check local rules", "Check local rules"],
];

// "a@b.com (personal); c@d.com (shared inbox)" -> [["a@b.com", "personal"], ...]
const labelled = (value: string) =>
  splitList(value).map((item) => {
    const m = item.match(/^(.*?)\s*\(([^)]*)\)\s*$/);
    return m ? [m[1], m[2]] : [item, ""];
  });

const socialName = (url: string) => {
  const host = url.replace(/^https?:\/\/(www\.)?/, "").split("/")[0];
  return host.replace(/\.(com|net|co\.uk)$/, "");
};

const SORTS: [string, string][] = [
  ["name", "Business"],
  ["town", "Town"],
  ["contact_rule", "May we email?"],
  ["email_confidence", "Email"],
];

function Details({ row, onClose }: { row: Row; onClose: () => void }) {
  const emails = labelled(row.all_emails);
  if (row.email && !emails.some(([a]) => a === row.email)) emails.unshift([row.email, row.email_type]);
  const phones = labelled(row.all_phones);
  if (row.phone && !phones.length) phones.push([row.phone, row.phone_type]);
  const socials = (row.socials || "").split(/\s+/).filter(Boolean);
  const mapUrl = row.lat && row.lon ? `https://www.openstreetmap.org/?mlat=${row.lat}&mlon=${row.lon}#map=18/${row.lat}/${row.lon}` : "";
  return (
    <>
      <div className="scrim" onClick={onClose} />
      <aside className="drawer">
        <div className="spread" style={{ alignItems: "flex-start" }}>
          <div>
            <h2 style={{ fontSize: 22 }}>{row.name}</h2>
            <div className="muted small">{row.sector} · {row.category?.replaceAll("_", " ")}</div>
          </div>
          <button className="btn ghost small" onClick={onClose} aria-label="Close"><X size={16} /></button>
        </div>
        <div className={`notice ${row.contact_rule === "can email" ? "good" : "warn"}`}>
          <div>
            <RuleBadge rule={row.contact_rule} />
            <p className="small" style={{ marginTop: 6 }}>
              {row.contact_rule === "can email"
                ? "A registered company or LLP: you may email it, with a clear way to opt out."
                : row.contact_rule === "post only"
                  ? "Not matched to a limited company, so it may be a sole trader or partnership. Write by post, or email only with their consent."
                  : "Recon doesn't know this country's email rules yet. Check before emailing."}
            </p>
          </div>
        </div>

        <div>
          <div className="section-title">Emails</div>
          {emails.length ? (
            <div className="list">
              {emails.map(([address, kind]) => (
                <div key={address} className="list-item">
                  <span className="row" style={{ gap: 8, minWidth: 0 }}>
                    <Mail size={14} className="faint" />
                    <span style={{ wordBreak: "break-all" }}>{address}</span>
                  </span>
                  <span className="row" style={{ gap: 6 }}>
                    <EmailKind kind={kind} />
                    {address === row.email && <Score value={row.email_confidence} />}
                  </span>
                </div>
              ))}
            </div>
          ) : <p className="faint small">No email found.</p>}
          {row.email_reason && <p className="faint small" style={{ marginTop: 8 }}>{row.email_reason}</p>}
        </div>

        {(row.contact_name || row.contact_email) && (
          <div>
            <div className="section-title">Named person</div>
            <div className="list-item">
              <span className="row" style={{ gap: 8 }}>
                <User size={14} className="faint" />
                <span>
                  {row.contact_name} <span className="faint small">{row.contact_role}</span>
                  {row.contact_email && <div className="small">{row.contact_email}</div>}
                </span>
              </span>
              <Score value={row.contact_email_confidence} />
            </div>
            {row.contact_email_reason && <p className="faint small" style={{ marginTop: 8 }}>{row.contact_email_reason}</p>}
          </div>
        )}

        <div>
          <div className="section-title">Phones</div>
          {phones.length ? (
            <div className="list">
              {phones.map(([number, kind]) => (
                <div key={number} className="list-item">
                  <span className="row" style={{ gap: 8 }}>
                    {kind === "mobile" ? <Smartphone size={14} className="faint" /> : <Phone size={14} className="faint" />}
                    {number}
                  </span>
                  {kind && <span className={`badge ${kind === "mobile" ? "pink" : "grey"}`}>{kind}</span>}
                </div>
              ))}
            </div>
          ) : <p className="faint small">No phone found.</p>}
          {row.mobile_only === "yes" && (
            <p className="faint small" style={{ marginTop: 8 }}>Only a mobile: often a sign of someone working alone.</p>
          )}
          <p className="faint small" style={{ marginTop: 6 }}>Screen against the TPS and CTPS before calling.</p>
        </div>

        {socials.length > 0 && (
          <div>
            <div className="section-title">Social links</div>
            <div className="chips">
              {socials.map((s) => (
                <a key={s} className="chip" href={s} target="_blank" rel="noreferrer">
                  {socialName(s)} <ExternalLink size={12} />
                </a>
              ))}
            </div>
          </div>
        )}

        <div>
          <div className="section-title">Business</div>
          <dl className="kv">
            <dt>Address</dt>
            <dd>{[row.address, row.town, row.postcode].filter(Boolean).join(", ") || "Not known"}</dd>
            {row.website && (<><dt>Website</dt><dd><a href={row.website} target="_blank" rel="noreferrer" style={{ color: "var(--accent-2)" }}>{row.website}</a></dd></>)}
            <dt>Company</dt>
            <dd>{row.company_number ? `${row.company_name} (${row.company_number}), ${row.company_type}` : "Not matched to Companies House"}</dd>
            {row.company_match && (<><dt>How matched</dt><dd>{row.company_match}</dd></>)}
            {row.email_pattern && (<><dt>Email pattern</dt><dd>{row.email_pattern}</dd></>)}
            {row.mail_server && (<><dt>Takes email</dt><dd>{row.mail_server}</dd></>)}
            {row.email_found_on && (<><dt>Email found on</dt><dd style={{ wordBreak: "break-all" }}>{row.email_found_on}</dd></>)}
            <dt>Source</dt>
            <dd>{row.source}</dd>
          </dl>
          {mapUrl && (
            <a className="btn small" href={mapUrl} target="_blank" rel="noreferrer" style={{ marginTop: 12 }}>
              <MapPin size={14} /> Show on the map
            </a>
          )}
        </div>
      </aside>
    </>
  );
}

export default function Results({ slug, projects }: { slug: string; projects: Project[] }) {
  const project = projects.find((p) => p.targets.some((t) => t.slug === slug));
  const target = project?.targets.find((t) => t.slug === slug);
  const [q, setQ] = useState("");
  const [typed, setTyped] = useState("");
  const [sector, setSector] = useState("");
  const [rule, setRule] = useState("");
  const [has, setHas] = useState<string[]>([]);
  const [sort, setSort] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<ResultsData | null>(null);
  const [error, setError] = useState("");
  const [open, setOpen] = useState<Row | null>(null);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setQ(typed), 250);
    return () => clearTimeout(t);
  }, [typed]);

  const query = useMemo(() => {
    const p = new URLSearchParams();
    if (q) p.set("q", q);
    if (sector) p.set("sector", sector);
    if (rule) p.set("rule", rule);
    has.forEach((h) => p.append("has", h));
    if (sort) p.set("sort", sort);
    return p;
  }, [q, sector, rule, has, sort]);

  useEffect(() => setPage(1), [query]);
  useEffect(() => {
    const p = new URLSearchParams(query);
    p.set("page", String(page));
    p.set("size", "50");
    api.results(slug, p).then((d) => { setData(d); setError(""); }, (e) => setError(e.message));
  }, [slug, query, page]);

  const s = data?.summary;
  const f = data?.filtered;
  const pages = data ? Math.max(1, Math.ceil(data.total / data.size)) : 1;
  const toggle = (h: string) => setHas((now) => (now.includes(h) ? now.filter((x) => x !== h) : [...now, h]));
  const sortBy = (key: string) => setSort(sort === key ? `-${key}` : sort === `-${key}` ? "" : key);

  return (
    <>
      <div className="page-head">
        <div>
          <div className="crumbs">
            <a href="#/">Projects</a> /
            {project && <a href={`#/p/${project.slug}`}>{project.name}</a>} / {target?.name ?? slug}
          </div>
          <h1>{target && <span style={{ marginRight: 10 }}>{FLAGS[target.country] ?? "🌍"}</span>}{target?.name ?? slug}</h1>
          {s?.file && <p className="lede small">From {s.file}, updated {s.updated}</p>}
        </div>
        <div className="row">
          <a className="btn" href={`#/t/${slug}/edit`}><Pencil size={15} /> Edit list</a>
          <button className="btn go" onClick={() => setRunning(true)} disabled={target?.running}>
            <Play size={15} /> {target?.running ? "Running…" : "Run"}
          </button>
          <a className="btn primary" href={api.exportUrl(slug, query)}>
            <Download size={15} /> Export {data && data.total !== s?.total ? `${fmt(data.total)} rows` : "spreadsheet"}
          </a>
        </div>
      </div>

      {error && <div className="notice bad">{error}</div>}
      {s && s.total === 0 && (
        <div className="card empty">
          No results yet. Press <b>Run</b> to search for these businesses.
        </div>
      )}

      {s && s.total > 0 && (
        <>
          <div className="stats" style={{ marginBottom: 18 }}>
            <div className="stat"><b>{fmt(s.total)}</b><span>businesses</span></div>
            <div className="stat green"><b>{fmt(s.can_email)}</b><span>can email ({pct(s.can_email, s.total)})</span></div>
            <div className="stat amber"><b>{fmt(s.post_only)}</b><span>post only</span></div>
            <div className="stat blue"><b>{fmt(s.with_email)}</b><span>emails found ({pct(s.with_email, s.total)})</span></div>
            <div className="stat pink"><b>{fmt(s.ready)}</b><span>ready to email</span></div>
            <div className="stat"><b>{fmt(s.with_phone)}</b><span>with a phone</span></div>
            <div className="stat"><b>{fmt(s.with_socials)}</b><span>with socials</span></div>
            <div className="stat"><b>{fmt(s.with_person)}</b><span>named people</span></div>
          </div>

          <div className="card stack" style={{ marginBottom: 18 }}>
            <div className="spread">
              <h3>By kind of business</h3>
              <span className="row small muted">
                <span className="badge can">can email</span><span className="badge post">post only</span>
              </span>
            </div>
            <div className="stack" style={{ gap: 10 }}>
              {Object.entries(s.sectors).sort((a, b) => b[1].total - a[1].total).map(([name, v]) => (
                <button key={name} className="btn ghost" style={{ display: "grid", gridTemplateColumns: "200px 1fr 120px", gap: 14, padding: "4px 6px", textAlign: "left" }}
                  onClick={() => setSector(sector === name ? "" : name)}>
                  <span style={{ color: sector === name ? "var(--text)" : undefined }}>{name}</span>
                  <span className="bar" style={{ alignSelf: "center" }}>
                    <i style={{ width: pct(v.can_email, s.total), background: "var(--green)" }} />
                    <i style={{ width: pct(v.total - v.can_email, s.total), background: "var(--amber)" }} />
                  </span>
                  <span className="small" style={{ textAlign: "right" }}>{fmt(v.total)}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="stack" style={{ marginBottom: 14 }}>
            <div className="row">
              <div className="search" style={{ flex: "1 1 260px" }}>
                <Search size={16} />
                <input className="input" placeholder="Search by name, town, postcode, email…" value={typed} onChange={(e) => setTyped(e.target.value)} />
              </div>
              <select className="input select" style={{ width: 220 }} value={sector} onChange={(e) => setSector(e.target.value)}>
                <option value="">Every kind of business</option>
                {Object.keys(s.sectors).map((name) => <option key={name}>{name}</option>)}
              </select>
            </div>
            <div className="row">
              <div className="chips">
                {RULES.map(([v, label]) => (
                  <button key={label} className={`chip ${rule === v ? "on" : ""}`} onClick={() => setRule(v)}>{label}</button>
                ))}
              </div>
              <span className="faint">|</span>
              <div className="chips">
                {HAS.map(([v, label]) => (
                  <button key={v} className={`chip ${has.includes(v) ? "on" : ""}`} onClick={() => toggle(v)}>{label}</button>
                ))}
              </div>
            </div>
            {f && data && data.total !== s.total && (
              <div className="small muted">
                Showing {fmt(data.total)} of {fmt(s.total)}: {fmt(f.can_email)} can email, {fmt(f.with_email)} with an email.
              </div>
            )}
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  {SORTS.map(([key, label]) => (
                    <th key={key} onClick={() => sortBy(key)}>
                      {label} {sort === key ? <ArrowUp size={12} /> : sort === `-${key}` ? <ArrowDown size={12} /> : null}
                    </th>
                  ))}
                  <th onClick={() => sortBy("phone")}>Phone</th>
                  <th onClick={() => sortBy("contact_name")}>Person</th>
                  <th>Links</th>
                </tr>
              </thead>
              <tbody>
                {data?.rows.map((row) => {
                  const extra = labelled(row.all_emails).filter(([a]) => a !== row.email).length;
                  return (
                    <tr key={row.key} onClick={() => setOpen(row)}>
                      <td>
                        <div className="name">{row.name}</div>
                        <div className="cell-sub">{row.sector}</div>
                      </td>
                      <td>
                        {row.town}
                        <div className="cell-sub">{row.postcode}</div>
                      </td>
                      <td><RuleBadge rule={row.contact_rule} /></td>
                      <td>
                        {row.email ? (
                          <>
                            <div className="email-line"><Score value={row.email_confidence} /> <span>{row.email}</span></div>
                            <div className="cell-sub row" style={{ gap: 6, marginTop: 4 }}>
                              <EmailKind kind={row.email_type} />
                              {extra > 0 && <span>+{extra} more</span>}
                            </div>
                          </>
                        ) : <span className="faint">None found</span>}
                      </td>
                      <td>
                        {row.phone && (
                          <div className="row" style={{ gap: 6, flexWrap: "nowrap" }}>
                            {row.phone_type === "mobile" ? <Smartphone size={13} className="faint" /> : <Phone size={13} className="faint" />}
                            <span style={{ whiteSpace: "nowrap" }}>{row.phone}</span>
                          </div>
                        )}
                        {row.mobile_only === "yes" && <div className="cell-sub">mobile only</div>}
                      </td>
                      <td>
                        {row.contact_name || <span className="faint">-</span>}
                        {row.contact_role && <div className="cell-sub">{row.contact_role}</div>}
                      </td>
                      <td>
                        <div className="icons" onClick={(e) => e.stopPropagation()}>
                          {row.website && <a href={row.website} target="_blank" rel="noreferrer" title="Website"><Globe size={16} /></a>}
                          {row.company_number && <span title={`${row.company_name} (${row.company_type})`}><Building2 size={16} /></span>}
                          {row.socials && <span className="small" title={row.socials}>{row.socials.split(/\s+/).filter(Boolean).length} social</span>}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {data && data.rows.length === 0 && <div className="empty">Nothing matches those filters.</div>}
          </div>
          <div className="pager">
            <span>Page {page} of {fmt(pages)}</span>
            <button className="btn small" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button>
            <button className="btn small" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</button>
          </div>
        </>
      )}
      {open && <Details row={open} onClose={() => setOpen(null)} />}
      {running && target && <RunPanel target={target} onClose={() => setRunning(false)} />}
    </>
  );
}
