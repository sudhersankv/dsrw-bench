import { compact, score } from "../data/format";
import { loadIndex } from "../data/load";
import { rankModels } from "../data/rank";
import type { RankedEntry } from "../data/rank";
import type { SiteIndex, SubScoreId } from "../data/types";
import { mountField, type FieldController } from "../field/controller";
import { demoStamp, parcelSvg, subscoreCell } from "../glyphs";
import { escapeHtml } from "../theme";
import { errorState, siteFooter, siteHeader } from "./shell";

const SUB_COLUMNS: { id: SubScoreId; label: string }[] = [
  { id: "history", label: "Uses history" },
  { id: "adapt", label: "Adapts" },
  { id: "use", label: "Acts on old evidence" },
  { id: "recall", label: "Recalls" },
];

const MEASURE_TEXT = "Does reading a longer history help an AI model make a better choice? We test that with a sheep's diary, and a wolf that sometimes changes its mind.";

function subCells(ranked: RankedEntry): string {
  return SUB_COLUMNS.map((column) => {
    const value = ranked.entry.subscores[column.id] ?? null;
    return `<td class="num col-sub"><span class="sub-label-phone">${column.label}</span>${subscoreCell(value)}</td>`;
  }).join("");
}

function rowHtml(ranked: RankedEntry): string {
  const { entry, rank } = ranked;
  const flockValue = score(entry.flock_score);
  const flockClass = entry.flock_score === null ? "board-flock untestable" : "board-flock";
  const scoreNote = SUB_COLUMNS.map((column) => `${column.label} ${score(entry.subscores[column.id] ?? null)}`).join(", ");
  return `<tr>
    <td class="col-rank rank">${rank ?? "–"}</td>
    <td class="col-model board-model"><a href="#/model/${encodeURIComponent(entry.model_id)}">
      ${parcelSvg(entry.subscores, 48, `Score shape: ${scoreNote}`)}<span class="board-name">${escapeHtml(entry.display)}</span></a></td>
    <td class="col-flock num ${flockClass}">${flockValue}</td>
    ${subCells(ranked)}
    <td class="num col-sub"><span class="sub-label-phone">Longest diary</span>${compact(entry.max_tokens_tested)}</td>
  </tr>`;
}

function leaderboard(index: SiteIndex): string {
  const headers = SUB_COLUMNS.map((c) => `<th scope="col" class="num">${c.label}</th>`).join("");
  const rows = rankModels(index.models).map(rowHtml).join("");
  return `<div class="plain-scroll"><table class="board">
    <thead><tr><th scope="col" aria-label="Rank"></th><th scope="col">Model</th><th scope="col" class="num">Flock score, shared ${compact(index.shared_length_tokens)}</th>${headers}<th scope="col" class="num">Longest diary run</th></tr></thead>
    <tbody>${rows}</tbody>
  </table></div>`;
}

const EMPTY_BOARD = `<div class="board-empty">No results yet. Run <code>swb analyze</code> to publish the first ones.</div>`;

function boardLede(index: SiteIndex): string {
  const longest = Math.max(...index.models.map((m) => m.max_tokens_tested));
  const reach = index.is_demo ? "No real model has been run yet; these rows come from mock readers." : `The longest diary any model has read so far is ${compact(longest)} tokens.`;
  return `<p class="section-lede">Ranked on diaries up to ${compact(index.shared_length_tokens)} tokens, the longest length every model can read. ${reach} Each model is one parcel: four boundary stones, one per score. Further from the centre is better.</p>`;
}

function disclaimers(index: SiteIndex): string {
  return index.disclaimers.map((line) => `<p class="section-lede">${escapeHtml(line)}</p>`).join("");
}

export interface PageView {
  destroy: () => void;
  /** Settles once the page's data has been drawn, so scrolling can wait for the final layout. */
  ready?: Promise<void>;
}

export function renderHome(app: HTMLElement): PageView {
  app.innerHTML = `<main class="sheet">
    ${siteHeader("home", MEASURE_TEXT)}
    <div id="demo-stamp-slot"></div>
    <div id="field-slot"></div>
    <section id="leaderboard" aria-labelledby="board-title">
      <h2 class="section-title" id="board-title">Leaderboard</h2>
      <div id="board-slot"><p class="loading-state">Reading the results…</p></div>
    </section>
    ${siteFooter()}
  </main>`;
  const field: FieldController = mountField();
  app.querySelector("#field-slot")!.append(field.root);
  return { destroy: field.destroy, ready: fillLeaderboard(app) };
}

async function fillLeaderboard(app: HTMLElement): Promise<void> {
  const slot = app.querySelector<HTMLElement>("#board-slot")!;
  try {
    const index = await loadIndex();
    if (index.is_demo) app.querySelector("#demo-stamp-slot")!.innerHTML = demoStamp();
    slot.innerHTML = index.models.length === 0 ? EMPTY_BOARD : `${boardLede(index)}${disclaimers(index)}${leaderboard(index)}`;
  } catch {
    slot.innerHTML = errorState(
      "No results to show yet.",
      "The results file could not be read. Publish one with swb analyze, or run the site with npm run dev to see demo data.",
    );
  }
}
