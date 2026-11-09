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
} from "./types";

type Raw = Record<string, unknown>;

export class DataError extends Error {}

function asObject(value: unknown, where: string): Raw {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new DataError(`${where}: expected an object`);
  }
  return value as Raw;
}

function asArray(value: unknown, where: string): unknown[] {
  if (!Array.isArray(value)) throw new DataError(`${where}: expected a list`);
  return value;
}

function asNumber(value: unknown, where: string): number {
  if (typeof value !== "number" || Number.isNaN(value)) {
    throw new DataError(`${where}: expected a number`);
  }
  return value;
}

function asString(value: unknown, where: string): string {
  if (typeof value !== "string") throw new DataError(`${where}: expected text`);
  return value;
}

function asBool(value: unknown, where: string): boolean {
  if (typeof value !== "boolean") throw new DataError(`${where}: expected true or false`);
  return value;
}

/** A missing or null value means "not testable", never zero. */
function asOptionalNumber(value: unknown, where: string): number | null {
  return value === null || value === undefined ? null : asNumber(value, where);
}

function asOptionalString(value: unknown, where: string): string | null {
  return value === null || value === undefined ? null : asString(value, where);
}

function parsePoint(value: unknown, where: string): CurvePoint {
  const r = asObject(value, where);
  return {
    x: asNumber(r.x, `${where}.x`),
    y: asNumber(r.y, `${where}.y`),
    lo: asOptionalNumber(r.lo, `${where}.lo`),
    hi: asOptionalNumber(r.hi, `${where}.hi`),
  };
}

function parseCurve(value: unknown, where: string): Curve {
  const r = asObject(value, where);
  return {
    id: asString(r.id, `${where}.id`),
    label: asString(r.label, `${where}.label`),
    kind: r.kind === "baseline" ? "baseline" : "model",
    points: asArray(r.points, `${where}.points`).map((p, i) => parsePoint(p, `${where}.points[${i}]`)),
  };
}

function parseChart(value: unknown, where: string): Chart {
  const r = asObject(value, where);
  const id = r.id;
  if (id !== "steady" && id !== "reversal" && id !== "ladder") {
    throw new DataError(`${where}.id: unknown chart "${String(id)}"`);
  }
  return {
    id,
    title: asString(r.title, `${where}.title`),
    x_label: asString(r.x_label, `${where}.x_label`),
    y_label: asString(r.y_label, `${where}.y_label`),
    x_log: r.x_log !== false,
    y_min: asOptionalNumber(r.y_min, `${where}.y_min`) ?? 0,
    y_max: asOptionalNumber(r.y_max, `${where}.y_max`) ?? 1,
    curves: asArray(r.curves, `${where}.curves`).map((c, i) => parseCurve(c, `${where}.curves[${i}]`)),
    takeaway: asString(r.takeaway, `${where}.takeaway`),
  };
}

function parseSubScore(value: unknown, where: string): SubScore {
  const r = asObject(value, where);
  const id = r.id;
  if (id !== "history" && id !== "adapt" && id !== "recall" && id !== "use") {
    throw new DataError(`${where}.id: unknown sub-score "${String(id)}"`);
  }
  return {
    id,
    label: asString(r.label, `${where}.label`),
    score: asOptionalNumber(r.score, `${where}.score`),
    lo: asOptionalNumber(r.lo, `${where}.lo`),
    hi: asOptionalNumber(r.hi, `${where}.hi`),
    how: asString(r.how, `${where}.how`),
    cells_used: asNumber(r.cells_used, `${where}.cells_used`),
    note: r.note === null || r.note === undefined ? null : asString(r.note, `${where}.note`),
  };
}

function parseHarness(value: unknown, where: string): HarnessResult {
  const r = asObject(value, where);
  return {
    policy: asString(r.policy, `${where}.policy`) as HarnessResult["policy"],
    label: asString(r.label, `${where}.label`),
    rescue: asOptionalNumber(r.rescue, `${where}.rescue`),
    value_added: asOptionalNumber(r.value_added, `${where}.value_added`),
    tokens_per_decision: asNumber(r.tokens_per_decision, `${where}.tokens_per_decision`),
    usd_per_life: asNumber(r.usd_per_life, `${where}.usd_per_life`),
  };
}

function parseHypothesis(value: unknown, where: string): HypothesisResult {
  const r = asObject(value, where);
  const id = r.id;
  if (id !== "H1" && id !== "H2" && id !== "H3") {
    throw new DataError(`${where}.id: unknown hypothesis "${String(id)}"`);
  }
  const verdict = r.verdict;
  if (verdict !== "supported" && verdict !== "not supported" && verdict !== "untestable") {
    throw new DataError(`${where}.verdict: unknown verdict "${String(verdict)}"`);
  }
  return {
    id,
    statement: asString(r.statement, `${where}.statement`),
    verdict,
    effect: asOptionalNumber(r.effect, `${where}.effect`),
    lo: asOptionalNumber(r.lo, `${where}.lo`),
    hi: asOptionalNumber(r.hi, `${where}.hi`),
    p_holm: asOptionalNumber(r.p_holm, `${where}.p_holm`),
    seeds_used: asOptionalNumber(r.seeds_used, `${where}.seeds_used`),
    seeds_expected: asOptionalNumber(r.seeds_expected, `${where}.seeds_expected`),
    note: asOptionalString(r.note, `${where}.note`),
  };
}

export function parseModelCard(value: unknown): ModelCard {
  const r = asObject(value, "model card");
  return {
    model_id: asString(r.model_id, "model_id"),
    display: asString(r.display, "display"),
    is_demo: asBool(r.is_demo, "is_demo"),
    flock_score: asOptionalNumber(r.flock_score, "flock_score"),
    subscores: asArray(r.subscores, "subscores").map((s, i) => parseSubScore(s, `subscores[${i}]`)),
    charts: asArray(r.charts, "charts").map((c, i) => parseChart(c, `charts[${i}]`)),
    harness: asArray(r.harness, "harness").map((h, i) => parseHarness(h, `harness[${i}]`)),
    hypotheses: asArray(r.hypotheses, "hypotheses").map((h, i) => parseHypothesis(h, `hypotheses[${i}]`)),
    max_tokens_tested: asNumber(r.max_tokens_tested, "max_tokens_tested"),
    probabilities_source: r.probabilities_source === "verbalized" ? "verbalized" : "model",
    calls: asNumber(r.calls, "calls"),
    input_tokens: asNumber(r.input_tokens, "input_tokens"),
    usd_spent: asNumber(r.usd_spent, "usd_spent"),
    seeds: asNumber(r.seeds, "seeds"),
    verdict_line: asString(r.verdict_line, "verdict_line"),
    generated_at: asString(r.generated_at, "generated_at"),
    flock_shared: asOptionalNumber(r.flock_shared, "flock_shared"),
    shared_length_tokens: asOptionalNumber(r.shared_length_tokens, "shared_length_tokens") ?? 0,
    registration_url: asOptionalString(r.registration_url, "registration_url"),
  };
}

function parseIndexEntry(value: unknown, where: string): IndexEntry {
  const r = asObject(value, where);
  const raw = asObject(r.subscores ?? {}, `${where}.subscores`);
  const subscores: IndexEntry["subscores"] = {};
  for (const id of ["history", "adapt", "recall", "use"] as const) {
    subscores[id] = asOptionalNumber(raw[id], `${where}.subscores.${id}`);
  }
  return {
    model_id: asString(r.model_id, `${where}.model_id`),
    display: asString(r.display, `${where}.display`),
    flock_score: asOptionalNumber(r.flock_score, `${where}.flock_score`),
    subscores,
    max_tokens_tested: asNumber(r.max_tokens_tested, `${where}.max_tokens_tested`),
  };
}

export function parseSiteIndex(value: unknown): SiteIndex {
  const r = asObject(value, "site index");
  return {
    is_demo: asBool(r.is_demo, "is_demo"),
    generated_at: asString(r.generated_at, "generated_at"),
    spec_version: typeof r.spec_version === "string" ? r.spec_version : "v2",
    models: asArray(r.models, "models").map((m, i) => parseIndexEntry(m, `models[${i}]`)),
    shared_length_tokens: asNumber(r.shared_length_tokens, "shared_length_tokens"),
    disclaimers: asArray(r.disclaimers ?? [], "disclaimers").map((d, i) => asString(d, `disclaimers[${i}]`)),
    registration_url: asOptionalString(r.registration_url, "registration_url"),
  };
}
