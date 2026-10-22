import { useEffect, useRef } from "react";
import { humanizeKey, humanizeValue, statusLabel } from "../lib/format";
import type { Finding, Issue } from "../types";
import { SeverityMark } from "./Marks";

interface Props {
  finding: Finding;
  issues: Map<string, Issue>;
  onClose: () => void;
}

function ago(days: number): string {
  if (days <= 0) return "today";
  return days === 1 ? "1 day ago" : `${days} days ago`;
}

export function RiskDrawer({ finding, issues, onClose }: Props) {
  const panel = useRef<HTMLElement>(null);

  // Move focus into the panel, and give it back to whatever opened it.
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    panel.current?.focus();
    return () => previous?.focus?.();
  }, [finding.id]);

  const involved = finding.issue_ids.map((id) => issues.get(id)).filter((i): i is Issue => Boolean(i));
  const metrics = Object.entries(finding.metrics).filter(([, v]) => typeof v !== "object" || v === null);

  return (
    <>
      <div className="scrim" onClick={onClose} aria-hidden="true" />
      <aside className="drawer" role="dialog" aria-modal="false" aria-labelledby="drawer-title" tabIndex={-1} ref={panel}>
        <header className="drawer-head">
          <SeverityMark severity={finding.severity} />
          <button type="button" className="quiet" onClick={onClose}>
            Close
          </button>
        </header>
        <h2 id="drawer-title">{finding.title}</h2>

        <section>
          <h3>Why this was flagged</h3>
          <p>{finding.message}</p>
        </section>

        {finding.action && (
          <section>
            <h3>What to do</h3>
            <p>{finding.action}</p>
          </section>
        )}

        {involved.length > 0 && (
          <section>
            <h3>Issues involved</h3>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th scope="col">Issue</th>
                    <th scope="col">Status</th>
                    <th scope="col">Owner</th>
                    <th scope="col">Last update</th>
                  </tr>
                </thead>
                <tbody>
                  {involved.map((issue) => (
                    <tr key={issue.id}>
                      <th scope="row">
                        {issue.url ? (
                          <a href={issue.url} target="_blank" rel="noopener noreferrer">
                            {issue.key}
                          </a>
                        ) : (
                          issue.key
                        )}
                        <span className="issue-title">{issue.title}</span>
                      </th>
                      <td>{statusLabel[issue.status]}</td>
                      <td>{issue.assignee ?? <span className="tone-alarm">No owner</span>}</td>
                      <td>{ago(issue.days_since_update)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {metrics.length > 0 && (
          <section>
            <h3>By the numbers</h3>
            <dl className="facts">
              {metrics.map(([key, value]) => (
                <div key={key}>
                  <dt>{humanizeKey(key)}</dt>
                  <dd>{humanizeValue(value)}</dd>
                </div>
              ))}
            </dl>
          </section>
        )}

        <section>
          <h3>How it was detected</h3>
          <p className="muted small">
            Rule <code>{finding.rule_id}</code> (check type <code>{finding.rule_type}</code>). Rules are plain YAML, so thresholds can be tuned without changing code.
          </p>
        </section>
      </aside>
    </>
  );
}
