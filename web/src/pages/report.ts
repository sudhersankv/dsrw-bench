import type { PageView } from "./home";
import { siteFooter, siteHeader } from "./shell";

export function renderReport(app: HTMLElement): PageView {
  app.innerHTML = `<main class="sheet">
    ${siteHeader("report", "What the first full run found, how it was run, and what it cannot tell you.")}
    <article class="prose">
      <h2>The short answer</h2>
      <p><strong>Snap can find a fact almost anywhere in a long diary, but it barely learns patterns from one.</strong> It recalled a single event correctly 91% to 99% of the time, even from 12,921 days back. Yet when the pattern was spread across 22,000 days, it put 27% on the dangerous field, against 25% for pure guessing and 67% for a simple counter.</p>
      <p>Reading more of the diary did not meaningfully help. A four-row table of counts, made by a few lines of code, took the same model from 27% to 55% while using a tiny fraction of the context.</p>

      <h2>What we ran</h2>
      <p>On November 9, 2026, an invented sheep's diary was given to each model as raw text. Snap made 10,020 main-run calls, with diaries up to 256K tokens, and Jev read whole diaries of up to about 16K tokens across 4,020 calls. Each condition used 20 to 30 independent diaries. Every answer was asked five times with shuffled options. Snap cost $22.88 including the pilot.</p>
      <dl>
        <dt>The steady wolf</dt>
        <dd>One field is always a little more dangerous. Can a model pick up that pattern as the diary grows?</dd>
        <dt>The wolf moves</dt>
        <dd>The most dangerous and safest fields swap. Does old history mislead the model?</dd>
        <dt>The old clue</dt>
        <dd>One block of evidence sits at a controlled distance in the past. Is it still found, and is it still acted on?</dd>
      </dl>

      <h2>The three pre-set tests (Snap)</h2>
      <dl>
        <dt>H1: history older than 1,000 days adds information. Not supported.</dt>
        <dd>At 256K tokens with a tiny gap between fields, the whole diary beat the last 1,000 days by 0.018 in probability (95% interval −0.002 to 0.040). The test required at least 0.05.</dd>
        <dt>H2: the model can report evidence it no longer acts on. Untestable.</dt>
        <dd>The test needs the answer to grow when evidence grows, and it didn't: the stronger evidence block moved the report answer less than the weaker one. So the planned ratio can't measure memory.</dd>
        <dt>H3: after a swap, recent days beat the whole diary. Not supported.</dt>
        <dd>The last 1,000 days did better by 0.024 (95% interval 0.004 to 0.049). That difference is probably real but falls short of the 0.05 the test required.</dd>
      </dl>

      <h2>What we learned</h2>
      <ul>
        <li><strong>Finding is not learning.</strong> Snap's retrieval held at every distance tested. Adding up evidence across a long diary is where it broke down.</li>
        <li><strong>A longer diary did not raise the score.</strong> On the 7-point steady wolf, Snap stayed flat, going from 33% to 30% between 1K and 56K tokens, while a simple counter climbed from 33% to 79%.</li>
        <li><strong>Distance alone did not cause forgetting.</strong> A single clue moved Snap's answer at least as much at 12,921 days as at 1 day, and the oldest clues had the strongest effect. A score of 100 on the old-clue tests means "no fading", not "strong effect".</li>
        <li><strong>Knowing and deciding came apart.</strong> With nine sightings, the clue moved the "where were wolves seen" answer five to seven times as much as the "which field to avoid" answer, at every distance. This is descriptive, because H2 could not be tested.</li>
        <li><strong>Stale history misled Snap only mildly.</strong> On the narrow gap it barely responded to the pattern at all, so old evidence had little to mislead. On the wide gap it leaned toward the old field until the swap was about 6,000 days old, far behind a change-detecting filter.</li>
        <li><strong>Code did the remembering better and far cheaper.</strong> Handing the model a table of counts was the most useful harness in this run, at about 650 tokens instead of 256,000. This supports having code do the counting on tasks like this one.</li>
        <li><strong>Models differ in basic ways.</strong> Jev gave nearly one-hot answers and varied between identical calls, so it is scored as top-1 only. It stayed flat at about 37% to 39% as its diary grew.</li>
      </ul>

      <h2>What could be wrong</h2>
      <ul>
        <li><strong>Not publicly preregistered.</strong> The hypotheses and code were frozen in a git tag before the runs, but not registered on OSF. Subquadratic supplied Snap's credits, so independent replication matters.</li>
        <li><strong>One task, one framing.</strong> The diaries use neutral words and random field names. Other formats may behave differently and have not been tested.</li>
        <li><strong>Long-diary results are Snap only.</strong> Nothing here shows that a bigger context window makes a better model, because window size can't be separated from everything else that differs between models.</li>
        <li><strong>OpenJev was excluded by a pre-set rule.</strong> It failed two pilot checks: reading a simple diary and showing no option bias.</li>
        <li><strong>Some plans changed after the pilot.</strong> Diaries came out shorter than planned, at about 22,000 days instead of 32,000, because real tokens per day were higher. Jev's limit proved to be about 33,000 tokens, not the listed 65,536. All changes are listed in the preregistration amendments.</li>
      </ul>

      <h2>Not tested yet</h2>
      <p>Random switching, gradual change, cues that signal which field is dangerous, a wolf that reacts to the sheep, other diary formats, gist-style summaries, and step-by-step reasoning models.</p>
    </article>
    ${siteFooter()}
  </main>`;
  return { destroy: () => undefined };
}
