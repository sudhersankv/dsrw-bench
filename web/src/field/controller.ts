import { compact, usd } from "../data/format";
import { token } from "../theme";
import { drawSheepGlyph, drawWolfGlyph } from "./animals";
import { buildFarm, fieldAt, type Farm } from "./geometry";
import { askDay, EXAMPLE_PRICE_NOTE, gradeOf, isGood, questionsFor, readerPick, viewTokens, VIEWS, type GameQuestion, type Grade, type MemoryView } from "./readers";
import { FieldRenderer, type Reveal } from "./render";
import { diaryLine, DIARY_DAYS, generateWorld, WINDOW_DAYS, type TestId, type World } from "./world";

export type { TestId };

const TESTS: { id: TestId; label: string; blurb: string }[] = [
  { id: "steady", label: "The steady wolf", blurb: "The wolf always prefers one field. A long diary can only help, if the AI really reads it." },
  { id: "reversal", label: "The wolf moves", blurb: "On day 2,000 the most dangerous and the safest fields swap. Every older mark now points the wrong way." },
  { id: "fog", label: "The old clue", blurb: "Fog hides the diary, except one bright block of 100 days of clear sightings. Fog then returns. Is that block still remembered 1,300 days later?" },
];

const SPEEDS = { slow: 12, normal: 120, fast: 600 } as const;
const ROUNDS_PER_LEVEL = 3;
const PHONE_WIDTH = 880;
type Speed = keyof typeof SPEEDS;
const TAPE_LINES = 26;
/** First days always run slowly so the diary can be read before the speed takes over. */
const INTRO_DAYS = 28;
const INTRO_RATE = 8;

export interface FieldController {
  root: HTMLElement;
  destroy: () => void;
}

interface Refs {
  canvas: HTMLCanvasElement;
  testButtons: HTMLButtonElement[];
  blurb: HTMLElement;
  memoryButtons: HTMLButtonElement[];
  memoryTokens: HTMLElement[];
  question: HTMLElement;
  skip: HTMLButtonElement;
  callButtons: HTMLButtonElement[];
  result: HTMLElement;
  scoreLine: HTMLElement;
  today: HTMLElement;
  play: HTMLButtonElement;
  restart: HTMLButtonElement;
  scrub: HTMLInputElement;
  speedButtons: HTMLButtonElement[];
  dayLabel: HTMLElement;
  bracket: HTMLElement;
  notch: HTMLElement;
  tape: HTMLElement;
}

function viewGlyph(view: MemoryView): string {
  if (view === "tally") {
    return `<svg viewBox="0 0 120 18" width="120" height="18" aria-hidden="true">
      <rect x="1" y="9" width="10" height="8" class="glyph-on"/><rect x="15" y="3" width="10" height="14" class="glyph-on"/>
      <rect x="29" y="11" width="10" height="6" class="glyph-on"/><rect x="43" y="6" width="10" height="11" class="glyph-on"/>
    </svg>`;
  }
  const lit = view === "whole" ? `<rect x="0" y="4" width="120" height="10" class="glyph-on"/>` : `<rect x="80" y="4" width="40" height="10" class="glyph-on"/>`;
  return `<svg viewBox="0 0 120 18" width="120" height="18" aria-hidden="true"><rect x="0" y="4" width="120" height="10" class="glyph-off"/>${lit}</svg>`;
}

function template(): string {
  const tests = TESTS.map((t) => `<button type="button" class="tab" data-test="${t.id}">${t.label}</button>`).join("");
  const memory = VIEWS.map(
    (v) => `<button type="button" class="memory" data-view="${v.id}">
      <span class="memory-title">${v.label}</span>
      ${viewGlyph(v.id)}
      <span class="memory-desc">${v.description}</span>
      <span class="memory-cost"><span data-tokens></span><span class="memory-life">${usd(v.usdPerLife)} per sheep life</span></span>
    </button>`,
  ).join("");
  const speeds = (Object.keys(SPEEDS) as Speed[]).map((s) => `<button type="button" class="speed" data-speed="${s}">${s[0].toUpperCase()}${s.slice(1)}</button>`).join("");
  return `
  <div class="field-lead">
    <p>Each day the sheep writes one line in its diary. <strong>The AI reads the diary and picks the safe field.</strong> You play the AI.</p>
    <ul class="map-key" aria-label="On the map">
      <li><canvas data-icon="sheep" width="72" height="44" aria-hidden="true"></canvas>The sheep</li>
      <li><canvas data-icon="wolf" width="72" height="44" aria-hidden="true"></canvas>A wolf, just seen</li>
      <li><canvas data-icon="cross" width="44" height="44" aria-hidden="true"></canvas>Wolf sighting</li>
      <li><canvas data-icon="ring" width="44" height="44" aria-hidden="true"></canvas>Sighting from before the wolf moved</li>
    </ul>
  </div>
  <div class="field-map">
    <canvas class="field-canvas" tabindex="-1" role="img"></canvas>
  </div>
  <div class="tabs" role="group" aria-label="Choose a test">${tests}</div>
  <p class="today-line" aria-live="off"></p>
  <aside class="field-panel">
    <p class="blurb"></p>
    <p class="score-line" aria-live="polite"></p>
    <h3 class="panel-title">What the AI gets to see</h3>
    <div class="memories" role="group" aria-label="Choose what the AI reads">${memory}</div>
    <p class="price-note">${EXAMPLE_PRICE_NOTE}</p>
    <h3 class="panel-title question"></h3>
    <button type="button" class="skip-ask">Skip to the question</button>
    <div class="calls"></div>
    <div class="result" aria-live="polite"></div>
  </aside>
  <div class="field-bar">
    <button type="button" class="play"></button>
    <button type="button" class="restart">New diary</button>
    <div class="timeline">
      <span class="bracket" aria-hidden="true"></span>
      <span class="notch" aria-hidden="true"></span>
      <input class="scrub" type="range" min="0" max="${DIARY_DAYS - 1}" value="0" step="1" aria-label="Day of the diary" />
    </div>
    <span class="day-label" aria-live="off"></span>
    <div class="speeds" role="group" aria-label="Playback speed">${speeds}</div>
  </div>
  <ol class="tape" aria-label="The sheep's diary, newest entry last"></ol>
  <p class="field-note">Simulated here with stronger wolf rates and 3,000 days so you can watch it. The AI models in the benchmark read the same kind of diary at far longer lengths.</p>`;
}

function paintIcons(root: HTMLElement): void {
  const ink = token("ink");
  root.querySelectorAll<HTMLCanvasElement>("[data-icon]").forEach((canvas) => {
    const ctx = canvas.getContext("2d")!;
    const [cx, cy] = [canvas.width / 2, canvas.height / 2];
    ctx.lineWidth = 4;
    ctx.strokeStyle = token("wolf");
    if (canvas.dataset.icon === "sheep") drawSheepGlyph(ctx, cx, cy, 15, 0, { body: token("sheep"), ink });
    else if (canvas.dataset.icon === "wolf") drawWolfGlyph(ctx, cx, cy, 14, 0, { body: token("wolf"), ink });
    else if (canvas.dataset.icon === "cross") {
      ctx.beginPath();
      ctx.moveTo(cx - 10, cy - 10);
      ctx.lineTo(cx + 10, cy + 10);
      ctx.moveTo(cx + 10, cy - 10);
      ctx.lineTo(cx - 10, cy + 10);
      ctx.stroke();
    } else {
      ctx.strokeStyle = token("wolf-stale");
      ctx.beginPath();
      ctx.arc(cx, cy, 10, 0, Math.PI * 2);
      ctx.stroke();
    }
  });
}

function collectRefs(root: HTMLElement): Refs {
  const all = <T extends Element>(selector: string): T[] => [...root.querySelectorAll<T>(selector)];
  const one = <T extends Element>(selector: string): T => root.querySelector<T>(selector)!;
  return {
    canvas: one("canvas.field-canvas"),
    testButtons: all("[data-test]"),
    blurb: one(".blurb"),
    memoryButtons: all("[data-view]"),
    memoryTokens: all("[data-tokens]"),
    question: one(".question"),
    skip: one(".skip-ask"),
    callButtons: [],
    result: one(".result"),
    scoreLine: one(".score-line"),
    today: one(".today-line"),
    play: one(".play"),
    restart: one(".restart"),
    scrub: one(".scrub"),
    speedButtons: all("[data-speed]"),
    dayLabel: one(".day-label"),
    bracket: one(".bracket"),
    notch: one(".notch"),
    tape: one(".tape"),
  };
}

function setPressed(buttons: HTMLButtonElement[], isOn: (button: HTMLButtonElement) => boolean): void {
  buttons.forEach((button) => button.setAttribute("aria-pressed", String(isOn(button))));
}

export function mountField(): FieldController {
  const root = document.createElement("section");
  root.className = "field";
  root.id = "field";
  root.setAttribute("aria-label", "The field: watch the sheep's diary being written");
  root.innerHTML = template();
  paintIcons(root);
  const refs = collectRefs(root);

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let seed = 1;
  let test: TestId = "steady";
  let world: World = generateWorld(test, seed);
  let farm: Farm = buildFarm(seed);
  let day = reducedMotion ? DIARY_DAYS - 1 : 0;
  let view: MemoryView = "whole";
  let speed: Speed = "normal";
  let playing = !reducedMotion;
  let reveal: Reveal | null = null;
  let visible = true;
  let lastTime = 0;
  let frame = 0;
  let lastTapeDay = -1;
  let picks: number[] = [];
  let answered = false;
  let round = 1;
  let right = 0;
  let asked = 0;
  let streak = 0;
  let labelledBucket = -1;
  let questions: GameQuestion[] = questionsFor(world);

  const renderer = new FieldRenderer(refs.canvas, world, farm);

  function resize(): void {
    renderer.resize(refs.canvas.clientWidth);
    requestDraw();
  }

  const observer = new ResizeObserver(resize);
  observer.observe(refs.canvas.parentElement!);
  const visibility = new IntersectionObserver(([entry]) => {
    visible = entry.isIntersecting;
    if (visible) lastTime = performance.now();
  });
  visibility.observe(root);

  function requestDraw(): void {
    renderer.draw({ day, view, reveal, labelScale: refs.canvas.clientWidth < 600 ? 1.7 : 1, animate: !reducedMotion && playing });
    syncChrome();
  }

  function syncTape(): void {
    const today = Math.floor(day);
    if (today === lastTapeDay) return;
    lastTapeDay = today;
    const lines: string[] = [];
    for (let d = Math.max(0, today - TAPE_LINES + 1); d <= today; d++) {
      const wolf = world.days[d].kind === "wolf" ? ' class="wolf"' : "";
      lines.push(`<li${wolf}>${diaryLine(world, d)}</li>`);
    }
    refs.tape.innerHTML = lines.join("");
  }

  function syncChrome(): void {
    const today = Math.floor(day);
    refs.dayLabel.textContent = `Day ${(today + 1).toLocaleString("en-GB")} of ${DIARY_DAYS.toLocaleString("en-GB")}`;
    refs.today.textContent = diaryLine(world, today);
    refs.today.classList.toggle("wolf", world.days[today].kind === "wolf");
    syncMapLabel(today);
    syncAsk(today);
    refs.scrub.value = String(today);
    syncBracket(today);
    syncTape();
    VIEWS.forEach((v, i) => (refs.memoryTokens[i].textContent = `${compact(viewTokens(v.id, today))} tokens now`));
    refs.play.textContent = playing ? "Pause" : day >= DIARY_DAYS - 1 ? "Replay" : "Play";
  }

  function syncMapLabel(today: number): void {
    const bucket = Math.floor(today / 100);
    if (bucket === labelledBucket) return;
    labelledBucket = bucket;
    const info = TESTS.find((t) => t.id === test)!;
    refs.canvas.setAttribute("aria-label", `Top-down map of four fields, ${world.names.join(", ")}. ${info.label}. Day ${today + 1} of the diary. Wolf sightings are marked in the field they happened.`);
  }

  function canAsk(today: number): boolean {
    return today >= askDay(world) && !answered;
  }

  function syncAsk(today: number): void {
    const ready = canAsk(today);
    refs.callButtons.forEach((button) => (button.disabled = !ready));
    refs.skip.hidden = ready || answered;
    refs.question.textContent = answered
      ? "Your answers are in"
      : ready
        ? questions[picks.length].text
        : `The question comes on day ${(askDay(world) + 1).toLocaleString("en-GB")}, once the diary has enough in it`;
    refs.canvas.style.cursor = ready ? "pointer" : "default";
  }

  function syncScore(): void {
    refs.scoreLine.textContent = `Round ${round} of ${ROUNDS_PER_LEVEL}. Score ${right} of ${asked}. Streak ${streak}.`;
  }

  function syncBracket(today: number): void {
    const pct = (d: number): number => (d / (DIARY_DAYS - 1)) * 100;
    const startDay = view === "window" ? Math.max(0, today - WINDOW_DAYS + 1) : 0;
    refs.bracket.style.left = view === "tally" ? "0%" : `${pct(startDay)}%`;
    refs.bracket.style.width = view === "tally" ? "0%" : `${pct(today) - pct(startDay)}%`;
    refs.bracket.classList.toggle("is-tally", view === "tally");
    const notchAt = world.swapDay ?? world.blockStart;
    refs.notch.hidden = notchAt === null;
    if (notchAt !== null) {
      refs.notch.style.left = `${pct(notchAt)}%`;
      refs.notch.style.width = world.blockEnd !== null ? `${pct(world.blockEnd - world.blockStart!)}%` : "2px";
      refs.notch.title = world.swapDay !== null ? "The swap" : "The one clear block";
    }
  }

  function loop(now: number): void {
    frame = requestAnimationFrame(loop);
    // rAF timestamps can precede performance.now(), so a first negative step is clamped away.
    const dt = Math.max(0, Math.min(0.1, (now - lastTime) / 1000));
    lastTime = now;
    if (!playing || !visible) return;
    const rate = speed !== "slow" && day < INTRO_DAYS ? INTRO_RATE : SPEEDS[speed];
    day = Math.min(DIARY_DAYS - 1, day + rate * dt);
    if (day >= DIARY_DAYS - 1) playing = false;
    requestDraw();
  }

  function buildCalls(): void {
    const container = root.querySelector<HTMLElement>(".calls")!;
    container.innerHTML = world.names
      .map((name, index) => `<button type="button" class="call" data-call="${index}">${name}</button>`)
      .join("");
    refs.callButtons = [...container.querySelectorAll<HTMLButtonElement>("[data-call]")];
    refs.callButtons.forEach((button) => button.addEventListener("click", () => makeCall(Number(button.dataset.call))));
  }

  function setWorld(nextSeed: number): void {
    seed = nextSeed;
    world = generateWorld(test, seed);
    farm = buildFarm(seed);
    renderer.setWorld(world, farm);
    reveal = null;
    day = reducedMotion ? DIARY_DAYS - 1 : 0;
    playing = !reducedMotion;
    lastTapeDay = -1;
    labelledBucket = -1;
    picks = [];
    answered = false;
    questions = questionsFor(world);
    refs.result.innerHTML = "";
    syncScore();
    const info = TESTS.find((t) => t.id === test)!;
    refs.blurb.textContent = info.blurb;
    setPressed(refs.testButtons, (b) => b.dataset.test === test);
    buildCalls();
    requestDraw();
  }

  function makeCall(field: number): void {
    if (!canAsk(Math.floor(day))) return;
    playing = false;
    picks.push(field);
    if (picks.length === questions.length) finishRound();
    requestDraw();
  }

  function readerRows(kind: GameQuestion["kind"], today: number): string {
    return VIEWS.map((v) => {
      const pickIndex = readerPick(world, v.id, today);
      const picked = pickIndex === null ? "No evidence left in view" : world.names[pickIndex];
      const grade: Grade | "Blind" = pickIndex === null ? "Blind" : gradeOf(world, kind, pickIndex);
      return `<tr><th scope="row">${v.label}</th><td>${picked}</td><td class="verdict-${grade.toLowerCase()}">${grade}</td></tr>`;
    }).join("");
  }

  function verdictLine(question: GameQuestion, field: number): string {
    const grade = gradeOf(world, question.kind, field);
    const name = world.names[field];
    if (question.kind === "report") return `${isGood(grade) ? "Right" : "Wrong"}: you said wolves were seen most on ${name}.`;
    if (question.kind === "decide") return `${isGood(grade) ? "Right" : "Wrong"}: you would keep the sheep off ${name}.`;
    if (grade === "Safest") return `${name} is the safest field. Good call.`;
    return grade === "Bitten" ? `${name} is the most dangerous field. The sheep gets bitten.` : `${name} is a middle field: risky, but not the worst.`;
  }

  function roundMessage(): string {
    if (round < ROUNDS_PER_LEVEL) return "";
    return `<p class="level-done"><strong>Level done: ${right} of ${asked} right.</strong> Try another test, or play this one again.</p>`;
  }

  function finishRound(): void {
    const today = Math.floor(day);
    answered = true;
    reveal = { chosen: picks[picks.length - 1], danger: world.hotNow, safe: world.safeNow };
    const grades = questions.map((question, index) => gradeOf(world, question.kind, picks[index]));
    asked += grades.length;
    right += grades.filter(isGood).length;
    streak = grades.every(isGood) ? streak + 1 : 0;
    const allGood = grades.every(isGood);
    const verdicts = questions.map((question, index) => `<strong>${verdictLine(question, picks[index])}</strong>`).join("<br />");
    const goal = world.test === "fog" ? `The old clue pointed at ${world.names[world.hotNow]}. A counter answers both questions the same way; the benchmark checks whether an AI can state the clue but no longer act on it.` : `The safest field tomorrow is ${world.names[world.safeNow!]}.`;
    refs.result.innerHTML = `
      <p class="verdict ${allGood ? "is-right" : "is-wrong"}">${verdicts}</p>
      <p class="verdict-goal">${goal}</p>
      <table class="readers"><caption>Simple counting code on this same diary, not an AI model</caption>
        <tbody>${readerRows(questions[questions.length - 1].kind, today)}</tbody></table>
      ${roundMessage()}
      <button type="button" class="next-round">${round < ROUNDS_PER_LEVEL ? "Next diary" : "Play this level again"}</button>`;
    refs.result.querySelector<HTMLButtonElement>(".next-round")!.addEventListener("click", advance);
    syncScore();
    if (window.innerWidth < PHONE_WIDTH) refs.result.scrollIntoView({ block: "nearest", behavior: reducedMotion ? "auto" : "smooth" });
  }

  function advance(): void {
    if (round < ROUNDS_PER_LEVEL) {
      round += 1;
    } else {
      resetLevel();
    }
    setWorld(seed + 1);
  }

  function resetLevel(): void {
    round = 1;
    right = 0;
    asked = 0;
    streak = 0;
  }

  refs.testButtons.forEach((button) =>
    button.addEventListener("click", () => {
      test = button.dataset.test as TestId;
      resetLevel();
      setWorld(seed);
    }),
  );
  refs.memoryButtons.forEach((button) =>
    button.addEventListener("click", () => {
      view = button.dataset.view as MemoryView;
      setPressed(refs.memoryButtons, (b) => b.dataset.view === view);
      requestDraw();
    }),
  );
  refs.speedButtons.forEach((button) =>
    button.addEventListener("click", () => {
      speed = button.dataset.speed as Speed;
      setPressed(refs.speedButtons, (b) => b.dataset.speed === speed);
    }),
  );
  refs.play.addEventListener("click", () => {
    if (day >= DIARY_DAYS - 1) {
      day = 0;
      lastTapeDay = -1;
      reveal = null;
      picks = [];
      answered = false;
      refs.result.innerHTML = "";
    }
    playing = !playing;
    requestDraw();
  });
  refs.restart.addEventListener("click", () => setWorld(seed + 1));
  refs.skip.addEventListener("click", () => {
    day = Math.max(day, askDay(world));
    playing = false;
    requestDraw();
  });
  refs.scrub.addEventListener("input", () => {
    day = Number(refs.scrub.value);
    playing = false;
    requestDraw();
  });
  refs.canvas.addEventListener("click", (event) => {
    const bounds = refs.canvas.getBoundingClientRect();
    const field = fieldAt(farm, renderer.pointToMap(event.clientX - bounds.left, event.clientY - bounds.top));
    if (field !== null) makeCall(field);
  });

  setPressed(refs.memoryButtons, (b) => b.dataset.view === view);
  setPressed(refs.speedButtons, (b) => b.dataset.speed === speed);
  setWorld(seed);
  lastTime = performance.now();
  frame = requestAnimationFrame(loop);

  return {
    root,
    destroy: () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      visibility.disconnect();
    },
  };
}
