import { describe, expect, it } from "vitest";
import type { Forecast } from "../types";
import { humanizeKey, humanizeValue, shortDate, toDate } from "./format";
import { layerLayout } from "./layout";
import { buildHash, parseRoute } from "./route";
import { monthTicks, position, timelineDomain, verdict } from "./timeline";

const forecast = (over: Partial<Forecast>): Forecast => ({
  scope_id: "m1",
  scope_name: "Beta",
  status: "ok",
  remaining: 5,
  weeks_of_history: 8,
  mean_weekly_throughput: 3,
  mean_weekly_scope_growth: 0,
  p50_date: "2026-11-10",
  p80_date: "2026-11-20",
  p95_date: "2026-12-01",
  due_date: "2026-11-15",
  on_time_probability: 0.6,
  note: "",
  summary: "",
  ...over,
});

describe("route", () => {
  it("round-trips program, tab and risk", () => {
    const hash = buildHash({ programId: "atlas", tab: "risks", riskId: "stale-blocker:bck-1" });
    expect(parseRoute(hash)).toEqual({ programId: "atlas", tab: "risks", riskId: "stale-blocker:bck-1" });
  });
  it("defaults to the portfolio and the overview tab", () => {
    expect(parseRoute("")).toEqual({ programId: null, tab: "overview", riskId: null });
    expect(parseRoute("#/p/atlas")).toEqual({ programId: "atlas", tab: "overview", riskId: null });
    expect(parseRoute("#/p/atlas/nonsense").tab).toBe("overview");
    expect(buildHash({})).toBe("#/");
  });
});

describe("format", () => {
  it("treats date-only strings as local calendar dates", () => {
    const d = toDate("2026-11-08");
    expect([d.getFullYear(), d.getMonth(), d.getDate()]).toEqual([2026, 10, 8]);
    expect(shortDate("2026-11-08")).toBe("Nov 8");
    expect(shortDate(null)).toBe("no date");
  });
  it("humanizes metric keys and values", () => {
    expect(humanizeKey("days_stale")).toBe("Days stale");
    expect(humanizeValue(0.5)).toBe("0.5");
    expect(humanizeValue("2026-11-08")).toBe("Nov 8");
    expect(humanizeValue(null)).toBe("none");
  });
});

describe("timeline", () => {
  it("classifies forecasts against their due date", () => {
    expect(verdict(forecast({ p80_date: "2026-11-14" }))).toBe("calm");
    expect(verdict(forecast({}))).toBe("caution");
    expect(verdict(forecast({ p50_date: "2026-11-30", p80_date: "2026-12-10" }))).toBe("alarm");
    expect(verdict(forecast({ status: "not_converging", p50_date: null }))).toBe("alarm");
    expect(verdict(forecast({ status: "insufficient_data", p50_date: null }))).toBe("unknown");
    expect(verdict(forecast({ status: "complete" }))).toBe("calm");
  });
  it("positions dates along a domain that contains them all", () => {
    const today = new Date(2026, 9, 21);
    const domain = timelineDomain([forecast({})], today);
    const pts = [position(today, domain), position("2026-11-15", domain), position("2026-12-01", domain)];
    expect(pts[0]).toBeGreaterThan(0);
    expect(pts[0]).toBeLessThan(pts[1]);
    expect(pts[1]).toBeLessThan(pts[2]);
    expect(pts[2]).toBeLessThan(100);
  });
  it("produces month ticks inside the domain", () => {
    const domain = timelineDomain([forecast({})], new Date(2026, 9, 21));
    const labels = monthTicks(domain).map((t) => t.label);
    expect(labels).toEqual(["Nov", "Dec"]);
  });
});

describe("layout", () => {
  it("places blockers to the left of what they block", () => {
    const placed = layerLayout(["a", "b", "c", "d"], [
      { source: "a", target: "b" },
      { source: "b", target: "c" },
      { source: "a", target: "d" },
    ]);
    expect(placed.get("a")!.layer).toBe(0);
    expect(placed.get("b")!.layer).toBe(1);
    expect(placed.get("c")!.layer).toBe(2);
    expect(placed.get("d")!.layer).toBe(1);
    expect(placed.get("c")!.x).toBeGreaterThan(placed.get("b")!.x);
  });
  it("does not hang or crash on cycles and ignores unknown nodes", () => {
    const placed = layerLayout(["a", "b"], [
      { source: "a", target: "b" },
      { source: "b", target: "a" },
      { source: "a", target: "ghost" },
    ]);
    expect(placed.size).toBe(2);
  });
  it("never overlaps two nodes in the same column", () => {
    const placed = layerLayout(["a", "b", "c"], [
      { source: "a", target: "b" },
      { source: "a", target: "c" },
    ]);
    expect(placed.get("b")!.y).not.toBe(placed.get("c")!.y);
  });
});
