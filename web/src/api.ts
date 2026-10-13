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
  categories: (country: string, words: string[]) =>
    call<{ category: string; places: number }[]>("POST", "categories", { country, words }),
};
