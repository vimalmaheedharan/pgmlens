import type { ReactNode } from "react";
import type { ProgramSummary } from "../types";
import { LensMark } from "./Marks";

interface Props {
  programs: ProgramSummary[];
  currentId: string | null;
  onSelect: (id: string | null) => void;
  onHelp: () => void;
  children: ReactNode;
}

export function Shell({ programs, currentId, onSelect, onHelp, children }: Props) {
  return (
    <>
      <button type="button" className="skip" onClick={() => document.getElementById("main")?.focus()}>
        Skip to content
      </button>
      <header className="topbar noprint">
        <a className="brand" href="#/" onClick={() => onSelect(null)}>
          <LensMark />
          <span>PGM Lens</span>
        </a>
        {programs.length > 1 && (
          <label className="switcher">
            <span className="sr-only">Program</span>
            <select value={currentId ?? ""} onChange={(e) => onSelect(e.target.value || null)}>
              <option value="">All programs</option>
              {programs.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
        )}
        <span className="spacer" />
        <button type="button" className="quiet" onClick={onHelp} aria-haspopup="dialog">
          Shortcuts
        </button>
      </header>
      <main id="main" tabIndex={-1}>
        {children}
      </main>
    </>
  );
}
