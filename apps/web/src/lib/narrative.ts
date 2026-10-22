import type { Forecast } from "../types";
import { plural, toDate } from "./format";

const lowerFirst = (text: string) => text.charAt(0).toLowerCase() + text.slice(1);

/**
 * The one sentence a leader should read first: which milestone will hurt soonest.
 * `fallback` is used when nothing is slipping and there is nothing more specific to say.
 */
export function leadSentence(forecasts: Forecast[], fallback: string): string {
  const milestones = forecasts.filter((f) => f.scope_id !== null && f.remaining > 0);
  const slipping = milestones
    .filter(
      (f) =>
        f.status === "not_converging" ||
        (f.status === "ok" && f.due_date && f.p80_date && toDate(f.p80_date) > toDate(f.due_date)),
    )
    .sort((a, b) => (a.due_date ?? "9999").localeCompare(b.due_date ?? "9999"));
  if (slipping.length > 0) {
    const [first, ...rest] = slipping;
    const head = `${first.scope_name} is ${lowerFirst(first.summary)}.`;
    return rest.length ? `${head} ${plural(rest.length, "other milestone")} also at risk.` : head;
  }
  if (milestones.length > 0 && milestones.every((f) => f.status === "ok")) {
    return "Every milestone is forecast to land on time.";
  }
  return fallback;
}
