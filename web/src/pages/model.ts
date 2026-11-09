import { downloadCard, drawCard } from "../card/draw";
import { renderChart } from "../charts/lineChart";
import { compact, longDate, score, signed, tokens, usd } from "../data/format";
import { loadCard } from "../data/load";
import type { HarnessResult, HypothesisResult, ModelCard, SubScore } from "../data/types";
import { demoStamp, parcelSvg, stripMeter } from "../glyphs";
import { escapeHtml, loadCanvasFonts } from "../theme";
import type { PageView } from "./home";
import { errorState, siteFooter, siteHeader } from "./shell";

const CHART_ORDER = ["steady", "reversal", "ladder"];

function siteHost(): string {
  return window.location.host || "sheep-wolf-bench";
}

function subscoreBlock(sub: SubScore): string {
  const value = sub.score === null ? `<span class="subscore-value is-untestable">Not testable</span>` : `<span class="subscore-value">${score(sub.score)}</span>`;
  const range = sub.lo !== null && sub.hi !== null ? `<p class="subscore-range">95% confidence range: ${sub.lo.toFixed(0)} to ${sub.hi.toFixed(0)}, from ${sub.cells_used} measurements.</p>` : "";
  const note = sub.note ? `<p class="subscore-range">${escapeHtml(sub.note)}</p>` : "";
  return `<div class="subscore">
    <h3 class="subscore-title"><span>${escapeHtml(sub.label)}</span>${value}</h3>
    ${stripMeter(sub.score, 320)}
    <p class="subscore-how">${escapeHtml(sub.how)}</p>${range}${note}
  </div>`;
}

function harnessRow(h: HarnessResult): string {
  return `<tr>
    <th scope="row">${escapeHtml(h.label)}</th>
    <td class="num">${signed(h.rescue)}</td>
    <td class="num">${signed(h.value_added)}</td>
    <td class="num">${tokens(h.tokens_per_decision)}</td>
    <td class="num">${usd(h.usd_per_life)}</td>
  </tr>`;
}

function seedsText(h: HypothesisResult): string {
  return h.seeds_used === null || h.seeds_expected === null ? "" : `${h.seeds_used} of ${h.seeds_expected} sheep lives`;
}

function hypothesisRow(h: HypothesisResult): string {
  const tagClass = h.verdict.replace(" ", "-");
  const effect = h.effect === null ? "not measured" : `${signed(h.effect)} (range ${h.lo?.toFixed(2)} to ${h.hi?.toFixed(2)})`;
  const note = h.note ? `<br /><span class="hypothesis-note">${escapeHtml(h.note)}</span>` : "";
  return `<tr>
    <th scope="row">${h.id}</th>
    <td>${escapeHtml(h.statement)}${note}</td>
    <td class="verdict-tag ${tagClass}">${h.verdict}</td>
    <td class="num">${effect}</td>
    <td class="num">${seedsText(h)}</td>
  </tr>`;
}

function registrationText(card: ModelCard): string {
  return card.registration_url
    ? `<a href="${encodeURI(card.registration_url)}">Publicly registered</a> before any real model was run. Each one is reported whatever it shows.`
    : "Planned before any real model is run, and not yet publicly registered. Each one is reported whatever it shows.";
}

function flockScopeText(card: ModelCard): string {
  const longest = compact(card.max_tokens_tested);
  if (card.flock_shared === null || card.shared_length_tokens >= card.max_tokens_tested) return `Scored on diaries up to ${longest} tokens.`;
  return `This number uses every length up to ${longest} tokens. On the shared ${compact(card.shared_length_tokens)} diaries used to rank models it is ${score(card.flock_shared)}.`;
}

function curvesSection(card: ModelCard): string {
  if (card.charts.every((chart) => chart.curves.length === 0)) return "";
  return `<section aria-labelledby="curves">
      <h2 class="section-title" id="curves">The three curves</h2>
      <p class="section-lede">The shaded band shows the 95% confidence range around the main line. Dashed lines are reference lines: simple code given the same diaries. A model can beat them.</p>
      <div id="charts"></div>
    </section>`;
}

function harnessSection(card: ModelCard): string {
  if (card.harness.length === 0) return "";
  return `<section aria-labelledby="harness">
      <h2 class="section-title" id="harness">Harness rescue and cost</h2>
      <p class="section-lede">Rescue is how much a harness helps compared with the whole diary. Value added is how much the model adds beyond the same harness run by code alone. Cost is for one 32,000-day sheep life, asked daily.</p>
      <div class="plain-scroll"><table class="plain-table">
        <thead><tr><th scope="col">What the AI gets to see</th><th scope="col" class="num">Rescue</th><th scope="col" class="num">Value added</th><th scope="col" class="num">Per decision</th><th scope="col" class="num">Per life</th></tr></thead>
        <tbody>${card.harness.map(harnessRow).join("")}</tbody>
      </table></div>
    </section>`;
}

function pageHtml(card: ModelCard): string {
  const scores = Object.fromEntries(card.subscores.map((s) => [s.id, s.score]));
  const flockClass = card.flock_score === null ? "flock-number is-untestable" : "flock-number";
  const topOnly = card.probabilities_source === "verbalized" ? `<p class="section-lede"><strong>Top-1 only.</strong> This model gives one answer instead of probabilities, so some scores cannot be measured.</p>` : "";
  return `
    ${siteHeader("model", "One model's full results, and the card you can post.")}
    ${card.is_demo ? demoStamp() : ""}
    <div class="model-head">
      <div>
        <h2 class="model-name">${escapeHtml(card.display)}</h2>
        <p class="model-verdict">${escapeHtml(card.verdict_line)}</p>
        ${topOnly}
      </div>
      <div class="flock">
        <div>
          <p class="${flockClass}">${score(card.flock_score)}</p>
          <p class="flock-caption">Flock score, out of 100</p>
          <p class="flock-scope">${flockScopeText(card)}</p>
        </div>
        ${parcelSvg(scores, 132, `Score shape for ${card.display}`)}
      </div>
    </div>
    <section aria-labelledby="scores">
      <h2 class="section-title" id="scores">Four scores, and how each one was worked out</h2>
      <p class="section-lede">The flock score is the average of Uses history, Adapts and Acts on old evidence. Recalls is shown next to it but left out, because the gap between Recalls and Acts is the finding.</p>
      <div class="subscores">${card.subscores.map(subscoreBlock).join("")}</div>
    </section>
    ${curvesSection(card)}
    ${harnessSection(card)}
    <section aria-labelledby="verdicts">
      <h2 class="section-title" id="verdicts">Hypotheses</h2>
      <p class="section-lede">${registrationText(card)}</p>
      <div class="plain-scroll"><table class="plain-table">
        <thead><tr><th scope="col">Id</th><th scope="col">What we checked</th><th scope="col">Result</th><th scope="col" class="num">Effect</th><th scope="col" class="num">Seeds</th></tr></thead>
        <tbody>${card.hypotheses.map(hypothesisRow).join("")}</tbody>
      </table></div>
    </section>
    <section aria-labelledby="tested">
      <h2 class="section-title" id="tested">What was tested</h2>
      <dl class="facts">
        <div><dt>Longest diary tested</dt><dd>${tokens(card.max_tokens_tested)}</dd></div>
        <div><dt>Requests made</dt><dd>${card.calls.toLocaleString("en-GB")}</dd></div>
        <div><dt>Input read</dt><dd>${compact(card.input_tokens)} tokens</dd></div>
        <div><dt>Money spent</dt><dd>${usd(card.usd_spent)}</dd></div>
        <div><dt>Sheep lives per test</dt><dd>${card.seeds}</dd></div>
        <div><dt>Data generated</dt><dd>${longDate(card.generated_at)}</dd></div>
      </dl>
    </section>
    <section aria-labelledby="card-title">
      <h2 class="section-title" id="card-title">The card</h2>
      <div class="download-row">
        <button type="button" class="download" data-format="landscape">Download PNG for X, 1200x675</button>
        <button type="button" class="download" data-format="portrait">Download PNG, 1080x1350</button>
        <a class="share-link" href="/model/${encodeURIComponent(card.model_id)}">Link with a preview image</a>
      </div>
      <canvas class="card-preview" aria-label="Preview of the downloadable card"></canvas>
    </section>
    ${siteFooter()}`;
}

function wireCard(sheet: HTMLElement, card: ModelCard): void {
  const host = siteHost();
  sheet.querySelectorAll<HTMLButtonElement>("[data-format]").forEach((button) => {
    button.addEventListener("click", () => void downloadCard(card, button.dataset.format as "landscape" | "portrait", host));
  });
  void loadCanvasFonts().then(() => {
    drawCard(sheet.querySelector<HTMLCanvasElement>(".card-preview")!, card, "landscape", host);
  });
}

export function renderModel(app: HTMLElement, modelId: string): PageView {
  app.innerHTML = `<main class="sheet">${siteHeader("model", "One model's full results, and the card you can post.")}<p class="loading-state">Reading the results…</p></main>`;
  const sheet = app.querySelector<HTMLElement>("main")!;
  void (async () => {
    try {
      const card = await loadCard(modelId);
      sheet.innerHTML = pageHtml(card);
      const charts = sheet.querySelector<HTMLElement>("#charts");
      const ordered = [...card.charts].filter((chart) => chart.curves.length > 0).sort((a, b) => CHART_ORDER.indexOf(a.id) - CHART_ORDER.indexOf(b.id));
      if (charts) ordered.forEach((chart) => charts.append(renderChart(chart)));
      wireCard(sheet, card);
    } catch {
      sheet.innerHTML = `${siteHeader("model", "One model's full results, and the card you can post.")}${errorState("That model has no published results.", "Go back to the leaderboard to see the models that have run.")}`;
    }
  })();
  return { destroy: () => undefined };
}
