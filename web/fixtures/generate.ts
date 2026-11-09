/** Demo data for development: seeded fakes shaped like the real /data files. Never included in production builds. */

import type {
  Chart,
  Curve,
  CurvePoint,
  HarnessResult,
  HypothesisResult,
  IndexEntry,
  ModelCard,
  SiteIndex,
  SubScore,
  SubScoreId,
} from "../src/data/types";

function mulberry32(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

type Rand = () => number;

interface FakeModel {
  id: string;
  display: string;
  source: "model" | "verbalized";
  maxTokens: number;
  history: number;
  adapt: number;
  use: number;
  recall: number;
  seed: number;
}

const FAKE_MODELS: FakeModel[] = [
  { id: "mock-counter", display: "Mock counter reader", source: "model", maxTokens: 256000, history: 0.88, adapt: 0.42, use: 0.71, recall: 0.86, seed: 11 },
  { id: "mock-exponential", display: "Mock exponential reader", source: "model", maxTokens: 112000, history: 0.58, adapt: 0.79, use: 0.44, recall: 0.62, seed: 12 },
  { id: "mock-window", display: "Mock window reader", source: "model", maxTokens: 56000, history: 0.41, adapt: 0.69, use: 0.16, recall: 0.2, seed: 13 },
  { id: "mock-primacy", display: "Mock primacy reader", source: "model", maxTokens: 56000, history: 0.3, adapt: 0.12, use: 0.55, recall: 0.74, seed: 14 },
  { id: "mock-verbalized", display: "Mock verbalized reader with a long display name", source: "verbalized", maxTokens: 56000, history: 0.52, adapt: 0.33, use: 0, recall: 0, seed: 15 },
];

const LENGTHS = [1000, 4000, 16000, 56000, 112000, 256000];
const SWAP_LENGTHS = [6, 16, 42, 110, 290, 760, 2000, 5300, 14000];
const LAGS = [1, 3, 10, 100, 300, 1000, 1900];

function clamp(value: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, value));
}

function noisyPoint(x: number, y: number, spread: number, rand: Rand, lo: number, hi: number): CurvePoint {
  const value = clamp(y + (rand() - 0.5) * spread * 0.5, lo, hi);
  return { x, y: value, lo: clamp(value - spread, lo, hi), hi: clamp(value + spread, lo, hi) };
}

function steadyChart(model: FakeModel, rand: Rand): Chart {
  const lengths = LENGTHS.filter((length) => length <= model.maxTokens);
  const ceiling = (length: number): number => Math.min(0.95, 0.27 + 0.13 * Math.log2(length / 1000));
  const curve = (id: string, label: string, gain: number, cap: number): Curve => ({
    id,
    label,
    kind: "model",
    points: lengths.map((length) =>
      noisyPoint(length, Math.min(cap, 0.25 + (ceiling(length) - 0.25) * gain), 0.05, rand, 0, 1),
    ),
  });
  const longest = lengths[lengths.length - 1];
  return {
    id: "steady",
    title: "The steady wolf",
    x_label: "Diary length (tokens)",
    y_label: "Probability on the wolf's real favourite",
    x_log: true,
    y_min: 0,
    y_max: 1,
    curves: [
      curve("raw", "Whole diary", model.history, 0.95),
      curve("w1000", "Last 1,000 days", model.history * 0.8, 0.46),
      curve("table", "Code tally", 1.05, 0.96),
      { id: "beta_ceiling", label: "Counting ceiling", kind: "baseline", points: lengths.map((x) => ({ x, y: ceiling(x), lo: null, hi: null })) },
    ],
    takeaway: `Demo: the whole diary reaches ${Math.round(ceiling(longest) * model.history * 100)}% on the favourite field at the longest length this reader tried.`,
  };
}

function reversalChart(model: FakeModel, rand: Rand): Chart {
  const shape = (m: number, crossover: number, sharpness: number): number =>
    clamp(Math.tanh(Math.log10(m / crossover) * sharpness), -0.95, 0.95);
  const curve = (id: string, label: string, crossover: number, sharpness: number): Curve => ({
    id,
    label,
    kind: "model",
    points: SWAP_LENGTHS.map((m) => noisyPoint(m, shape(m, crossover, sharpness), 0.09, rand, -1, 1)),
  });
  return {
    id: "reversal",
    title: "The wolf moves",
    x_label: "Days since the swap",
    y_label: "New field minus old field",
    x_log: true,
    y_min: -1,
    y_max: 1,
    curves: [
      curve("raw", "Whole diary", 300 + (1 - model.adapt) * 1800, 1.6),
      curve("w1000", "Last 1,000 days", 700, 2.6),
      curve("e700", "Code tally (recent days count more)", 500, 2.2),
      { id: "filter_ceiling", label: "Change detector ceiling", kind: "baseline", points: SWAP_LENGTHS.map((x) => ({ x, y: shape(x, 90, 2.4), lo: null, hi: null })) },
    ],
    takeaway: "Demo: the whole diary needs many more days after the swap before it trusts the new field.",
  };
}

function ladderChart(model: FakeModel, rand: Rand): Chart {
  const fall = (lag: number, strength: number): number =>
    1.6 * Math.exp(-lag / (160 + strength * 1600)) * (0.4 + strength * 0.6);
  const curve = (id: string, label: string, strength: number): Curve => ({
    id,
    label,
    kind: "model",
    points: LAGS.map((lag) => noisyPoint(lag, fall(lag, strength), 0.14, rand, 0, 2.2)),
  });
  const comparison = model.recall >= model.use ? "better than" : "about as well as";
  return {
    id: "ladder",
    title: "The old clue",
    x_label: "Days ago the clue appeared",
    y_label: "Evidence still in use (log-odds shift)",
    x_log: true,
    y_min: 0,
    y_max: 2.2,
    curves: [curve("report", "Reports the clue", model.recall), curve("decide", "Acts on the clue", model.use)],
    takeaway: `Demo: the clue is reported ${comparison} it is acted on at long lags.`,
  };
}

function measuredSubScore(id: SubScoreId, label: string, value: number, how: string): SubScore {
  return {
    id,
    label,
    score: value * 100,
    lo: Math.max(0, value * 100 - 7),
    hi: Math.min(100, value * 100 + 7),
    how,
    cells_used: 8,
    note: null,
  };
}

function untestableSubScore(id: SubScoreId, label: string): SubScore {
  return {
    id,
    label,
    score: null,
    lo: null,
    hi: null,
    how: "This reader gives one answer instead of probabilities, so there are no log-odds shifts to measure.",
    cells_used: 0,
    note: "Top-1 only",
  };
}

function subscores(model: FakeModel): SubScore[] {
  const verbalized = model.source === "verbalized";
  return [
    measuredSubScore("history", "Uses history", model.history, "Demo: mean probability on the wolf's favourite field above 0.25, divided by the counting ceiling above 0.25, over 6 diary lengths."),
    measuredSubScore("adapt", "Adapts", model.adapt, "Demo: mean probability on the new field above 0.25, divided by the change detector's above 0.25, over 9 swap timings."),
    verbalized ? untestableSubScore("recall", "Recalls") : measuredSubScore("recall", "Recalls", model.recall, "Demo: mean of RK(report) for clues 100 or more days old, on the statistical rung."),
    verbalized ? untestableSubScore("use", "Acts on old evidence") : measuredSubScore("use", "Acts on old evidence", model.use, "Demo: mean of RK(decide) for clues 100 or more days old, same cells as Recalls."),
  ];
}

function flockScore(subs: SubScore[]): number | null {
  const parts = subs.filter((sub) => sub.id !== "recall").map((sub) => sub.score);
  return parts.every((part): part is number => part !== null)
    ? parts.reduce((a, b) => a + b, 0) / parts.length
    : null;
}

function harness(rand: Rand): HarnessResult[] {
  const row = (policy: HarnessResult["policy"], label: string, tokens: number, usd: number, offset: number): HarnessResult => ({
    policy,
    label,
    rescue: offset + rand() * 0.08,
    value_added: offset - 0.03 + rand() * 0.06,
    tokens_per_decision: tokens,
    usd_per_life: usd,
  });
  return [
    row("w1000", "Last 1,000 days", 8000, 10.24, 0.05),
    row("e700", "Code tally (recent days count more)", 100, 0.13, 0.12),
    row("table", "Code tally (all time)", 100, 0.13, 0.02),
  ];
}

function hypotheses(rand: Rand): HypothesisResult[] {
  const row = (id: HypothesisResult["id"], statement: string, verdict: HypothesisResult["verdict"], effect: number | null): HypothesisResult => ({
    id,
    statement,
    verdict,
    effect,
    lo: effect === null ? null : effect - 0.06,
    hi: effect === null ? null : effect + 0.06,
    p_holm: effect === null ? null : Number((0.002 + rand() * 0.05).toFixed(3)),
    seeds_used: 8,
    seeds_expected: 30,
    note: null,
  });
  return [
    row("H1", "History beyond the last 1,000 days adds information.", "supported", 0.21),
    row("H2", "The model can report evidence that it no longer acts on.", "not supported", 0.09),
    row("H3", "After a reversal, a recent window beats the full diary.", "untestable", null),
  ];
}

function buildCard(model: FakeModel): ModelCard {
  const rand = mulberry32(model.seed);
  const subs = subscores(model);
  return {
    model_id: model.id,
    display: model.display,
    is_demo: true,
    flock_score: flockScore(subs),
    subscores: subs,
    charts: [steadyChart(model, rand), reversalChart(model, rand), ladderChart(model, rand)],
    harness: harness(rand),
    hypotheses: hypotheses(rand),
    max_tokens_tested: model.maxTokens,
    probabilities_source: model.source,
    calls: 1880,
    input_tokens: 41_300_000,
    usd_spent: 1.73,
    seeds: 8,
    verdict_line: "Demo verdict: remembers the old clue when asked, but ignores it when choosing a field.",
    generated_at: "2026-11-08T12:00:00Z",
    flock_shared: flockScore(subs),
    shared_length_tokens: 56000,
    registration_url: null,
  };
}

function indexEntry(card: ModelCard): IndexEntry {
  const subs: IndexEntry["subscores"] = {};
  for (const sub of card.subscores) subs[sub.id] = sub.score;
  return { model_id: card.model_id, display: card.display, flock_score: card.flock_score, subscores: subs, max_tokens_tested: card.max_tokens_tested };
}

export function generateFixtures(): Map<string, unknown> {
  const cards = FAKE_MODELS.map(buildCard);
  const index: SiteIndex = {
    is_demo: true,
    generated_at: "2026-11-08T12:00:00Z",
    spec_version: "v2",
    models: cards.map(indexEntry),
    shared_length_tokens: 56000,
    disclaimers: ["Everything on this page comes from simulated readers. No model result is shown."],
    registration_url: null,
  };
  const files = new Map<string, unknown>([["/data/index.json", index]]);
  for (const card of cards) files.set(`/data/models/${card.model_id}.json`, card);
  return files;
}
