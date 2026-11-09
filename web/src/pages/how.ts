import { loadIndex } from "../data/load";
import { demoStamp, parcelSvg } from "../glyphs";
import type { PageView } from "./home";
import { siteFooter, siteHeader } from "./shell";

const EXAMPLE_SCORES = { history: 82, adapt: 44, use: 61, recall: 90 };

export function renderHow(app: HTMLElement): PageView {
  app.innerHTML = `<main class="sheet">
    ${siteHeader("how", "The benchmark in plain words: the worlds, the scores, the reference lines and the limits.")}
    <div id="demo-stamp-slot"></div>
    <article class="prose">
      <h2>The idea</h2>
      <p>Some AI models are built to make one quick choice from a short list, and they often sit inside assistants that keep a growing record of everything so far. We ask whether reading that whole record actually helps, whether old entries can do harm, and when a few lines of code do the same job for far less money.</p>
      <p>To test it, a program writes a diary for an invented sheep. Each day says which of four fields the sheep grazed and what it saw: <em>Grazed Kell. Saw a crow.</em> Sometimes it saw a wolf. The sheep's grazing never depends on the AI, so every model reads exactly the same words.</p>

      <h2>The three worlds</h2>
      <dl>
        <dt>The steady wolf</dt>
        <dd>One field is always a bit more dangerous and one a bit safer. Nothing changes, so a longer diary can only help. If a model gets worse with more diary, it failed at reading, not at remembering.</dd>
        <dt>The wolf moves</dt>
        <dd>Partway through, the most dangerous and the safest fields swap places. Now old diary entries point the wrong way. We watch whether the model keeps trusting them, and how many days after the swap it takes to stop.</dd>
        <dt>The old clue</dt>
        <dd>Fog covers almost every day. One block of 100 days holds clear sightings, placed at a measured distance in the past. We ask both what the diary says and which field to avoid, using the same evidence, to see whether something can be remembered but not acted on.</dd>
      </dl>
      <p>The gap between the worst and safest field comes in sizes. A narrow gap is a few percentage points of wolf risk, a tiny gap is smaller still, and a wide gap is obvious.</p>

      <h2>The scores</h2>
      <dl>
        <dt>Uses history</dt>
        <dd>In the steady world, how much better than chance the model is at naming the danger field, as a share of what a simple counter gets from the same diaries.</dd>
        <dt>Adapts</dt>
        <dd>The same comparison in the world that swaps, measured against a change-detecting filter. It covers only swaps the filter has already spotted.</dd>
        <dt>Recalls</dt>
        <dd>How much of an old clue's effect on the model's reported beliefs survives once the clue is 100 or more days old, compared with the model's own response to a fresh clue.</dd>
        <dt>Acts on old evidence</dt>
        <dd>The same measurement, but for the model's choices rather than its reports.</dd>
        <dt>Flock score</dt>
        <dd>The average of Uses history, Adapts and Acts on old evidence. It is blank unless all three could be measured. Recalls is left out on purpose, because a model that remembers a clue but ignores it should not be rewarded for that.</dd>
      </dl>
      <div class="how-legend">
        ${parcelSvg(EXAMPLE_SCORES, 120, "Example score shape")}
        <p>Each model appears as a parcel of land. The four boundary stones sit north, east, south and west: Uses history, Adapts, Acts on old evidence, and Recalls. Further from the centre is better. An open ring at the edge means that score could not be measured, which is different from zero.</p>
      </div>

      <h2>Reference lines</h2>
      <p>A score of 100 does not mean a perfect mind. Uses history and Adapts compare the model with code: a simple counter and a change detector, given the same diary. Recalls and Acts compare the model with its own response to a recent clue, so a weak but steady model can still score 100 on them. None of these is a true limit, and a model can do better than a reference line.</p>
      <p>A measurement only counts when the reference is at least 0.20 above chance. Otherwise there is too little signal for a fair score, and it appears as "Not testable", never as zero.</p>

      <h2>Limits</h2>
      <p>Scores describe one model on one kind of task. The proper statistical tests are the three hypotheses on each model's page; everything else is descriptive. <span id="registration-note">They have not been publicly registered yet.</span></p>
      <p>The longest diaries were only run on models with large enough windows, so a model with a smaller window is scored on fewer lengths. The leaderboard ranks everyone on the lengths they all share, and each card shows both numbers.</p>
      <p>Models that return one answer instead of probabilities show "Top-1 only". The Recalls and Acts scores need probabilities, so those models cannot get them.</p>
      <p>When simple code computes the answer, the score says more about the code than the model. So the harness table reports rescue and value added separately, and only value added tests the model itself.</p>
    </article>
    ${siteFooter()}
  </main>`;
  const ready = fillFromIndex(app);
  return { destroy: () => undefined, ready };
}

async function fillFromIndex(app: HTMLElement): Promise<void> {
  try {
    const index = await loadIndex();
    if (index.is_demo) app.querySelector("#demo-stamp-slot")!.innerHTML = demoStamp();
    if (index.registration_url) {
      const note = app.querySelector("#registration-note")!;
      note.innerHTML = `They were <a href="${encodeURI(index.registration_url)}">publicly registered</a> before any real model was run.`;
    }
  } catch {
    // Without an index this page has nothing to add: it is still correct as written.
  }
}
