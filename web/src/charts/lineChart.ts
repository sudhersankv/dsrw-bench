import { compact } from "../data/format";
import type { Chart, Curve, CurvePoint } from "../data/types";
import { escapeHtml } from "../theme";

const SLOT_TOKENS = ["series-1", "series-2", "series-3", "series-4"];
const BASELINE_DASHES = ["7 5", "2 4", "11 4 2 4"];
/** A policy or readout keeps its color on every chart; unknown ids take the next free slot in their chart. */
const PREFERRED_SLOT: Record<string, number> = { raw: 0, w1000: 1, table: 2, e700: 2, oracle: 3, report: 0, decide: 1, find: 2 };
const CONTRAST_TITLES: Record<string, string> = { "7pt": "Narrow gap between fields", "2pt": "Tiny gap between fields", high: "Wide gap between fields" };

function policyOf(curve: Curve): string {
  return curve.id.split("_")[0];
}

function contrastOf(curve: Curve): string | null {
  const suffix = curve.id.split("_").pop() ?? "";
  return suffix in CONTRAST_TITLES ? suffix : null;
}

/** Keeps the main line and one reference per panel; the full set stays in the numbers table. */
function keptInPanel(chart: Chart, curve: Curve): boolean {
  if (chart.id !== "reversal") return true;
  return policyOf(curve) === "raw" || curve.id.startsWith("ref_filter");
}

/** One small multiple per contrast. Panel titles carry the contrast, so line names can stay short. */
function panelsFor(chart: Chart): { title: string; chart: Chart }[] {
  const contrasts = [...new Set(chart.curves.map(contrastOf))];
  return contrasts.map((contrast) => ({
    title: contrast === null ? "" : CONTRAST_TITLES[contrast],
    chart: {
      ...chart,
      curves: chart.curves
        .filter((curve) => contrastOf(curve) === contrast && keptInPanel(chart, curve))
        .map((curve) => ({ ...curve, label: curve.label.split(",")[0] })),
    },
  }));
}

function hasBand(curve: Curve): boolean {
  return policyOf(curve) === "raw" || curve.id === "report";
}
const chartSlots = new WeakMap<Chart, Map<string, number>>();

function slotsFor(chart: Chart): Map<string, number> {
  const cached = chartSlots.get(chart);
  if (cached) return cached;
  const slots = new Map<string, number>();
  const models = chart.curves.filter((curve) => curve.kind === "model");
  for (const curve of models) {
    const slot = PREFERRED_SLOT[policyOf(curve)];
    if (slot !== undefined && ![...slots.values()].includes(slot)) slots.set(curve.id, slot);
  }
  for (const curve of models) {
    if (slots.has(curve.id)) continue;
    const free = SLOT_TOKENS.findIndex((_, index) => ![...slots.values()].includes(index));
    if (free !== -1) slots.set(curve.id, free);
  }
  chartSlots.set(chart, slots);
  return slots;
}

function colorFor(chart: Chart, curve: Curve): string {
  if (curve.kind === "baseline") return "var(--ink)";
  const slot = slotsFor(chart).get(curve.id);
  return slot === undefined ? "var(--muted)" : `var(--${SLOT_TOKENS[slot]})`;
}

interface Scale {
  x: (v: number) => number;
  y: (v: number) => number;
  plot: { left: number; right: number; top: number; bottom: number };
}

function xDomain(chart: Chart): [number, number] {
  const xs = chart.curves.flatMap((c) => c.points.map((p) => p.x)).filter((x) => !chart.x_log || x > 0);
  return [Math.min(...xs), Math.max(...xs)];
}

function makeScale(chart: Chart, width: number, height: number, roomRight: number): Scale {
  const plot = { left: 46, right: width - roomRight, top: 12, bottom: height - 42 };
  const [xMin, xMax] = xDomain(chart);
  const toX = chart.x_log ? (v: number): number => Math.log10(Math.max(v, xMin)) : (v: number): number => v;
  const span = toX(xMax) - toX(xMin) || 1;
  const x = (v: number): number => plot.left + ((toX(v) - toX(xMin)) / span) * (plot.right - plot.left);
  const y = (v: number): number =>
    plot.bottom - ((v - chart.y_min) / (chart.y_max - chart.y_min)) * (plot.bottom - plot.top);
  return { x, y, plot };
}

function logTicks(min: number, max: number): number[] {
  const ticks = [min];
  for (let power = Math.ceil(Math.log10(min)); power <= Math.floor(Math.log10(max)); power++) {
    const tick = 10 ** power;
    if (tick > min * 1.4 && tick < max / 1.4) ticks.push(tick);
  }
  ticks.push(max);
  return ticks;
}

function xTicks(chart: Chart): number[] {
  const [min, max] = xDomain(chart);
  if (chart.x_log) return logTicks(min, max);
  return Array.from({ length: 5 }, (_, i) => min + ((max - min) * i) / 4);
}

function yTicks(chart: Chart): number[] {
  return Array.from({ length: 5 }, (_, i) => chart.y_min + ((chart.y_max - chart.y_min) * i) / 4);
}

function bandPath(points: CurvePoint[], s: Scale): string {
  const usable = points.filter((p): p is CurvePoint & { lo: number; hi: number } => p.lo !== null && p.hi !== null);
  if (usable.length < 2) return "";
  const upper = usable.map((p) => `${s.x(p.x)},${s.y(p.hi)}`);
  const lower = [...usable].reverse().map((p) => `${s.x(p.x)},${s.y(p.lo)}`);
  return `M${upper.join("L")}L${lower.join("L")}Z`;
}

function linePath(points: CurvePoint[], s: Scale): string {
  return `M${points.map((p) => `${s.x(p.x)},${s.y(p.y)}`).join("L")}`;
}

function gridAndAxes(chart: Chart, s: Scale): string {
  const yLines = yTicks(chart)
    .map((v) => {
      const zero = chart.y_min < 0 && v === 0;
      return `<line x1="${s.plot.left}" x2="${s.plot.right}" y1="${s.y(v)}" y2="${s.y(v)}" class="${zero ? "grid-zero" : "grid"}"/>
        <text x="${s.plot.left - 7}" y="${s.y(v) + 4}" class="tick" text-anchor="end">${v.toFixed(2).replace(/\.?0+$/, "") || "0"}</text>`;
    })
    .join("");
  const xLabels = xTicks(chart)
    .map((v) => `<line x1="${s.x(v)}" x2="${s.x(v)}" y1="${s.plot.bottom}" y2="${s.plot.bottom + 5}" class="axis"/>
      <text x="${s.x(v)}" y="${s.plot.bottom + 19}" class="tick" text-anchor="middle">${compact(v)}</text>`)
    .join("");
  const title = `<text x="${(s.plot.left + s.plot.right) / 2}" y="${s.plot.bottom + 36}" class="axis-title" text-anchor="middle">${escapeHtml(chart.x_label)}</text>`;
  return `${yLines}<line x1="${s.plot.left}" x2="${s.plot.right}" y1="${s.plot.bottom}" y2="${s.plot.bottom}" class="axis"/>${xLabels}${title}`;
}

function curveMarks(chart: Chart, s: Scale): string {
  let baselineIndex = 0;
  return chart.curves
    .map((curve) => {
      const color = colorFor(chart, curve);
      const band = hasBand(curve) ? bandPath(curve.points, s) : "";
      const bandEl = band ? `<path d="${band}" fill="${color}" opacity="0.15"/>` : "";
      const dash = curve.kind === "baseline" ? BASELINE_DASHES[baselineIndex++ % BASELINE_DASHES.length] : "";
      const line = `<path d="${linePath(curve.points, s)}" fill="none" stroke="${color}" stroke-width="2" ${dash ? `stroke-dasharray="${dash}"` : ""}/>`;
      const dots =
        curve.kind === "model"
          ? curve.points.map((p) => `<circle cx="${s.x(p.x)}" cy="${s.y(p.y)}" r="3" fill="${color}" stroke="var(--surface)" stroke-width="1.5"/>`).join("")
          : "";
      return bandEl + line + dots;
    })
    .join("");
}

function directLabels(chart: Chart, s: Scale): string {
  const items = chart.curves
    .filter((curve) => curve.points.length > 0)
    .map((curve) => {
      const last = curve.points[curve.points.length - 1];
      return { curve, y: s.y(last.y), x: s.x(last.x) };
    })
    .sort((a, b) => a.y - b.y);
  const gap = 16;
  for (let i = 1; i < items.length; i++) {
    if (items[i].y - items[i - 1].y < gap) items[i].y = items[i - 1].y + gap;
  }
  return items
    .map(({ curve, x, y }) => {
      return `<text x="${x + 8}" y="${y + 4}" class="direct-label">${escapeHtml(curve.label)}</text>`;
    })
    .join("");
}

function legend(chart: Chart): string {
  let baselineIndex = 0;
  const items = chart.curves
    .map((curve) => {
      const color = colorFor(chart, curve);
      const dash = curve.kind === "baseline" ? BASELINE_DASHES[baselineIndex++ % BASELINE_DASHES.length] : "";
      return `<li><svg width="26" height="10" aria-hidden="true"><line x1="0" x2="26" y1="5" y2="5" stroke="${color}" stroke-width="2.5" ${dash ? `stroke-dasharray="${dash}"` : ""}/></svg>${escapeHtml(curve.label)}</li>`;
    })
    .join("");
  return `<ul class="legend">${items}</ul>`;
}

function dataTable(chart: Chart): string {
  const xs = [...new Set(chart.curves.flatMap((c) => c.points.map((p) => p.x)))].sort((a, b) => a - b);
  const head = chart.curves.map((c) => `<th scope="col">${escapeHtml(c.label)}</th>`).join("");
  const rows = xs
    .map((x) => {
      const cells = chart.curves
        .map((c) => {
          const point = c.points.find((p) => p.x === x);
          return `<td>${point ? point.y.toFixed(2) : "–"}</td>`;
        })
        .join("");
      return `<tr><th scope="row">${compact(x)}</th>${cells}</tr>`;
    })
    .join("");
  return `<details class="numbers"><summary>Show the numbers</summary>
    <div class="numbers-scroll"><table><thead><tr><th scope="col">${escapeHtml(chart.x_label)}</th>${head}</tr></thead><tbody>${rows}</tbody></table></div></details>`;
}

function allX(chart: Chart): number[] {
  return [...new Set(chart.curves.flatMap((c) => c.points.map((p) => p.x)))].sort((a, b) => a - b);
}

function hoverRows(chart: Chart, x: number): string {
  return chart.curves
    .map((curve) => {
      const point = curve.points.find((p) => p.x === x);
      if (!point) return "";
      return `<tr><th scope="row"><span class="swatch" style="background:${colorFor(chart, curve)}"></span>${escapeHtml(curve.label)}</th><td>${point.y.toFixed(2)}</td></tr>`;
    })
    .join("");
}

function attachHover(root: HTMLElement, chart: Chart, s: Scale): void {
  const svg = root.querySelector("svg")!;
  const rule = root.querySelector<SVGLineElement>(".hover-rule")!;
  const tip = root.querySelector<HTMLElement>(".chart-tip")!;
  const xs = allX(chart);
  svg.addEventListener("pointermove", (event) => {
    const box = svg.getBoundingClientRect();
    const px = event.clientX - box.left;
    const nearest = xs.reduce((best, x) => (Math.abs(s.x(x) - px) < Math.abs(s.x(best) - px) ? x : best), xs[0]);
    rule.setAttribute("x1", String(s.x(nearest)));
    rule.setAttribute("x2", String(s.x(nearest)));
    rule.style.display = "";
    tip.innerHTML = `<p class="tip-x">${escapeHtml(chart.x_label)}: ${compact(nearest)}</p><table>${hoverRows(chart, nearest)}</table>`;
    tip.hidden = false;
    const tipWidth = tip.offsetWidth;
    const left = Math.max(0, Math.min(s.x(nearest) + 12, box.width - tipWidth - 2));
    tip.style.left = `${left}px`;
    tip.style.top = `${Math.max(4, event.clientY - box.top - 30)}px`;
  });
  svg.addEventListener("pointerleave", () => {
    tip.hidden = true;
    rule.style.display = "none";
  });
}

function drawInto(host: HTMLElement, chart: Chart): void {
  const width = host.clientWidth;
  if (width === 0) return;
  const height = Math.round(Math.min(330, Math.max(240, width * 0.52)));
  const roomRight = width >= 480 ? 160 : 14;
  const scale = makeScale(chart, width, height, roomRight);
  const labels = roomRight > 14 ? directLabels(chart, scale) : "";
  host.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" width="${width}" height="${height}" role="img" aria-label="${escapeHtml(chart.title)}: ${escapeHtml(chart.takeaway)}">
      ${gridAndAxes(chart, scale)}
      ${curveMarks(chart, scale)}
      ${labels}
      <line class="hover-rule" y1="${scale.plot.top}" y2="${scale.plot.bottom}" style="display:none"/>
    </svg>
    <div class="chart-tip" hidden></div>`;
  attachHover(host, chart, scale);
}

/** Builds one chart figure. Resizing the container redraws it at the new width. */
export function renderChart(chart: Chart): HTMLElement {
  const figure = document.createElement("figure");
  figure.className = "chart";
  const panels = panelsFor(chart);
  figure.innerHTML = `
    <h3 class="chart-title">${escapeHtml(chart.title)}</h3>
    <p class="chart-takeaway">${escapeHtml(chart.takeaway)}</p>
    <p class="chart-y">${escapeHtml(chart.y_label)}</p>
    <div class="chart-panels">${panels
      .map((panel) => `<div class="chart-panel">${panel.title ? `<h4 class="panel-heading">${escapeHtml(panel.title)}</h4>` : ""}<div class="chart-plot"></div></div>`)
      .join("")}</div>
    ${legend(panels[0].chart)}
    ${dataTable(chart)}`;
  figure.querySelectorAll<HTMLElement>(".chart-plot").forEach((plot, index) => {
    new ResizeObserver(() => drawInto(plot, panels[index].chart)).observe(plot);
  });
  return figure;
}
