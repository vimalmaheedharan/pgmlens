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

const HOURGLASS = "M10 8.6H17M10 18.4H17M11 8.6C11 11.6 13.5 12 13.5 13.5S11 15.4 11 18.4M16 8.6C16 11.6 13.5 12 13.5 13.5S16 15.4 16 18.4";
const SAND = "M12 18.4C12.2 16.8 13.5 16.2 13.5 16.2S14.8 16.8 15 18.4Z";

function LensGlyph({ ink, glass, className }: { ink: string; glass: number; className: string }) {
  return (
    <g className={className}>
      <path d="M21.2 21.2L28 28" stroke="#f2b705" strokeWidth="4.2" strokeLinecap="round" />
      <circle cx="13.5" cy="13.5" r="10" fill="#fff" fillOpacity={glass} stroke={ink} strokeWidth="2.6" />
      <path d={HOURGLASS} fill="none" stroke={ink} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      <path d={SAND} fill={ink} />
    </g>
  );
}

export function LensMark() {
  return (
    <svg viewBox="0 0 32 32" width="30" height="30" aria-hidden="true" focusable="false" className="lens">
      <LensGlyph className="lens-light" ink="#1b7466" glass={0.9} />
      <LensGlyph className="lens-dark" ink="#55c7ad" glass={0.12} />
    </svg>
  );
}
