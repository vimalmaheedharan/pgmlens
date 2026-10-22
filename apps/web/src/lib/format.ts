import type { HealthStatus, IssueStatus, Severity } from "../types";

/** Parse "2026-11-08" as a local calendar date and full timestamps as instants. */
export function toDate(value: string): Date {
  const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (dateOnly) return new Date(Number(dateOnly[1]), Number(dateOnly[2]) - 1, Number(dateOnly[3]));
  return new Date(value);
}

const MONTH_DAY = new Intl.DateTimeFormat("en", { month: "short", day: "numeric" });
const FULL = new Intl.DateTimeFormat("en", { year: "numeric", month: "long", day: "numeric" });

export const shortDate = (value: string | null): string => (value ? MONTH_DAY.format(toDate(value)) : "no date");
export const fullDate = (value: string): string => FULL.format(toDate(value));

export const percent = (value: number | null): string => (value === null ? "n/a" : `${Math.round(value * 100)}%`);

export function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

export const severityLabel: Record<Severity, string> = {
  critical: "Critical",
  high: "High",
  medium: "Medium",
  low: "Low",
};

export const severityOrder: Severity[] = ["critical", "high", "medium", "low"];

export const statusLabel: Record<IssueStatus, string> = {
  todo: "To do",
  in_progress: "In progress",
  blocked: "Blocked",
  done: "Done",
};

export const healthTone: Record<HealthStatus, "calm" | "caution" | "alarm"> = {
  on_track: "calm",
  at_risk: "caution",
  off_track: "alarm",
};

/** "stale_days" -> "Stale days" */
export function humanizeKey(key: string): string {
  const spaced = key.replace(/_/g, " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

export function humanizeValue(value: unknown): string {
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : String(Math.round(value * 100) / 100);
  if (value === null || value === undefined) return "none";
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value)) return shortDate(value);
  return String(value);
}
