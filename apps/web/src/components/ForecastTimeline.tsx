import { useId, useMemo } from "react";
import { percent, plural, shortDate, toDate } from "../lib/format";
import { monthTicks, position, timelineDomain, verdict } from "../lib/timeline";
import type { Forecast } from "../types";

interface Props {
  forecasts: Forecast[];
  asOf: string;
  showNumbers: boolean;
}

function rowLabel(f: Forecast): string {
  const due = f.due_date ? `, due ${shortDate(f.due_date)}` : "";
  const chance = f.on_time_probability !== null && f.status !== "complete" ? `, ${percent(f.on_time_probability)} chance of finishing on time` : "";
  return `${f.scope_name}${due}: ${f.summary}${chance}`;
}

export function ForecastTimeline({ forecasts, asOf, showNumbers }: Props) {
  const today = useMemo(() => toDate(asOf), [asOf]);
  const rows = useMemo(
    () =>
      [...forecasts]
        .filter((f) => f.status !== "complete")
        // The whole-program row adds nothing when it just repeats a milestone's dates.
        .filter(
          (f, _i, all) =>
            f.scope_id !== null ||
            !all.some((o) => o.scope_id !== null && o.due_date === f.due_date && o.p50_date === f.p50_date && o.p80_date === f.p80_date),
        )
        .sort((a, b) => Number(a.scope_id === null) - Number(b.scope_id === null) || (a.due_date ?? "9999").localeCompare(b.due_date ?? "9999")),
    [forecasts],
  );
  const domain = useMemo(() => timelineDomain(rows, today), [rows, today]);
  const ticks = useMemo(() => monthTicks(domain), [domain]);
  const todayPct = position(today, domain);
  const captionId = useId();

  if (rows.length === 0) return <p className="muted">Nothing left to forecast. All milestones are complete.</p>;

  return (
    <figure className="timeline" aria-labelledby={captionId}>
      <div className="trow taxis" aria-hidden="true">
        <span />
        <div className="track">
          {ticks.map((t) => (
            <span key={t.label + t.pct} className="tick-label" style={{ left: `${t.pct}%` }}>
              {t.label}
            </span>
          ))}
          <span className="today-label" style={{ left: `${todayPct}%` }}>
            Today
          </span>
        </div>
        <span />
      </div>

      {rows.map((f) => {
        const tone = verdict(f);
        const hasBand = f.status === "ok" && f.p50_date && f.p80_date;
        const p50 = hasBand ? position(f.p50_date!, domain) : 0;
        const p80 = hasBand ? position(f.p80_date!, domain) : 0;
        const p95 = f.p95_date ? position(f.p95_date, domain) : p80;
        return (
          <div key={f.scope_id ?? "program"} className={`trow ${f.scope_id === null ? "whole" : ""}`} role="group" aria-label={rowLabel(f)}>
            <div className="tname">
              <strong>{f.scope_name}</strong>
              <span className="muted small">{f.due_date ? `due ${shortDate(f.due_date)}` : "no due date"}</span>
            </div>
            <div className="track" aria-hidden="true">
              {ticks.map((t) => (
                <span key={t.label + t.pct} className="gridline" style={{ left: `${t.pct}%` }} />
              ))}
              <span className="todayline" style={{ left: `${todayPct}%` }} />
              {hasBand && (
                <>
                  <span className={`whisker tone-bg-${tone}`} style={{ left: `${p50}%`, width: `${Math.max(p95 - p50, 0)}%` }} />
                  <span className={`band tone-bg-${tone}`} style={{ left: `${p50}%`, width: `max(${Math.max(p80 - p50, 0)}%, 8px)` }} />
                  <span className={`likely tone-bg-${tone}`} style={{ left: `${p50}%` }} />
                </>
              )}
              {f.due_date && (
                <span className="dueline" style={{ left: `${position(f.due_date, domain)}%` }}>
                  <span className="dueflag" />
                </span>
              )}
            </div>
            <div className="tverdict">
              <span className={`tone-${tone === "unknown" ? "quiet" : tone}`}>{f.summary}</span>
              {f.status === "ok" && f.on_time_probability !== null && (
                <span className="muted small">{percent(f.on_time_probability)} chance of finishing on time</span>
              )}
            </div>
            {showNumbers && (
              <p className="tnumbers small">
                {f.status === "ok" && f.p50_date && f.p80_date && f.p95_date ? (
                  <>
                    Most likely {shortDate(f.p50_date)}. 80% sure by {shortDate(f.p80_date)}. 95% sure by {shortDate(f.p95_date)}.{" "}
                  </>
                ) : (
                  f.note && <>{f.note} </>
                )}
                {plural(f.remaining, "issue")} in scope; the team finishes about {f.mean_weekly_throughput} a week
                {f.mean_weekly_scope_growth > 0 ? ` while about ${f.mean_weekly_scope_growth} a week are added` : ""}.
              </p>
            )}
          </div>
        );
      })}

      <figcaption id={captionId} className="muted small">
        The bar runs from the most likely finish to the date we are 80% sure of, with a thin line out to 95%. The vertical
        line is the due date.
      </figcaption>
    </figure>
  );
}
