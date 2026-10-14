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
  founded: { year: number; count: number }[];
  trades: { trade: string; name: string }[];
  money: Money;
  shown: number;
  points: Place[];
};

export type Heat = {
  available: boolean;
  founded: { year: number; count: number }[];
  trades: { trade: string; name: string }[];
  districts: { district: string; lat: number; lon: number; count: number; may_email: number }[];
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
  map: (query: URLSearchParams) => call<MapResults>("GET", `map?${query}`),
  heat: (query: URLSearchParams) => call<Heat>("GET", `map/heat?${query}`),
  mapExportUrl: (query: URLSearchParams) => `/api/map/export?${query}`,
  categories: (country: string, words: string[]) =>
    call<{ category: string; places: number }[]>("POST", "categories", { country, words }),
};
