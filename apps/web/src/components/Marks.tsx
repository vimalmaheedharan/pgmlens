import type { HealthStatus, Severity } from "../types";
import { severityLabel } from "../lib/format";

type Tone = "calm" | "caution" | "alarm" | "quiet";
type Shape = "circle" | "ring" | "triangle" | "diamond" | "dot";

// Shape + word carry the meaning; color only reinforces it.
const SHAPES: Record<Shape, string> = {
  circle: "M8 2.5a5.5 5.5 0 1 0 0 11 5.5 5.5 0 0 0 0-11Z",
  ring: "M8 3.25a4.75 4.75 0 1 0 0 9.5 4.75 4.75 0 0 0 0-9.5Zm0 1.5a3.25 3.25 0 1 1 0 6.5 3.25 3.25 0 0 1 0-6.5Z",
  triangle: "M8 2.2 14.2 13H1.8L8 2.2Z",
  diamond: "M8 1.6 14.4 8 8 14.4 1.6 8 8 1.6Z",
  dot: "M8 6a2 2 0 1 0 0 4 2 2 0 0 0 0-4Z",
};

function Glyph({ shape, tone }: { shape: Shape; tone: Tone }) {
  return (
    <svg className={`glyph tone-${tone}`} viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false">
      <path d={SHAPES[shape]} fillRule="evenodd" />
    </svg>
  );
}

const SEVERITY_LOOK: Record<Severity, { shape: Shape; tone: Tone }> = {
  critical: { shape: "diamond", tone: "alarm" },
  high: { shape: "triangle", tone: "alarm" },
  medium: { shape: "ring", tone: "caution" },
  low: { shape: "dot", tone: "quiet" },
};

export function SeverityMark({ severity }: { severity: Severity }) {
  const look = SEVERITY_LOOK[severity];
  return (
    <span className="mark">
      <Glyph {...look} />
      <span className={`mark-word tone-${look.tone}`}>{severityLabel[severity]}</span>
    </span>
  );
}

const HEALTH_LOOK: Record<HealthStatus, { shape: Shape; tone: Tone }> = {
  on_track: { shape: "circle", tone: "calm" },
  at_risk: { shape: "triangle", tone: "caution" },
  off_track: { shape: "diamond", tone: "alarm" },
};

export function HealthMark({ status, label }: { status: HealthStatus; label: string }) {
  const look = HEALTH_LOOK[status];
  return (
    <span className="mark">
      <Glyph {...look} />
      <span className={`mark-word tone-${look.tone}`}>{label}</span>
    </span>
  );
}

export function LensMark() {
  return (
    <svg viewBox="0 0 32 32" width="26" height="26" aria-hidden="true" focusable="false" className="lens">
      <circle cx="16" cy="16" r="11" fill="none" stroke="currentColor" strokeWidth="3" />
      <circle cx="16" cy="16" r="4" fill="currentColor" />
    </svg>
  );
}
