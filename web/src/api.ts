// Talks to Recon's own server (recon/server.py). Every change carries the
// X-Recon header, which the server asks for so other web pages can't act.

export type Sector = { overture: string[]; osm: [string, string][]; sic: string[] };

export type TargetList = {
  name: string;
  project: string;
  country: string;
  notes: string;
  sectors: Record<string, Sector>;
  box?: number[];
};

export type Summary = {
  file: string | null;
  updated: string | null;
  total: number;
  can_email: number;
  post_only: number;
  check: number;
  with_email: number;
  ready: number;
  with_person: number;
  with_phone: number;
  mobile_only: number;
  with_socials: number;
  sectors: Record<string, { total: number; can_email: number; ready: number }>;
};

export type TargetCard = {
  slug: string;
  name: string;
  project: string;
  country: string;
  notes: string;
  sectors: string[];
  results: Summary | null;
  running: boolean;
};

export type Project = { slug: string; name: string; description: string; targets: TargetCard[] };

export type Row = Record<string, string>;

export type Results = {
  total: number;
  page: number;
  size: number;
  rows: Row[];
  summary: Summary;
  filtered: Summary;
};

export type Run = {
  id: string;
  target: string;
  step: string;
  started: number;
  finished: number | null;
  status: "running" | "finished" | "failed" | "stopped";
  log?: string;
};

export type Setup = {
  duckdb: boolean;
  companies_house_key: boolean;
  hunter_key: boolean;
  companies_house_files: string[];
  countries: { code: string; name: string }[];
  ready_score: number;
};

export type MasterArea = { area: string; organisations?: number; with_email?: number; may_email?: number; with_phone?: number; with_website?: number };

export type MasterSource = { name: string; title: string; country: string; url: string; licence: string; records: string; with_email: string };

export type MasterStatus = {
  available: boolean;
  folder: string | null;
  groups?: Record<string, MasterArea[]>;
  sources?: MasterSource[];
};

export type MasterResults = {
  total: number;
  with_email: number;
  may_email: number;
  with_phone: number;
  with_website: number;
  page: number;
  size: number;
  by_area: { area: string; count: number }[];
  by_source: { source: string; count: number }[];
  rows: Row[];
  // Set when the search is limited to a circle around a postcode or town.
  circle: { lat: number; lon: number; miles: number; label: string } | null;
  // On the first page: how many matches have a position, and up to 3,000 of them for the map.
  placed: number;
  points: Row[];
};

export type AreaCounts = { area: string; organisations: number; with_email: number; may_email: number; with_phone: number; with_website: number };
export type CountryCounts = { totals: Partial<Omit<AreaCounts, "area">>; areas: AreaCounts[] };
export type Money = {
  available: boolean;
  total?: number;
  registered?: number;
  publishes_turnover?: number;
  with_net_assets?: number;
  with_staff?: number;
  size_bands?: { band: string; count: number }[];
  account_types?: { type: string; count: number }[];
};
export type TradeSummary = Record<string, number> & { trade: string };

export type Overview = {
  available: boolean;
  countries?: Record<string, CountryCounts>;
  sources?: { name: string; title: string; country: string; licence: string; url: string; records: number; with_email: number }[];
  trades?: TradeSummary[];
  money?: Money;
};

// New UK companies each month, and the last 30 days against the 30 before.
export type Growth = {
  available: boolean;
  as_of?: string;
  last_30?: number;
  prior_30?: number;
  months?: { month: string; count: number }[];
};

export type Place = Record<string, string> & { lat: number; lon: number; miles?: number };

export type MapResults = {
  available: boolean;
  centre: { lat: number; lon: number; label: string; matched: string } | null;
  miles: number;
  total: number;
  with_email: number;
  may_email: number;
  with_phone: number;
  with_mobile: number;
  with_website: number;
  by_trade: { trade: string; name: string; count: number }[];
  by_district: { district: string; count: number; may_email: number }[];
  founded?: { year: number; count: number }[];
  trades?: { trade: string; name: string }[];
  money: Money;
  shown: number;
  points: Place[];
};

// Every organisation sorted into sectors, then industries, then niches.
export type Niche = { niche: string; name: string; count: number };
export type Industry = { industry: string; name: string; count: number; niches: Niche[] };
export type SectorNode = { sector: string; name: string; count: number; may_email: number; industries: Industry[] };
export type SectorTree = { available: boolean; total: number; sectors: SectorNode[] };

export type Heat = {
  available: boolean;
  founded: { year: number; count: number }[];
  trades: { trade: string; name: string }[];
  districts: { district: string; lat: number; lon: number; count: number; may_email: number; with_email?: number; with_phone?: number }[];
};

// Ask Recon: a plain question answered from the sector index.
export type Answer = {
  answer: string;
  figures?: { total: number; may_email: number; with_email: number; with_phone: number };
  districts?: Heat["districts"];
  map?: Record<string, string[]>;
  understood: { sector?: string | null; niche?: string | null; place?: string | null; miles?: number | null; rule?: string | null; has?: string[] };
};

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await fetch("/api/" + path, {
    method,
    headers: method === "GET" ? {} : { "Content-Type": "application/json", "X-Recon": "1" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `Recon said ${response.status}`);
  return data as T;
}

export const api = {
  setup: () => call<Setup>("GET", "setup"),
  projects: () => call<Project[]>("GET", "projects"),
  createProject: (p: { name: string; description: string }) =>
    call<{ slug: string }>("POST", "projects", p),
  saveProject: (slug: string, p: { name: string; description: string }) =>
    call<{ slug: string }>("PUT", `projects/${slug}`, p),
  target: (slug: string) => call<TargetList>("GET", `targets/${slug}`),
  createTarget: (t: TargetList) => call<{ slug: string }>("POST", "targets", t),
  saveTarget: (slug: string, t: TargetList) => call<{ slug: string }>("PUT", `targets/${slug}`, t),
  results: (slug: string, query: URLSearchParams) =>
    call<Results>("GET", `targets/${slug}/results?${query}`),
  exportUrl: (slug: string, query: URLSearchParams) => `/api/targets/${slug}/export?${query}`,
  runs: () => call<Run[]>("GET", "runs"),
  run: (id: string) => call<Run>("GET", `runs/${id}`),
  startRun: (target: string, step: string, options: Record<string, unknown>) =>
    call<Run>("POST", "runs", { target, step, options }),
  stopRun: (id: string) => call<Run>("POST", `runs/${id}/stop`),
  master: () => call<MasterStatus>("GET", "master"),
  masterSearch: (query: URLSearchParams) => call<MasterResults>("GET", `master/search?${query}`),
  masterKinds: (group: string) => call<{ kind: string; count: number }[]>("GET", `master/kinds?group=${group}`),
  masterExportUrl: (query: URLSearchParams) => `/api/master/export?${query}`,
  overview: () => call<Overview>("GET", "overview"),
  growth: () => call<Growth>("GET", "overview/growth"),
  map: (query: URLSearchParams) => call<MapResults>("GET", `map?${query}`),
  heat: (query: URLSearchParams) => call<Heat>("GET", `map/heat?${query}`),
  sectors: (group: string) => call<SectorTree>("GET", `sectors?group=${group}`),
  sectorHeat: (query: URLSearchParams) => call<Heat>("GET", `sectors/heat?${query}`),
  ask: (text: string) => call<Answer>("POST", "ask", { text }),
  mapExportUrl: (query: URLSearchParams) => `/api/map/export?${query}`,
  categories: (country: string, words: string[]) =>
    call<{ category: string; places: number }[]>("POST", "categories", { country, words }),
};

// The small CRM: saved lists, today's calls, a status and notes for each business.
export type SavedList = {
  id: number; name: string; project: string; notes: string; query: Record<string, string[]>;
  created: string; updated: string; businesses: number; contacted: number; with_phone: number; may_email: number;
};
export type Saved = {
  id: string; name: string; kind: string; address: string; town: string; postcode: string;
  phone: string; mobile: string; email: string; website: string; rule: string; sources: string; country: string;
  lat: string; lon: string; updated: string;
  status: string; note: string; call_back: string | null; status_updated?: string | null; blocked: number | boolean;
};
export type ListDetail = Omit<SavedList, "businesses" | "contacted" | "with_phone" | "may_email"> & { items: (Saved & { added: string })[] };
export type Activity = { id: number; at: string; kind: string; outcome: string; note: string; seconds: number | null; recording: string; call_id: string };
export type Business = Saved & { history: Activity[]; lists: { id: number; name: string }[]; screening: string };
export type Call = Saved & { dial: string; mobile_number: boolean; screening: string; why: string; calls: number; last_call: string | null; lists: string };
export type Blocked = { id: number; business: string; phone: string; email: string; name: string; reason: string; at: string };
export type SavedNiche = { id: number; name: string; country: string; query: Record<string, string[]>; created: string };
export type CallingSetup = {
  provider: string; configured: boolean; missing: string[]; webhook_protected: boolean; caller_id: string;
  unscreened: number; steps: string[];
};
export type CrmSummary = {
  lists: number; businesses: number; contacted: number; interested: number; customers: number;
  call_backs_due: number; do_not_contact: number; calls_today: number; niches: number;
};

export const crm = {
  summary: () => call<CrmSummary>("GET", "crm"),
  lists: () => call<SavedList[]>("GET", "lists"),
  list: (id: number) => call<ListDetail>("GET", `lists/${id}`),
  createList: (body: { name: string; project?: string; notes?: string; query?: Record<string, string[]>; items?: Row[] }) =>
    call<ListDetail>("POST", "lists", body),
  updateList: (id: number, body: { name?: string; project?: string; notes?: string }) => call<ListDetail>("PUT", `lists/${id}`, body),
  deleteList: (id: number) => call<{ deleted: number }>("DELETE", `lists/${id}`),
  addItems: (id: number, items: Row[]) => call<{ added: number; list: ListDetail }>("POST", `lists/${id}/items`, { items }),
  removeItem: (id: number, business: string) => call<{ removed: string }>("DELETE", `lists/${id}/items/${encodeURIComponent(business)}`),
  exportUrl: (id: number) => `/api/lists/${id}/export`,
  today: (list: number | null, count = 10) => call<Call[]>("GET", `today?count=${count}${list ? `&list=${list}` : ""}`),
  business: (id: string) => call<Business>("GET", `contacts/${encodeURIComponent(id)}`),
  save: (id: string, row: Row) => call<Business>("POST", `contacts/${encodeURIComponent(id)}/save`, row),
  log: (id: string, body: { outcome: string; note?: string; call_back?: string }) =>
    call<Business>("POST", `contacts/${encodeURIComponent(id)}/log`, body),
  blocked: () => call<Blocked[]>("GET", "blocked"),
  block: (body: { business?: string; phone?: string; email?: string; name?: string; reason?: string }) => call<Blocked[]>("POST", "blocked", body),
  unblock: (id: number) => call<{ deleted: number }>("DELETE", `blocked/${id}`),
  niches: () => call<SavedNiche[]>("GET", "niches"),
  saveNiche: (name: string, query: Record<string, string[]>, country: string) => call<SavedNiche[]>("POST", "niches", { name, query, country }),
  deleteNiche: (id: number) => call<SavedNiche[]>("DELETE", `niches/${id}`),
  screening: (list: number | null) => call<{ unscreened: string[] }>("GET", `screening${list ? `?list=${list}` : ""}`),
  recordScreening: (rows: { phone: string; result: string }[], source: string) => call<{ saved: number }>("POST", "screening", { rows, source }),
  callingSetup: () => call<CallingSetup>("GET", "calls/setup"),
  callCheck: (business: string) => call<{ reason: string }>("GET", `calls/check?business=${encodeURIComponent(business)}`),
  startCall: (business: string) => call<{ call_id: string; to: string; business: string }>("POST", "calls/start", { business }),
};
