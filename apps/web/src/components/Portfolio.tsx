import { shortDate } from "../lib/format";
import type { ProgramSummary } from "../types";
import { HealthMark } from "./Marks";

export function Portfolio({ programs, onOpen }: { programs: ProgramSummary[]; onOpen: (id: string) => void }) {
  if (programs.length === 0) {
    return (
      <section className="page narrow">
        <h1>No programs yet</h1>
        <p>PGM Lens has nothing to show. Pick one of these to get started:</p>
        <ul className="plain-list">
          <li>
            Start the API with <code>PGMLENS_DEMO=1</code> to explore a synthetic program.
          </li>
          <li>
            Generate a dataset with <code>pgmlens demo --out demo.json</code>, then send it to <code>POST /api/programs</code>.
          </li>
          <li>Pull your own data with the Jira or GitLab connector and post the result the same way.</li>
        </ul>
      </section>
    );
  }
  return (
    <section className="page">
      <h1>Programs</h1>
      <ul className="portfolio">
        {programs.map((p) => (
          <li key={p.id}>
            <button type="button" className="portfolio-row" onClick={() => onOpen(p.id)}>
              <span className="portfolio-name">{p.name}</span>
              <HealthMark status={p.health.status} label={p.health.label} />
              <span className="portfolio-line">
                {p.next_milestone
                  ? `${p.next_milestone.scope_name}, due ${shortDate(p.next_milestone.due_date)}: ${p.next_milestone.summary.toLowerCase()}`
                  : p.health.headline}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
