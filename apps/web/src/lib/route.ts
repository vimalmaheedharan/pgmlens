// Tiny hash router: #/  ·  #/p/<program>/<tab>?risk=<finding id>

export type Tab = "overview" | "dependencies" | "risks" | "briefing";
export const TABS: { id: Tab; label: string; key: string }[] = [
  { id: "overview", label: "Overview", key: "o" },
  { id: "dependencies", label: "Dependencies", key: "d" },
  { id: "risks", label: "Risks", key: "r" },
  { id: "briefing", label: "Briefing", key: "b" },
];

export interface Route {
  programId: string | null;
  tab: Tab;
  riskId: string | null;
}

const isTab = (value: string | undefined): value is Tab => TABS.some((t) => t.id === value);

export function parseRoute(hash: string): Route {
  const [path, query = ""] = hash.replace(/^#/, "").split("?");
  const parts = path.split("/").filter(Boolean);
  const riskId = new URLSearchParams(query).get("risk");
  if (parts[0] !== "p" || !parts[1]) return { programId: null, tab: "overview", riskId: null };
  return {
    programId: decodeURIComponent(parts[1]),
    tab: isTab(parts[2]) ? parts[2] : "overview",
    riskId,
  };
}

export function buildHash(route: Partial<Route>): string {
  if (!route.programId) return "#/";
  const base = `#/p/${encodeURIComponent(route.programId)}/${route.tab ?? "overview"}`;
  return route.riskId ? `${base}?risk=${encodeURIComponent(route.riskId)}` : base;
}
