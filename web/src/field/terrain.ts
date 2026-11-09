import type { Rng } from "./rng";

type Segment = [number, number, number, number];

interface Wave {
  fx: number;
  fy: number;
  phase: number;
  amp: number;
}

function makeWaves(rng: Rng): Wave[] {
  return Array.from({ length: 5 }, (): Wave => ({
    fx: 0.002 + rng() * 0.008,
    fy: 0.002 + rng() * 0.008,
    phase: rng() * Math.PI * 2,
    amp: 0.5 + rng(),
  }));
}

function height(waves: Wave[], x: number, y: number): number {
  return waves.reduce((sum, w) => sum + Math.sin(x * w.fx + y * w.fy + w.phase) * w.amp, 0);
}

/** Marching squares over the seeded height field, returning all contour line segments. */
export function contourSegments(rng: Rng, width: number, height_: number, spacing: number, step: number): Segment[] {
  const waves = makeWaves(rng);
  const segments: Segment[] = [];
  const rows = Math.ceil(height_ / step);
  const cols = Math.ceil(width / step);
  const value = (cx: number, cy: number): number => height(waves, cx * step, cy * step);
  for (let cy = 0; cy < rows; cy++) {
    for (let cx = 0; cx < cols; cx++) {
      addCellSegments(segments, value, cx, cy, step, spacing);
    }
  }
  return segments;
}

function addCellSegments(
  segments: Segment[],
  value: (cx: number, cy: number) => number,
  cx: number,
  cy: number,
  step: number,
  spacing: number,
): void {
  const a = value(cx, cy);
  const b = value(cx + 1, cy);
  const c = value(cx + 1, cy + 1);
  const d = value(cx, cy + 1);
  const min = Math.min(a, b, c, d);
  const max = Math.max(a, b, c, d);
  for (let level = Math.ceil(min / spacing) * spacing; level < max; level += spacing) {
    const edges = crossings(a, b, c, d, level);
    if (edges.length >= 2) {
      const [p, q] = edges;
      segments.push([(cx + p[0]) * step, (cy + p[1]) * step, (cx + q[0]) * step, (cy + q[1]) * step]);
    }
    if (edges.length === 4) {
      const [, , p, q] = edges;
      segments.push([(cx + p[0]) * step, (cy + p[1]) * step, (cx + q[0]) * step, (cy + q[1]) * step]);
    }
  }
}

function crossings(a: number, b: number, c: number, d: number, level: number): [number, number][] {
  const points: [number, number][] = [];
  const add = (v1: number, v2: number, p1: [number, number], p2: [number, number]): void => {
    if (v1 >= level !== v2 >= level) {
      const t = (level - v1) / (v2 - v1);
      points.push([p1[0] + (p2[0] - p1[0]) * t, p1[1] + (p2[1] - p1[1]) * t]);
    }
  };
  add(a, b, [0, 0], [1, 0]);
  add(b, c, [1, 0], [1, 1]);
  add(d, c, [0, 1], [1, 1]);
  add(a, d, [0, 0], [0, 1]);
  return points;
}
