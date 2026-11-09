import { compact, score } from "../data/format";
import type { Chart, Curve, ModelCard, SubScore } from "../data/types";
import { drawSheepGlyph, drawWolfGlyph } from "../field/animals";
import { contourSegments } from "../field/terrain";
import { createRng } from "../field/rng";
import { BEARINGS, DEMO_STAMP_TEXT, parcelVertex } from "../glyphs";
import { FONT_BODY, FONT_DISPLAY, loadCanvasFonts, token } from "../theme";

export type CardFormat = "landscape" | "portrait";

interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

interface CardLayout {
  width: number;
  height: number;
  titleSize: number;
  title: Rect;
  premiseSize: number;
  premise: Rect;
  nameSize: number;
  name: Rect;
  flock: Rect;
  flockSize: number;
  flockNoteSize: number;
  parcel: { cx: number; cy: number; r: number };
  parcelLabelSize: number;
  subs: Rect;
  subLabelSize: number;
  subGlossSize: number;
  curve: Rect;
  verdict: Rect;
  verdictSize: number;
  footer: Rect;
  motif: Rect;
  stampWidth: number;
  stampY: number;
}

const LAYOUTS: Record<CardFormat, CardLayout> = {
  landscape: {
    width: 1200,
    height: 675,
    titleSize: 32,
    title: { x: 58, y: 42, w: 580, h: 36 },
    premiseSize: 21,
    premise: { x: 58, y: 84, w: 580, h: 26 },
    nameSize: 46,
    name: { x: 58, y: 116, w: 540, h: 74 },
    flock: { x: 58, y: 196, w: 240, h: 226 },
    flockSize: 170,
    flockNoteSize: 18,
    parcel: { cx: 472, cy: 302, r: 78 },
    parcelLabelSize: 18,
    subs: { x: 640, y: 96, w: 500, h: 276 },
    subLabelSize: 24,
    subGlossSize: 16,
    curve: { x: 640, y: 384, w: 500, h: 196 },
    verdict: { x: 58, y: 468, w: 540, h: 108 },
    verdictSize: 22,
    footer: { x: 58, y: 596, w: 1084, h: 30 },
    motif: { x: 880, y: 40, w: 260, h: 50 },
    stampWidth: 900,
    stampY: 338,
  },
  portrait: {
    width: 1080,
    height: 1350,
    titleSize: 40,
    title: { x: 64, y: 56, w: 640, h: 44 },
    premiseSize: 30,
    premise: { x: 64, y: 108, w: 952, h: 36 },
    nameSize: 68,
    name: { x: 64, y: 150, w: 952, h: 122 },
    flock: { x: 64, y: 280, w: 480, h: 300 },
    flockSize: 240,
    flockNoteSize: 24,
    parcel: { cx: 776, cy: 430, r: 130 },
    parcelLabelSize: 26,
    subs: { x: 64, y: 650, w: 952, h: 276 },
    subLabelSize: 32,
    subGlossSize: 22,
    curve: { x: 64, y: 938, w: 952, h: 212 },
    verdict: { x: 64, y: 1160, w: 952, h: 94 },
    verdictSize: 28,
    footer: { x: 64, y: 1262, w: 952, h: 34 },
    motif: { x: 736, y: 54, w: 280, h: 52 },
    stampWidth: 900,
    stampY: 470,
  },
};

const PREMISE = "An AI reads a sheep's diary and must pick the safe field.";
const FLOCK_DEFINITION = "Flock score: the mean of Uses history, Adapts and Acts.";
const SUB_GLOSS: Record<SubScore["id"], string> = {
  history: "Steady wolf: how close to a simple counter",
  adapt: "The wolf moves: how close to a change detector",
  recall: "Old clue: reported, against a fresh clue",
  use: "Old clue: acted on, against a fresh clue",
};
const NAME_MIN_SIZE = 26;
const MIN_TEXT_SIZE = 12;

function setFont(ctx: CanvasRenderingContext2D, font: string): void {
  ctx.font = font;
}

/** Shrinks the size until the text fits the width, so any model name works. */
function fitFont(ctx: CanvasRenderingContext2D, text: string, weightAndFamily: (size: number) => string, maxSize: number, width: number, minSize: number): number {
  let size = maxSize;
  setFont(ctx, weightAndFamily(size));
  while (ctx.measureText(text).width > width && size > minSize) {
    size -= 2;
    setFont(ctx, weightAndFamily(size));
  }
  return size;
}

function wrapLines(ctx: CanvasRenderingContext2D, text: string, width: number): string[] {
  const lines: string[] = [];
  let line = "";
  for (const word of text.split(/\s+/)) {
    const candidate = line ? `${line} ${word}` : word;
    if (ctx.measureText(candidate).width > width && line) {
      lines.push(line);
      line = word;
    } else {
      line = candidate;
    }
  }
  if (line) lines.push(line);
  return lines;
}

function drawText(ctx: CanvasRenderingContext2D, lines: string[], x: number, y: number, lineHeight: number, maxLines: number): void {
  lines.slice(0, maxLines).forEach((line, index) => ctx.fillText(line, x, y + index * lineHeight));
}

function drawBackdrop(ctx: CanvasRenderingContext2D, layout: CardLayout, seed: number): void {
  ctx.fillStyle = token("paper");
  ctx.fillRect(0, 0, layout.width, layout.height);
  ctx.strokeStyle = token("contour-card");
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (const [x1, y1, x2, y2] of contourSegments(createRng(seed), layout.width, layout.height, 0.55, 14)) {
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
  }
  ctx.stroke();
  ctx.strokeStyle = token("ink");
  ctx.lineWidth = 4;
  ctx.strokeRect(24, 24, layout.width - 48, layout.height - 48);
  ctx.lineWidth = 1.5;
  ctx.strokeRect(32, 32, layout.width - 64, layout.height - 64);
  drawTicks(ctx, layout);
}

function drawTicks(ctx: CanvasRenderingContext2D, layout: CardLayout): void {
  ctx.strokeStyle = token("ink");
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  for (let x = 120; x < layout.width - 60; x += 100) {
    ctx.moveTo(x, 24);
    ctx.lineTo(x, 12);
    ctx.moveTo(x, layout.height - 24);
    ctx.lineTo(x, layout.height - 12);
  }
  for (let y = 120; y < layout.height - 60; y += 100) {
    ctx.moveTo(24, y);
    ctx.lineTo(12, y);
    ctx.moveTo(layout.width - 24, y);
    ctx.lineTo(layout.width - 12, y);
  }
  ctx.stroke();
}

function drawMotif(ctx: CanvasRenderingContext2D, layout: CardLayout): void {
  const { x, y, w, h } = layout.motif;
  ctx.fillStyle = token("field-a");
  ctx.fillRect(x, y, w, h);
  ctx.strokeStyle = token("ink");
  ctx.lineWidth = 2;
  ctx.strokeRect(x, y, w, h);
  ctx.setLineDash([3, 9]);
  ctx.beginPath();
  ctx.moveTo(x, y + h / 2);
  ctx.lineTo(x + w, y + h / 2);
  ctx.stroke();
  ctx.setLineDash([]);
  const size = h * 0.3;
  drawSheepGlyph(ctx, x + w * 0.28, y + h / 2, size, 0, { body: token("sheep"), ink: token("ink") });
  drawWolfGlyph(ctx, x + w * 0.74, y + h / 2, size * 0.92, Math.PI, { body: token("wolf"), ink: token("ink") });
}

function drawTitles(ctx: CanvasRenderingContext2D, layout: CardLayout, card: ModelCard): void {
  ctx.fillStyle = token("ink");
  const heading = (size: number): string => `700 ${size}px ${FONT_DISPLAY}`;
  const headingSize = fitFont(ctx, "Does the Sheep Remember the Wolf?", heading, layout.titleSize, layout.title.w, MIN_TEXT_SIZE);
  ctx.fillText("Does the Sheep Remember the Wolf?", layout.title.x, layout.title.y + headingSize);
  ctx.fillStyle = token("muted");
  const body = (size: number): string => `600 ${size}px ${FONT_BODY}`;
  const premiseSize = fitFont(ctx, PREMISE, body, layout.premiseSize, layout.premise.w, MIN_TEXT_SIZE);
  ctx.fillText(PREMISE, layout.premise.x, layout.premise.y + premiseSize);
  drawName(ctx, layout, card.display);
}

/** Breaks a model name at spaces, slashes and hyphens; a run too long to fit is split by character. */
function nameTokens(ctx: CanvasRenderingContext2D, name: string, width: number): string[] {
  return name.split(/(?<=[ /-])/).flatMap((token_) => {
    if (ctx.measureText(token_).width <= width) return [token_];
    const parts: string[] = [];
    let current = "";
    for (const char of token_) {
      if (ctx.measureText(current + char).width > width && current) {
        parts.push(current);
        current = char;
      } else {
        current += char;
      }
    }
    return current ? [...parts, current] : parts;
  });
}

function wrapName(ctx: CanvasRenderingContext2D, name: string, width: number): string[] {
  const lines: string[] = [];
  let line = "";
  for (const part of nameTokens(ctx, name, width)) {
    if (line && ctx.measureText(line + part).width > width) {
      lines.push(line);
      line = part;
    } else {
      line += part;
    }
  }
  if (line) lines.push(line);
  return lines.map((text) => text.trimEnd());
}

function ellipsize(ctx: CanvasRenderingContext2D, text: string, width: number): string {
  let cut = text;
  while (cut && ctx.measureText(`${cut}\u2026`).width > width) cut = cut.slice(0, -1);
  return `${cut.trimEnd()}\u2026`;
}

function fitName(ctx: CanvasRenderingContext2D, layout: CardLayout, name: string): { size: number; lines: string[] } {
  const { w, h } = layout.name;
  for (let size = layout.nameSize; size >= NAME_MIN_SIZE; size -= 2) {
    setFont(ctx, `800 ${size}px ${FONT_DISPLAY}`);
    const lines = wrapName(ctx, name, w);
    if (lines.length * size * 1.04 <= h) return { size, lines };
  }
  setFont(ctx, `800 ${NAME_MIN_SIZE}px ${FONT_DISPLAY}`);
  const lines = wrapName(ctx, name, w);
  const room = Math.max(1, Math.floor(h / (NAME_MIN_SIZE * 1.04)));
  if (lines.length <= room) return { size: NAME_MIN_SIZE, lines };
  const kept = lines.slice(0, room);
  kept[room - 1] = ellipsize(ctx, lines.slice(room - 1).join(""), w);
  return { size: NAME_MIN_SIZE, lines: kept };
}

function drawName(ctx: CanvasRenderingContext2D, layout: CardLayout, name: string): void {
  const { size, lines } = fitName(ctx, layout, name);
  ctx.fillStyle = token("ink");
  setFont(ctx, `800 ${size}px ${FONT_DISPLAY}`);
  drawText(ctx, lines, layout.name.x, layout.name.y + size * 0.92, size * 1.04, lines.length);
}

function flockScope(card: ModelCard): string {
  const longest = compact(card.max_tokens_tested);
  if (card.flock_shared === null || card.shared_length_tokens >= card.max_tokens_tested) {
    return `Scored on diaries up to ${longest} tokens.`;
  }
  return `All lengths up to ${longest} tokens. Leaderboard, shared ${compact(card.shared_length_tokens)}: ${score(card.flock_shared)}.`;
}

function drawFlock(ctx: CanvasRenderingContext2D, layout: CardLayout, card: ModelCard): void {
  const rect = layout.flock;
  ctx.fillStyle = token("ink");
  setFont(ctx, `700 ${Math.round(layout.flockSize * 0.15)}px ${FONT_DISPLAY}`);
  ctx.fillText("Flock score", rect.x, rect.y + layout.flockSize * 0.15);
  const value = score(card.flock_score);
  const display = (size: number): string => `800 ${size}px ${FONT_DISPLAY}`;
  const big = fitFont(ctx, value, display, card.flock_score === null ? Math.round(layout.flockSize * 0.42) : layout.flockSize, rect.w, MIN_TEXT_SIZE);
  ctx.fillText(value, rect.x, rect.y + layout.flockSize * 1.02);
  ctx.fillStyle = token("muted");
  if (card.flock_score !== null) {
    setFont(ctx, `400 ${layout.flockNoteSize}px ${FONT_BODY}`);
    ctx.fillText("out of 100", rect.x + big * 0.05, rect.y + layout.flockSize * 1.02 + layout.flockNoteSize * 1.3);
  }
  const note = (size: number): string => `400 ${size}px ${FONT_BODY}`;
  const lines = [FLOCK_DEFINITION, flockScope(card)];
  lines.forEach((line, index) => {
    fitFont(ctx, line, note, layout.flockNoteSize, layout.verdict.w, MIN_TEXT_SIZE);
    ctx.fillText(line, rect.x, rect.y + rect.h + layout.flockNoteSize * (0.9 + index * 1.15));
  });
}

function drawParcelLabels(ctx: CanvasRenderingContext2D, layout: CardLayout): void {
  const { cx, cy, r } = layout.parcel;
  const gap = layout.parcelLabelSize * 0.55;
  setFont(ctx, `600 ${layout.parcelLabelSize}px ${FONT_BODY}`);
  ctx.fillStyle = token("ink");
  BEARINGS.forEach((b) => {
    ctx.textAlign = b.dx > 0 ? "left" : b.dx < 0 ? "right" : "center";
    ctx.textBaseline = b.dy < 0 ? "alphabetic" : b.dy > 0 ? "top" : "middle";
    ctx.fillText(b.short, cx + b.dx * (r + gap), cy + b.dy * (r + gap));
  });
  ctx.textAlign = "left";
  ctx.textBaseline = "alphabetic";
}

function drawParcel(ctx: CanvasRenderingContext2D, layout: CardLayout, card: ModelCard): void {
  const { cx, cy, r } = layout.parcel;
  const value = (id: SubScore["id"]): number | null => card.subscores.find((s) => s.id === id)?.score ?? null;
  ctx.strokeStyle = token("muted");
  ctx.lineWidth = 1.5;
  ctx.setLineDash([5, 5]);
  ctx.beginPath();
  BEARINGS.forEach((b) => ctx.lineTo(cx + b.dx * r, cy + b.dy * r));
  ctx.closePath();
  ctx.stroke();
  ctx.setLineDash([]);
  BEARINGS.forEach((b) => {
    ctx.setLineDash(value(b.id) === null ? [4, 6] : []);
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx + b.dx * r, cy + b.dy * r);
    ctx.stroke();
  });
  ctx.setLineDash([]);
  const stones = BEARINGS.flatMap((b) => {
    const point = parcelVertex(b, value(b.id), cx, cy, r);
    return point ? [point] : [];
  });
  if (stones.length >= 2) {
    ctx.beginPath();
    stones.forEach((p, i) => (i === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y)));
    ctx.closePath();
    ctx.fillStyle = token("field-a");
    ctx.fill();
    ctx.strokeStyle = token("ink");
    ctx.lineWidth = 3;
    ctx.stroke();
  }
  ctx.fillStyle = token("ink");
  stones.forEach((p) => {
    ctx.beginPath();
    ctx.arc(p.x, p.y, 4, 0, Math.PI * 2);
    ctx.fill();
  });
  drawMissingTips(ctx, layout, value);
  drawParcelLabels(ctx, layout);
}

/** An open ring at the tip of an unmeasured bearing, so "not testable" cannot be read as zero. */
function drawMissingTips(ctx: CanvasRenderingContext2D, layout: CardLayout, value: (id: SubScore["id"]) => number | null): void {
  const { cx, cy, r } = layout.parcel;
  ctx.strokeStyle = token("ink");
  ctx.fillStyle = token("paper");
  ctx.lineWidth = 2;
  BEARINGS.filter((b) => value(b.id) === null).forEach((b) => {
    ctx.beginPath();
    ctx.arc(cx + b.dx * r, cy + b.dy * r, 6, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
  });
}

function drawSubRow(ctx: CanvasRenderingContext2D, layout: CardLayout, sub: SubScore, rect: Rect): void {
  const labelWidth = rect.w * 0.6;
  const meterX = rect.x + rect.w * 0.62;
  const meterW = rect.w * 0.26;
  const meterH = Math.min(rect.h * 0.32, 22);
  const centerY = rect.y + rect.h / 2;
  const family = (weight: number) => (size: number): string => `${weight} ${size}px ${FONT_BODY}`;
  ctx.fillStyle = token("ink");
  const labelSize = fitFont(ctx, sub.label, family(650), layout.subLabelSize, labelWidth, MIN_TEXT_SIZE);
  ctx.fillText(sub.label, rect.x, centerY - labelSize * 0.1);
  ctx.fillStyle = token("muted");
  const gloss = SUB_GLOSS[sub.id];
  fitFont(ctx, gloss, family(400), layout.subGlossSize, labelWidth, MIN_TEXT_SIZE);
  ctx.fillText(gloss, rect.x, centerY + layout.subGlossSize * 1.05);
  ctx.textBaseline = "middle";
  if (sub.score === null) {
    ctx.fillStyle = token("muted");
    setFont(ctx, `600 ${layout.subLabelSize * 0.9}px ${FONT_BODY}`);
    ctx.textAlign = "right";
    ctx.fillText("Not testable", rect.x + rect.w, centerY);
    ctx.textAlign = "left";
  } else {
    ctx.fillStyle = token("strip-ground");
    ctx.fillRect(meterX, centerY - meterH / 2, meterW, meterH);
    ctx.fillStyle = token("field-a-strong");
    ctx.fillRect(meterX, centerY - meterH / 2, (meterW * sub.score) / 100, meterH);
    ctx.strokeStyle = token("ink");
    ctx.lineWidth = 2;
    ctx.strokeRect(meterX, centerY - meterH / 2, meterW, meterH);
    ctx.fillStyle = token("ink");
    setFont(ctx, `800 ${layout.subLabelSize * 1.4}px ${FONT_DISPLAY}`);
    ctx.textAlign = "right";
    ctx.fillText(score(sub.score), rect.x + rect.w, centerY);
    ctx.textAlign = "left";
  }
  ctx.textBaseline = "alphabetic";
}

function drawSubs(ctx: CanvasRenderingContext2D, layout: CardLayout, card: ModelCard): void {
  const rows = card.subscores.slice(0, 4);
  const rowHeight = layout.subs.h / Math.max(rows.length, 1);
  rows.forEach((sub, index) => {
    drawSubRow(ctx, layout, sub, { x: layout.subs.x, y: layout.subs.y + rowHeight * index, w: layout.subs.w, h: rowHeight });
  });
}

const CONTRAST_OF = /_(7pt|2pt|high)$/;

function chartForCard(card: ModelCard): { chart: Chart; curves: Curve[] } | null {
  const chart = card.charts.find((c) => c.id === "steady" && c.curves.length > 0) ?? card.charts.find((c) => c.curves.length > 0);
  if (!chart) return null;
  const longest = (a: Curve, b: Curve): Curve => ((a.points.at(-1)?.x ?? 0) >= (b.points.at(-1)?.x ?? 0) ? a : b);
  const models = chart.curves.filter((c) => c.kind === "model" && c.points.length > 0);
  if (models.length === 0) return null;
  const raw = models.filter((c) => c.id.startsWith("raw"));
  const model = (raw.length > 0 ? raw : models).reduce(longest);
  const contrast = CONTRAST_OF.exec(model.id)?.[1] ?? null;
  const baseline = chart.curves.find((c) => c.kind === "baseline" && c.points.length > 0 && (contrast === null || c.id.endsWith(`_${contrast}`)));
  return { chart, curves: baseline ? [model, baseline] : [model] };
}

/** Draws right-aligned and returns the x where the legend starts, so the title can stop short of it. */
function drawCurveLegend(ctx: CanvasRenderingContext2D, rect: Rect, y: number, size: number, hasBaseline: boolean): number {
  const entries: { label: string; baseline: boolean }[] = [{ label: "This model", baseline: false }];
  if (hasBaseline) entries.push({ label: "Simple counter", baseline: true });
  setFont(ctx, `600 ${size}px ${FONT_BODY}`);
  let x = rect.x + rect.w;
  ctx.textBaseline = "middle";
  ctx.textAlign = "left";
  [...entries].reverse().forEach((entry) => {
    const textWidth = ctx.measureText(entry.label).width;
    x -= textWidth;
    ctx.fillStyle = token("ink");
    ctx.fillText(entry.label, x, y);
    x -= 42;
    ctx.strokeStyle = entry.baseline ? token("ink") : token("series-1");
    ctx.lineWidth = entry.baseline ? 2 : 3.5;
    ctx.setLineDash(entry.baseline ? [6, 5] : []);
    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.lineTo(x + 34, y);
    ctx.stroke();
    ctx.setLineDash([]);
    x -= 18;
  });
  ctx.textBaseline = "alphabetic";
  return x;
}

function drawCurve(ctx: CanvasRenderingContext2D, layout: CardLayout, card: ModelCard): void {
  const rect = layout.curve;
  const titleSize = layout.width > 1100 ? 22 : 30;
  const found = chartForCard(card);
  if (!found) {
    ctx.fillStyle = token("muted");
    setFont(ctx, `600 ${titleSize}px ${FONT_BODY}`);
    ctx.fillText("No curves: this model could not be tested.", rect.x, rect.y + titleSize * 1.6);
    return;
  }
  const { chart, curves } = found;
  const tickSize = titleSize * 0.68;
  const pad = { left: titleSize * 2.1, right: 12, top: titleSize + 22, bottom: titleSize + 12 };
  const xs = curves.flatMap((c) => c.points.map((p) => p.x)).filter((x) => x > 0);
  const [xMin, xMax] = [Math.min(...xs), Math.max(...xs)];
  const px = (v: number): number => {
    const span = chart.x_log ? Math.log10(xMax / xMin) || 1 : xMax - xMin || 1;
    const t = chart.x_log ? Math.log10(Math.max(v, xMin) / xMin) : v - xMin;
    return rect.x + pad.left + (t / span) * (rect.w - pad.left - pad.right);
  };
  const plotBottom = rect.y + rect.h - pad.bottom;
  const py = (v: number): number => plotBottom - ((v - chart.y_min) / (chart.y_max - chart.y_min)) * (plotBottom - rect.y - pad.top);
  const legendStart = drawCurveLegend(ctx, rect, rect.y + titleSize * 0.62, tickSize * 1.05, curves.length > 1);
  ctx.fillStyle = token("ink");
  const heading = (size: number): string => `700 ${size}px ${FONT_BODY}`;
  fitFont(ctx, chart.title, heading, titleSize, legendStart - rect.x, MIN_TEXT_SIZE);
  ctx.fillText(chart.title, rect.x, rect.y + titleSize);
  ctx.fillStyle = token("surface");
  ctx.fillRect(rect.x + pad.left, rect.y + pad.top, rect.w - pad.left - pad.right, plotBottom - rect.y - pad.top);
  ctx.strokeStyle = token("rule");
  ctx.lineWidth = 1;
  const yTicks = [chart.y_min, (chart.y_min + chart.y_max) / 2, chart.y_max];
  ctx.fillStyle = token("muted");
  setFont(ctx, `400 ${tickSize}px ${FONT_BODY}`);
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  yTicks.forEach((tick) => {
    ctx.beginPath();
    ctx.moveTo(rect.x + pad.left, py(tick));
    ctx.lineTo(rect.x + rect.w - pad.right, py(tick));
    ctx.stroke();
    ctx.fillText(tick.toFixed(1), rect.x + pad.left - 6, py(tick));
  });
  ctx.textAlign = "left";
  ctx.textBaseline = "alphabetic";
  curves.forEach((curve) => {
    const baseline = curve.kind === "baseline";
    ctx.strokeStyle = baseline ? token("ink") : token("series-1");
    ctx.lineWidth = baseline ? 2 : 3.5;
    ctx.setLineDash(baseline ? [8, 6] : []);
    ctx.beginPath();
    curve.points.forEach((p, i) => (i === 0 ? ctx.moveTo(px(p.x), py(p.y)) : ctx.lineTo(px(p.x), py(p.y))));
    ctx.stroke();
    ctx.setLineDash([]);
  });
  ctx.fillStyle = token("muted");
  setFont(ctx, `400 ${tickSize}px ${FONT_BODY}`);
  ctx.fillText(`${chart.x_label}: ${compact(xMin)} to ${compact(xMax)}. Up is ${chart.y_label.toLowerCase()}.`, rect.x, rect.y + rect.h - 4);
}

const MIN_VERDICT_SIZE = 14;

/** The verdict is the card's one sentence, so it shrinks to fit rather than losing its end. */
function fitVerdict(ctx: CanvasRenderingContext2D, layout: CardLayout, text: string): { size: number; lines: string[] } {
  const rect = layout.verdict;
  for (let size = layout.verdictSize; size > MIN_VERDICT_SIZE; size--) {
    setFont(ctx, `600 ${size}px ${FONT_BODY}`);
    const lines = wrapLines(ctx, text, rect.w);
    if (lines.length * size * 1.26 <= rect.h) return { size, lines };
  }
  setFont(ctx, `600 ${MIN_VERDICT_SIZE}px ${FONT_BODY}`);
  return { size: MIN_VERDICT_SIZE, lines: wrapLines(ctx, text, rect.w) };
}

function drawVerdict(ctx: CanvasRenderingContext2D, layout: CardLayout, card: ModelCard): void {
  const rect = layout.verdict;
  ctx.fillStyle = token("ink");
  const { size, lines } = fitVerdict(ctx, layout, card.verdict_line);
  drawText(ctx, lines, rect.x, rect.y + size, size * 1.26, lines.length);
}

function drawFooter(ctx: CanvasRenderingContext2D, layout: CardLayout, card: ModelCard, siteUrl: string): void {
  const rect = layout.footer;
  const size = layout.width > 1100 ? 22 : 30;
  ctx.fillStyle = token("ink");
  setFont(ctx, `600 ${size}px ${FONT_BODY}`);
  ctx.fillText(siteUrl, rect.x, rect.y + size);
  ctx.textAlign = "right";
  ctx.fillStyle = token("muted");
  setFont(ctx, `400 ${size * 0.86}px ${FONT_BODY}`);
  ctx.fillText(`Longest diary tested: ${compact(card.max_tokens_tested)} tokens`, rect.x + rect.w, rect.y + size);
  ctx.textAlign = "left";
}

function drawDemoStamp(ctx: CanvasRenderingContext2D, layout: CardLayout): void {
  const width = layout.stampWidth;
  const height = width * 0.125;
  ctx.save();
  ctx.translate(layout.width / 2, layout.stampY);
  ctx.rotate(-0.13);
  ctx.fillStyle = token("paper");
  ctx.globalAlpha = 0.95;
  ctx.fillRect(-width / 2, -height / 2, width, height);
  ctx.globalAlpha = 1;
  ctx.strokeStyle = token("wolf");
  ctx.lineWidth = 7;
  ctx.strokeRect(-width / 2, -height / 2, width, height);
  ctx.lineWidth = 2;
  ctx.strokeRect(-width / 2 + 12, -height / 2 + 12, width - 24, height - 24);
  ctx.fillStyle = token("wolf");
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  const family = (size: number): string => `800 ${size}px ${FONT_DISPLAY}`;
  fitFont(ctx, DEMO_STAMP_TEXT, family, Math.round(height * 0.62), width - 60, 24);
  ctx.fillText(DEMO_STAMP_TEXT, 0, 2);
  ctx.restore();
  ctx.textAlign = "left";
  ctx.textBaseline = "alphabetic";
}

function seedFor(modelId: string): number {
  return [...modelId].reduce((hash, char) => Math.imul(hash, 31) + char.charCodeAt(0), 7) >>> 0;
}

export function drawCard(canvas: HTMLCanvasElement, card: ModelCard, format: CardFormat, siteUrl: string): void {
  const layout = LAYOUTS[format];
  canvas.width = layout.width;
  canvas.height = layout.height;
  const ctx = canvas.getContext("2d")!;
  drawBackdrop(ctx, layout, seedFor(card.model_id));
  drawMotif(ctx, layout);
  drawTitles(ctx, layout, card);
  drawFlock(ctx, layout, card);
  drawParcel(ctx, layout, card);
  drawSubs(ctx, layout, card);
  drawCurve(ctx, layout, card);
  drawVerdict(ctx, layout, card);
  drawFooter(ctx, layout, card, siteUrl);
  if (card.is_demo) drawDemoStamp(ctx, layout);
}

/** Draws the card off-screen with fonts ready, then triggers a PNG download. */
export async function downloadCard(card: ModelCard, format: CardFormat, siteUrl: string): Promise<void> {
  await loadCanvasFonts();
  const canvas = document.createElement("canvas");
  drawCard(canvas, card, format, siteUrl);
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/png"));
  if (!blob) return;
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${card.model_id}-${format === "landscape" ? "1200x675" : "1080x1350"}.png`;
  anchor.click();
  URL.revokeObjectURL(url);
}
