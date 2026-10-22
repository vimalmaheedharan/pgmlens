import type { Forecast } from "../types";
import { toDate } from "./format";

const DAY = 86_400_000;

export type Verdict = "calm" | "caution" | "alarm" | "unknown";

/** Is this forecast comfortably before its due date, borderline, or after it? */
export function verdict(f: Forecast): Verdict {
  if (f.status === "complete") return "calm";
  if (f.status === "not_converging") return "alarm";
  if (f.status !== "ok" || !f.p50_date || !f.p80_date) return "unknown";
  if (!f.due_date) return "unknown";
  const due = toDate(f.due_date).getTime();
  if (toDate(f.p80_date).getTime() <= due) return "calm";
  if (toDate(f.p50_date).getTime() <= due) return "caution";
  return "alarm";
}

export interface Domain {
  start: number;
  end: number;
}

/** Date range that fits every due date and forecast, with a little breathing room. */
export function timelineDomain(forecasts: Forecast[], today: Date): Domain {
  const stamps = [today.getTime()];
  for (const f of forecasts) {
    for (const d of [f.due_date, f.p50_date, f.p80_date, f.p95_date]) {
      if (d) stamps.push(toDate(d).getTime());
    }
  }
  const start = Math.min(...stamps) - 3 * DAY;
  const end = Math.max(...stamps) + 10 * DAY;
  return { start, end: Math.max(end, start + 30 * DAY) };
}

/** Position of a date along the axis as a percentage (clamped to 0..100). */
export function position(date: Date | string, domain: Domain): number {
  const t = typeof date === "string" ? toDate(date).getTime() : date.getTime();
  const pct = ((t - domain.start) / (domain.end - domain.start)) * 100;
  return Math.min(100, Math.max(0, pct));
}

/** First-of-month ticks that fall inside the domain. */
export function monthTicks(domain: Domain): { label: string; pct: number }[] {
  const ticks: { label: string; pct: number }[] = [];
  const cursor = new Date(domain.start);
  cursor.setDate(1);
  cursor.setHours(0, 0, 0, 0);
  cursor.setMonth(cursor.getMonth() + 1);
  while (cursor.getTime() < domain.end) {
    const label = cursor.toLocaleDateString("en", { month: "short", ...(cursor.getMonth() === 0 ? { year: "numeric" as const } : {}) });
    ticks.push({ label, pct: position(cursor, domain) });
    cursor.setMonth(cursor.getMonth() + 1);
  }
  return ticks;
}
