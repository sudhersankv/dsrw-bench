import { score as formatScore } from "./data/format";
import type { SubScoreId } from "./data/types";
import { escapeHtml } from "./theme";

export type Scores = Partial<Record<SubScoreId, number | null>>;

export interface Bearing {
  id: SubScoreId;
  dx: number;
  dy: number;
  short: string;
}

/** Bearing of each sub-score on the surveyed parcel: north, east, south, west. */
export const BEARINGS: Bearing[] = [
  { id: "history", dx: 0, dy: -1, short: "Uses history" },
  { id: "adapt", dx: 1, dy: 0, short: "Adapts" },
  { id: "use", dx: 0, dy: 1, short: "Acts" },
  { id: "recall", dx: -1, dy: 0, short: "Recalls" },
];

/** A vertex of the measured polygon, or null: a missing score is never drawn as a zero. */
export function parcelVertex(bearing: Bearing, value: number | null | undefined, cx: number, cy: number, radius: number): { x: number; y: number } | null {
  if (value === null || value === undefined) return null;
  return { x: cx + (bearing.dx * radius * value) / 100, y: cy + (bearing.dy * radius * value) / 100 };
}

/** The model's score plot as a surveyed parcel: four boundary stones, one per sub-score. */
export function parcelSvg(scores: Scores, size: number, labelled: string): string {
  const center = size / 2;
  const radius = size / 2 - 7;
  const tip = (b: Bearing, reach = radius): { x: number; y: number } => ({ x: center + b.dx * reach, y: center + b.dy * reach });
  const ghost = BEARINGS.map((b) => `${tip(b).x},${tip(b).y}`).join(" ");
  const missing = BEARINGS.filter((b) => (scores[b.id] ?? null) === null);
  const axes = BEARINGS.map((b) => {
    const dashed = missing.includes(b) ? ' stroke-dasharray="3 3"' : "";
    return `<line x1="${center}" y1="${center}" x2="${tip(b).x}" y2="${tip(b).y}" class="parcel-axis"${dashed}/>`;
  }).join("");
  const stones = BEARINGS.flatMap((b) => {
    const point = parcelVertex(b, scores[b.id], center, center, radius);
    return point ? [point] : [];
  });
  const fill = stones.length >= 2 ? `<polygon points="${stones.map((p) => `${p.x},${p.y}`).join(" ")}" class="parcel-fill"/>` : "";
  const stoneDots = stones.map((p) => `<circle cx="${p.x}" cy="${p.y}" r="2.6" class="parcel-stone"/>`).join("");
  const rings = missing.map((b) => `<circle cx="${tip(b).x}" cy="${tip(b).y}" r="3.4" class="parcel-missing"/>`).join("");
  return `<svg viewBox="0 0 ${size} ${size}" width="${size}" height="${size}" role="img" aria-label="${escapeHtml(labelled)}" class="parcel">
    <polygon points="${ghost}" class="parcel-ghost"/>${axes}${fill}${stoneDots}${rings}
  </svg>`;
}

/** A mown strip: stripes up to the score, unmown ground beyond it. "Not testable" gets its own hatch. */
export function stripMeter(value: number | null, width = 96): string {
  const height = 14;
  if (value === null) {
    return `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" width="${width}" height="${height}" aria-hidden="true" class="strip"><rect width="${width}" height="${height}" class="strip-untestable"/></svg>`;
  }
  const stripes = 16;
  const stripeWidth = width / stripes;
  const lit = (value / 100) * stripes;
  const bars = Array.from({ length: stripes }, (_, index) => {
    const remaining = Math.max(0, Math.min(1, lit - index));
    if (remaining === 0) return "";
    const tone = index % 2 === 0 ? "strip-a" : "strip-b";
    return `<rect x="${index * stripeWidth}" width="${stripeWidth * remaining}" height="${height}" class="${tone}"/>`;
  }).join("");
  return `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" width="${width}" height="${height}" aria-hidden="true" class="strip"><rect width="${width}" height="${height}" class="strip-ground"/>${bars}<rect width="${width}" height="${height}" class="strip-edge"/></svg>`;
}

export function subscoreCell(value: number | null): string {
  const untestable = value === null ? " is-untestable" : "";
  return `<span class="meter">${stripMeter(value)}<span class="meter-value${untestable}">${formatScore(value)}</span></span>`;
}

export const DEMO_STAMP_TEXT = "DEMO DATA, NOT A MODEL RESULT";

export function demoStamp(): string {
  return `<p class="demo-stamp" role="status"><strong>${DEMO_STAMP_TEXT}</strong></p>`;
}
