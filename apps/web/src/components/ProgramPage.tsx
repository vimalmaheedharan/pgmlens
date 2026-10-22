import { useEffect, useMemo, useRef, useState } from "react";
import { useFetch } from "../hooks";
import { fullDate, severityLabel, severityOrder } from "../lib/format";
import { leadSentence } from "../lib/narrative";
import { TABS, type Route, type Tab } from "../lib/route";
import type { Finding, ProgramDetail, Severity } from "../types";
import { BriefingView } from "./BriefingView";
import { DependencyMap } from "./DependencyMap";
import { ForecastTimeline } from "./ForecastTimeline";
import { HealthMark } from "./Marks";
import { RiskDrawer } from "./RiskDrawer";
import { RiskList } from "./RiskList";

interface Props {
  programId: string;
  tab: Tab;
  riskId: string | null;
  searchRequest: number;
  navigate: (route: Partial<Route>) => void;
}

export function ProgramPage({ programId, tab, riskId, searchRequest, navigate }: Props) {
  const { data, error, loading, reload } = useFetch<ProgramDetail>(`/api/programs/${encodeURIComponent(programId)}`);

  useEffect(() => {
    document.title = data ? `${data.summary.name} - PGM Lens` : "PGM Lens";
  }, [data]);

  const issues = useMemo(() => new Map((data?.issues ?? []).map((i) => [i.id, i])), [data]);

  if (error) {
    return (
      <section className="page narrow">
        <div className="notice" role="alert">
          <p>{error}</p>
          <button type="button" onClick={reload}>
            Try again
          </button>
        </div>
      </section>
    );
  }
  if (!data) {
    return (
      <section className="page" aria-busy={loading}>
        <p className="muted">Loading the program…</p>
      </section>
    );
  }

  const open = (id: string) => navigate({ programId, tab, riskId: id });
  const close = () => navigate({ programId, tab, riskId: null });
  const activeFinding = data.analysis.findings.find((f) => f.id === riskId);

  return (
    <section className="page">
      <header className="page-head">
        <h1>{data.summary.name}</h1>
        <span className="muted small">Updated {fullDate(data.summary.as_of)}</span>
      </header>

      <nav className="tabs noprint" aria-label="Program sections">
        {TABS.map((t) => (
          <a key={t.id} href={`#/p/${encodeURIComponent(programId)}/${t.id}`} aria-current={t.id === tab ? "page" : undefined}>
            {t.label}
            {t.id === "risks" && <span className="count">{data.analysis.findings.length}</span>}
          </a>
        ))}
      </nav>

      {tab === "overview" && <Overview detail={data} activeId={riskId} onOpen={open} onSeeAll={() => navigate({ programId, tab: "risks" })} />}
      {tab === "dependencies" && <DependencyMap detail={data} />}
      {tab === "risks" && <Risks findings={data.analysis.findings} activeId={riskId} onOpen={open} searchRequest={searchRequest} />}
      {tab === "briefing" && <BriefingView programId={programId} />}

      {activeFinding && <RiskDrawer finding={activeFinding} issues={issues} onClose={close} />}
    </section>
  );
}

function Overview({ detail, activeId, onOpen, onSeeAll }: { detail: ProgramDetail; activeId: string | null; onOpen: (id: string) => void; onSeeAll: () => void }) {
  const [showNumbers, setShowNumbers] = useState(false);
  const { health, stats, forecasts, findings } = detail.analysis;
  const lead = leadSentence(forecasts, health.headline.replace(/^[^:]+:\s*/, "").replace(/^./, (c) => c.toUpperCase()) + ".");
  // Milestone slips are already drawn in the timeline above; lead with the other findings.
  const others = findings.filter((f) => f.rule_type !== "milestone_slip");
  const attention = others.length > 0 ? others : findings;
  return (
    <>
      <div className="statement">
        <HealthMark status={health.status} label={health.label} />
        <p className="lead">{lead}</p>
        <p className="muted">
          {stats.open} open issues, {stats.done} done. {stats.blocked} blocked and {stats.unassigned_open} without an owner.
        </p>
      </div>

      <section aria-labelledby="when">
        <div className="section-head">
          <h2 id="when">When will it finish?</h2>
          <label className="check">
            <input type="checkbox" checked={showNumbers} onChange={(e) => setShowNumbers(e.target.checked)} />
            Show the numbers behind the forecast
          </label>
        </div>
        <ForecastTimeline forecasts={forecasts} asOf={detail.summary.as_of} showNumbers={showNumbers} />
      </section>

      <section aria-labelledby="attention">
        <div className="section-head">
          <h2 id="attention">What needs attention?</h2>
          {attention.length > 3 && (
            <button type="button" className="quiet" onClick={onSeeAll}>
              See all {findings.length} risks
            </button>
          )}
        </div>
        <RiskList findings={attention.slice(0, 3)} activeId={activeId} onOpen={onOpen} emptyText="Nothing needs attention right now." />
      </section>
    </>
  );
}

function Risks({ findings, activeId, onOpen, searchRequest }: { findings: Finding[]; activeId: string | null; onOpen: (id: string) => void; searchRequest: number }) {
  const [severity, setSeverity] = useState<Severity | "all">("all");
  const [query, setQuery] = useState("");
  const search = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (searchRequest > 0) search.current?.focus();
  }, [searchRequest]);

  const counts = useMemo(() => {
    const c: Record<string, number> = { all: findings.length };
    for (const f of findings) c[f.severity] = (c[f.severity] ?? 0) + 1;
    return c;
  }, [findings]);

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return findings.filter(
      (f) =>
        (severity === "all" || f.severity === severity) &&
        (!q || [f.title, f.message, f.rule_id, ...f.issue_keys].some((s) => s.toLowerCase().includes(q))),
    );
  }, [findings, severity, query]);

  return (
    <section aria-labelledby="all-risks">
      <h2 id="all-risks" className="sr-only">
        All risks
      </h2>
      <div className="filters">
        <div role="group" aria-label="Filter by severity" className="chips">
          {(["all", ...severityOrder] as const).map((s) => (
            <button key={s} type="button" aria-pressed={severity === s} disabled={s !== "all" && !counts[s]} onClick={() => setSeverity(s)}>
              {s === "all" ? "All" : severityLabel[s]} <span className="count">{counts[s] ?? 0}</span>
            </button>
          ))}
        </div>
        <label className="search">
          <span className="sr-only">Search risks</span>
          <input ref={search} type="search" placeholder="Search by issue, rule or wording" value={query} onChange={(e) => setQuery(e.target.value)} />
        </label>
      </div>
      <p className="sr-only" role="status">
        {shown.length} risks shown
      </p>
      <RiskList findings={shown} activeId={activeId} onOpen={onOpen} emptyText="No risks match. Clear the search or pick a different severity." />
    </section>
  );
}
