import { FONT_BODY, FONT_NAMES, token } from "../theme";
import { drawSheepGlyph, drawWolfGlyph } from "./animals";
import { MAP_HEIGHT, MAP_WIDTH, randomPointIn, type Farm, type Point } from "./geometry";
import { tally, type MemoryView } from "./readers";
import { createRng } from "./rng";
import { contourSegments } from "./terrain";
import { WINDOW_DAYS, type World } from "./world";

const TAU = Math.PI * 2;
const FENCE_POST_GAP = 26;

export interface Reveal {
  chosen: number;
  danger: number;
  safe: number | null;
}

export interface FrameState {
  day: number;
  view: MemoryView;
  reveal: Reveal | null;
  /** Enlarges field names on narrow screens, where the map is drawn small. */
  labelScale: number;
  /** False under reduced motion: the wolf still appears but no ring expands from it. */
  animate: boolean;
}

/** Everything fixed for one farm and one world: base map, per-day positions, wolf days. */
export class FieldRenderer {
  private base: HTMLCanvasElement = document.createElement("canvas");
  private points: Point[] = [];
  private wolfDays: number[] = [];

  constructor(
    private readonly canvas: HTMLCanvasElement,
    private world: World,
    private farm: Farm,
  ) {
    this.placeDays();
  }

  setWorld(world: World, farm: Farm): void {
    this.world = world;
    this.farm = farm;
    this.placeDays();
    this.resize(this.canvas.clientWidth);
  }

  private placeDays(): void {
    const rng = createRng(this.world.seed * 5003 + 41);
    this.points = this.world.days.map((day) => randomPointIn(this.farm.pastures[day.grazed], rng));
    this.wolfDays = this.world.days.flatMap((day, index) => (day.kind === "wolf" ? [index] : []));
  }

  resize(cssWidth: number): void {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const pixelWidth = Math.max(1, Math.round(cssWidth * dpr));
    const pixelHeight = Math.round((pixelWidth * MAP_HEIGHT) / MAP_WIDTH);
    this.canvas.width = pixelWidth;
    this.canvas.height = pixelHeight;
    this.base.width = pixelWidth;
    this.base.height = pixelHeight;
    const ctx = this.base.getContext("2d")!;
    ctx.setTransform(pixelWidth / MAP_WIDTH, 0, 0, pixelWidth / MAP_WIDTH, 0, 0);
    drawBase(ctx, this.world, this.farm);
  }

  pointToMap(cssX: number, cssY: number): Point {
    const scale = MAP_WIDTH / this.canvas.clientWidth;
    return { x: cssX * scale, y: cssY * scale };
  }

  draw(state: FrameState): void {
    const ctx = this.canvas.getContext("2d")!;
    const scale = this.canvas.width / MAP_WIDTH;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.drawImage(this.base, 0, 0);
    ctx.setTransform(scale, 0, 0, scale, 0, 0);
    drawFog(ctx, this.world, state.day);
    drawMarks(ctx, this.world, this.points, this.wolfDays, state);
    drawLabels(ctx, this.world, this.farm, state);
    drawPing(ctx, this.points, this.wolfDays, state);
    drawSheep(ctx, this.points, state.day);
    if (state.reveal) drawReveal(ctx, this.farm, this.world, state.reveal);
    drawSwapNotice(ctx, this.world, state.day);
  }
}

function strokePolygon(ctx: CanvasRenderingContext2D, polygon: Point[]): void {
  ctx.beginPath();
  polygon.forEach((p, i) => (i === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y)));
  ctx.closePath();
}

function drawBase(ctx: CanvasRenderingContext2D, world: World, farm: Farm): void {
  ctx.fillStyle = token("paper");
  ctx.fillRect(0, 0, MAP_WIDTH, MAP_HEIGHT);
  const rng = createRng(world.seed * 211 + 5);
  const tints = ["field-a", "field-b", "field-c", "field-d"].map(token);
  farm.pastures.forEach((polygon, index) => {
    ctx.save();
    strokePolygon(ctx, polygon);
    ctx.fillStyle = tints[index];
    ctx.fill();
    ctx.clip();
    drawMownStripes(ctx, polygon, rng());
    ctx.restore();
  });
  drawContours(ctx, world.seed);
  farm.pastures.forEach((polygon) => drawFence(ctx, polygon));
  drawNeatLine(ctx);
  drawNorthArrow(ctx);
}

function drawMownStripes(ctx: CanvasRenderingContext2D, polygon: Point[], angleSeed: number): void {
  const angle = angleSeed * Math.PI;
  const dx = Math.cos(angle);
  const dy = Math.sin(angle);
  const xs = polygon.map((p) => p.x);
  const ys = polygon.map((p) => p.y);
  const reach = Math.hypot(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys));
  const cx = xs.reduce((a, b) => a + b, 0) / xs.length;
  const cy = ys.reduce((a, b) => a + b, 0) / ys.length;
  ctx.lineWidth = 9;
  ctx.strokeStyle = token("mown");
  for (let offset = -reach; offset < reach; offset += 26) {
    const px = cx - dy * offset;
    const py = cy + dx * offset;
    ctx.beginPath();
    ctx.moveTo(px - dx * reach, py - dy * reach);
    ctx.lineTo(px + dx * reach, py + dy * reach);
    ctx.stroke();
  }
}

function drawContours(ctx: CanvasRenderingContext2D, seed: number): void {
  const segments = contourSegments(createRng(seed * 37 + 3), MAP_WIDTH, MAP_HEIGHT, 0.55, 12);
  ctx.strokeStyle = token("contour");
  ctx.lineWidth = 0.9;
  ctx.beginPath();
  for (const [x1, y1, x2, y2] of segments) {
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
  }
  ctx.stroke();
}

function drawFence(ctx: CanvasRenderingContext2D, polygon: Point[]): void {
  ctx.strokeStyle = token("ink");
  ctx.lineWidth = 2;
  strokePolygon(ctx, polygon);
  ctx.stroke();
  ctx.fillStyle = token("ink");
  polygon.forEach((p, i) => {
    const q = polygon[(i + 1) % polygon.length];
    const steps = Math.floor(Math.hypot(q.x - p.x, q.y - p.y) / FENCE_POST_GAP);
    for (let s = 0; s <= steps; s++) {
      const t = steps === 0 ? 0 : s / steps;
      ctx.fillRect(p.x + (q.x - p.x) * t - 1.5, p.y + (q.y - p.y) * t - 1.5, 3, 3);
    }
  });
}

function drawNeatLine(ctx: CanvasRenderingContext2D): void {
  ctx.strokeStyle = token("ink");
  ctx.lineWidth = 3;
  ctx.strokeRect(1.5, 1.5, MAP_WIDTH - 3, MAP_HEIGHT - 3);
  ctx.lineWidth = 1;
  for (let x = 100; x < MAP_WIDTH; x += 100) tick(ctx, x, 0, 0, 12);
  for (let y = 100; y < MAP_HEIGHT; y += 100) tick(ctx, 0, y, 12, 0);
}

function tick(ctx: CanvasRenderingContext2D, x: number, y: number, dx: number, dy: number): void {
  ctx.beginPath();
  ctx.moveTo(x, y);
  ctx.lineTo(x + dx, y + dy);
  ctx.stroke();
}

function drawNorthArrow(ctx: CanvasRenderingContext2D): void {
  const x = MAP_WIDTH - 34;
  const y = 38;
  ctx.fillStyle = token("ink");
  ctx.strokeStyle = token("ink");
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(x, y - 18);
  ctx.lineTo(x + 7, y + 8);
  ctx.lineTo(x, y + 3);
  ctx.closePath();
  ctx.fill();
  ctx.beginPath();
  ctx.moveTo(x, y - 18);
  ctx.lineTo(x - 7, y + 8);
  ctx.lineTo(x, y + 3);
  ctx.closePath();
  ctx.stroke();
  ctx.font = `600 13px ${FONT_BODY}`;
  ctx.textAlign = "center";
  ctx.fillText("N", x, y + 22);
}

function drawFog(ctx: CanvasRenderingContext2D, world: World, day: number): void {
  if (world.test !== "fog") return;
  const inBlock = day >= world.blockStart! && day <= world.blockEnd!;
  ctx.fillStyle = token("fog");
  ctx.globalAlpha = inBlock ? 0.05 : 0.86;
  ctx.fillRect(0, 0, MAP_WIDTH, MAP_HEIGHT);
  ctx.globalAlpha = inBlock ? 0 : 0.5;
  ctx.strokeStyle = token("fog-hatch");
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let x = -MAP_HEIGHT; x < MAP_WIDTH; x += 16) {
    ctx.moveTo(x, 0);
    ctx.lineTo(x + MAP_HEIGHT, MAP_HEIGHT);
  }
  ctx.stroke();
  ctx.globalAlpha = 1;
}

function drawMarks(ctx: CanvasRenderingContext2D, world: World, points: Point[], wolfDays: number[], state: FrameState): void {
  if (state.view === "tally") return;
  const latest = Math.floor(state.day);
  const fresh = new Path2D();
  const stale = new Path2D();
  const ghosted = new Path2D();
  for (const day of wolfDays) {
    if (day > latest) break;
    const p = points[day];
    if (state.view === "window" && day <= latest - WINDOW_DAYS) {
      ghosted.moveTo(p.x + 2, p.y);
      ghosted.arc(p.x, p.y, 2, 0, TAU);
    } else if (world.swapDay !== null && day < world.swapDay && latest >= world.swapDay) {
      stale.moveTo(p.x + 3.4, p.y);
      stale.arc(p.x, p.y, 3.4, 0, TAU);
    } else {
      fresh.moveTo(p.x - 3.6, p.y - 3.6);
      fresh.lineTo(p.x + 3.6, p.y + 3.6);
      fresh.moveTo(p.x + 3.6, p.y - 3.6);
      fresh.lineTo(p.x - 3.6, p.y + 3.6);
    }
  }
  ctx.globalAlpha = 0.28;
  ctx.fillStyle = token("muted");
  ctx.fill(ghosted);
  ctx.globalAlpha = 1;
  ctx.strokeStyle = token("wolf-stale");
  ctx.lineWidth = 1.2;
  ctx.stroke(stale);
  ctx.strokeStyle = token("wolf");
  ctx.lineWidth = 1.8;
  ctx.stroke(fresh);
}

function plaque(ctx: CanvasRenderingContext2D, text: string, x: number, y: number, font: string, color: string, height = 24): void {
  ctx.font = font;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  const width = ctx.measureText(text).width + 14;
  ctx.fillStyle = token("label-bg");
  ctx.fillRect(x - width / 2, y - height / 2, width, height);
  ctx.fillStyle = color;
  ctx.fillText(text, x, y + 1);
  ctx.textBaseline = "alphabetic";
}

function drawLabels(ctx: CanvasRenderingContext2D, world: World, farm: Farm, state: FrameState): void {
  const counts = state.view === "tally" ? tally(world, "tally", Math.floor(state.day)) : null;
  const k = state.labelScale;
  farm.centroids.forEach((point, index) => {
    plaque(ctx, world.names[index], point.x, point.y - (counts ? 26 * k : 0), `italic 400 ${25 * k}px ${FONT_NAMES}`, token("ink"), 24 * k);
    if (!counts) return;
    const count = counts[index];
    plaque(ctx, `${Math.round(count.wolves)} ${Math.round(count.wolves) === 1 ? "wolf" : "wolves"}, ${Math.round(count.visits)} days`, point.x, point.y + 2, `600 ${15 * k}px ${FONT_BODY}`, token("ink"), 22 * k);
  });
}

function drawReveal(ctx: CanvasRenderingContext2D, farm: Farm, world: World, reveal: Reveal): void {
  ctx.lineWidth = 5;
  ctx.strokeStyle = token("wolf");
  strokePolygon(ctx, farm.pastures[reveal.danger]);
  ctx.stroke();
  const danger = farm.centroids[reveal.danger];
  plaque(ctx, world.test === "fog" ? "The old clue pointed here" : "The wolf is here now", danger.x, danger.y + 34, `700 17px ${FONT_BODY}`, token("wolf"));
  if (reveal.safe !== null) {
    ctx.strokeStyle = token("safe");
    strokePolygon(ctx, farm.pastures[reveal.safe]);
    ctx.stroke();
    const safe = farm.centroids[reveal.safe];
    plaque(ctx, "Safest field", safe.x, safe.y + 34, `700 17px ${FONT_BODY}`, token("safe"));
  }
  const chosen = farm.centroids[reveal.chosen];
  ctx.strokeStyle = token("ink");
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.arc(chosen.x, chosen.y - 8, 62, 0, TAU);
  ctx.stroke();
  plaque(ctx, "Your call", chosen.x, chosen.y - 78, `700 17px ${FONT_BODY}`, token("ink"));
}

function drawPing(ctx: CanvasRenderingContext2D, points: Point[], wolfDays: number[], state: FrameState): void {
  const latest = Math.floor(state.day);
  const lastWolf = [...wolfDays].reverse().find((day) => day <= latest);
  if (lastWolf === undefined) return;
  const age = state.day - lastWolf;
  if (age > 40) return;
  const p = points[lastWolf];
  drawWolfGlyph(ctx, p.x, p.y, 8, -Math.PI / 2, { body: token("wolf"), ink: token("ink") });
  if (state.animate) {
    ctx.strokeStyle = token("wolf");
    ctx.globalAlpha = Math.max(0, 1 - age / 40);
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(p.x, p.y, 16 + age * 1.6, 0, TAU);
    ctx.stroke();
    ctx.globalAlpha = 1;
  }
}

function drawSheep(ctx: CanvasRenderingContext2D, points: Point[], day: number): void {
  const current = Math.floor(day);
  const point = points[current];
  const previous = points[Math.max(0, current - 1)];
  const frac = day - current;
  const x = previous.x + (point.x - previous.x) * frac;
  const y = previous.y + (point.y - previous.y) * frac;
  const angle = Math.atan2(point.y - previous.y, point.x - previous.x);
  drawSheepGlyph(ctx, x, y, 8.5, angle, { body: token("sheep"), ink: token("ink") });
}

function drawSwapNotice(ctx: CanvasRenderingContext2D, world: World, day: number): void {
  if (world.swapDay === null || day < world.swapDay || day > world.swapDay + 90) return;
  plaque(ctx, `Day ${world.swapDay.toLocaleString("en-GB")}: the danger and safe fields swap. Old marks turn hollow.`, MAP_WIDTH / 2, 30, `700 17px ${FONT_BODY}`, token("wolf"));
}
