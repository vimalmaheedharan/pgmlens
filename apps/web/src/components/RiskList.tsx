import type { Finding } from "../types";
import { SeverityMark } from "./Marks";

interface Props {
  findings: Finding[];
  activeId: string | null;
  onOpen: (id: string) => void;
  emptyText?: string;
}

export function RiskList({ findings, activeId, onOpen, emptyText = "No risks detected." }: Props) {
  if (findings.length === 0) return <p className="muted">{emptyText}</p>;
  return (
    <ul className="risks">
      {findings.map((f) => (
        <li key={f.id}>
          <button type="button" className={`risk ${f.id === activeId ? "active" : ""}`} onClick={() => onOpen(f.id)} aria-label={`${f.severity} risk: ${f.title}. Open details.`}>
            <SeverityMark severity={f.severity} />
            <span className="risk-body">
              <span className="risk-title">{f.title}</span>
              <span className="risk-message">{f.message}</span>
              {f.issue_keys.length > 0 && (
                <span className="risk-keys small muted">
                  {f.issue_keys.slice(0, 6).join(", ")}
                  {f.issue_keys.length > 6 ? ` and ${f.issue_keys.length - 6} more` : ""}
                </span>
              )}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}
