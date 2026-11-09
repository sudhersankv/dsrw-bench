import { createRng, type Rng } from "./rng";

export interface Point {
  x: number;
  y: number;
}

export interface Farm {
  width: number;
  height: number;
  pastures: Point[][];
  centroids: Point[];
}

export const MAP_WIDTH = 1000;
export const MAP_HEIGHT = 620;

function bisectorClip(polygon: Point[], site: Point, other: Point): Point[] {
  const mid = { x: (site.x + other.x) / 2, y: (site.y + other.y) / 2 };
  const nx = other.x - site.x;
  const ny = other.y - site.y;
  const side = (p: Point): number => (p.x - mid.x) * nx + (p.y - mid.y) * ny;
  const result: Point[] = [];
  polygon.forEach((current, i) => {
    const next = polygon[(i + 1) % polygon.length];
    const sc = side(current);
    const sn = side(next);
    if (sc <= 0) result.push(current);
    if (sc * sn < 0) {
      const t = sc / (sc - sn);
      result.push({ x: current.x + (next.x - current.x) * t, y: current.y + (next.y - current.y) * t });
    }
  });
  return result;
}

function voronoiCell(site: Point, sites: Point[], width: number, height: number): Point[] {
  const rect: Point[] = [
    { x: 0, y: 0 },
    { x: width, y: 0 },
    { x: width, y: height },
    { x: 0, y: height },
  ];
  return sites.filter((other) => other !== site).reduce((poly, other) => bisectorClip(poly, site, other), rect);
}

export function polygonArea(polygon: Point[]): number {
  let total = 0;
  polygon.forEach((p, i) => {
    const q = polygon[(i + 1) % polygon.length];
    total += p.x * q.y - q.x * p.y;
  });
  return Math.abs(total) / 2;
}

export function centroid(polygon: Point[]): Point {
  let doubledArea = 0;
  let cx = 0;
  let cy = 0;
  polygon.forEach((p, i) => {
    const q = polygon[(i + 1) % polygon.length];
    const cross = p.x * q.y - q.x * p.y;
    doubledArea += cross;
    cx += (p.x + q.x) * cross;
    cy += (p.y + q.y) * cross;
  });
  return { x: cx / (3 * doubledArea), y: cy / (3 * doubledArea) };
}

export function contains(polygon: Point[], point: Point): boolean {
  let inside = false;
  polygon.forEach((a, i) => {
    const b = polygon[(i + 1) % polygon.length];
    if (a.y > point.y !== b.y > point.y && point.x < ((b.x - a.x) * (point.y - a.y)) / (b.y - a.y) + a.x) {
      inside = !inside;
    }
  });
  return inside;
}

/** Sites in four loose quadrants, jittered, so every field is large enough to read. */
function jitteredSites(rng: Rng, width: number, height: number): Point[] {
  const cells: [number, number][] = [
    [0.27, 0.3],
    [0.72, 0.26],
    [0.3, 0.75],
    [0.74, 0.72],
  ];
  return cells.map(([u, v]) => ({
    x: width * (u + (rng() - 0.5) * 0.2),
    y: height * (v + (rng() - 0.5) * 0.22),
  }));
}

export function buildFarm(seed: number, width: number = MAP_WIDTH, height: number = MAP_HEIGHT): Farm {
  const rng = createRng(seed * 1009 + 17);
  const sites = jitteredSites(rng, width, height);
  const pastures = sites.map((site) => voronoiCell(site, sites, width, height));
  return { width, height, pastures, centroids: pastures.map(centroid) };
}

export function randomPointIn(polygon: Point[], rng: Rng, inset = 0.82): Point {
  const center = centroid(polygon);
  const xs = polygon.map((p) => p.x);
  const ys = polygon.map((p) => p.y);
  const [minX, maxX, minY, maxY] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  for (let attempt = 0; attempt < 80; attempt++) {
    const raw = { x: minX + rng() * (maxX - minX), y: minY + rng() * (maxY - minY) };
    const scaled = { x: center.x + (raw.x - center.x) * inset, y: center.y + (raw.y - center.y) * inset };
    if (contains(polygon, raw)) return scaled;
  }
  return center;
}

export function fieldAt(farm: Farm, point: Point): number | null {
  const index = farm.pastures.findIndex((polygon) => contains(polygon, point));
  return index === -1 ? null : index;
}
