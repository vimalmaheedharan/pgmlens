import { useEffect, useState } from "react";
import { useFetch } from "../hooks";
import type { BriefingOut } from "../types";

export function BriefingView({ programId }: { programId: string }) {
  const [useAi, setUseAi] = useState(false);
  const [active, setActive] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const { data, error, loading, reload } = useFetch<BriefingOut>(`/api/programs/${encodeURIComponent(programId)}/briefing?llm=${useAi}`);

  useEffect(() => {
    if (!active) return;
    document.getElementById(`fact-${active}`)?.scrollIntoView({ block: "center", behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  }, [active]);

  async function copy() {
    if (!data) return;
    try {
      await navigator.clipboard.writeText(data.markdown);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }

  if (error) {
    return (
      <div className="notice" role="alert">
        <p>{error}</p>
        <button type="button" onClick={reload}>
          Try again
        </button>
      </div>
    );
  }
  if (!data) return <p className="muted">Writing the briefing…</p>;
  const { briefing } = data;
  const cited = new Set(briefing.sections.flatMap((s) => s.claims.flatMap((c) => c.fact_ids)));

  return (
    <article className="briefing" aria-busy={loading}>
      <div className="briefing-actions noprint">
        <label className="check">
          <input type="checkbox" checked={useAi} onChange={(e) => setUseAi(e.target.checked)} />
          Rewrite with AI
        </label>
        <span className="spacer" />
        <button type="button" onClick={copy}>
          {copied ? "Copied" : "Copy as Markdown"}
        </button>
        <button type="button" onClick={() => window.print()}>
          Print
        </button>
      </div>

      {briefing.warnings.map((w) => (
        <p key={w} className="notice small" role="status">
          {w}
        </p>
      ))}

      <h2 className="briefing-headline">{briefing.headline}</h2>
      {briefing.sections
        .filter((s) => s.claims.length > 0)
        .map((section) => (
          <section key={section.title}>
            <h3>{section.title}</h3>
            <ul className="claims">
              {section.claims.map((claim, index) => (
                <li key={index}>
                  {claim.text}{" "}
                  {claim.fact_ids.map((id) => (
                    <button key={id} type="button" className="cite noprint" onClick={() => setActive(id)} aria-label={`Show the evidence for ${id}`}>
                      {id}
                    </button>
                  ))}
                </li>
              ))}
            </ul>
          </section>
        ))}

      <section>
        <h3>Evidence</h3>
        <p className="muted small">
          {briefing.source === "llm" ? "The wording was written by an AI, but every statement was checked against these computed facts." : "Every statement above comes straight from these computed facts."}
        </p>
        <ol className="evidence">
          {briefing.facts
            .filter((f) => cited.has(f.id))
            .map((fact) => (
              <li key={fact.id} id={`fact-${fact.id}`} className={fact.id === active ? "active" : ""}>
                <span className="fact-id">{fact.id}</span> {fact.text}
                {fact.evidence.length > 0 && <span className="muted small"> Issues: {fact.evidence.join(", ")}.</span>}
              </li>
            ))}
        </ol>
      </section>
    </article>
  );
}
