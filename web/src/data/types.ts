/** Mirrors the Site* and ModelCard types in src/swb/contracts.py. */

export type SubScoreId = "history" | "adapt" | "recall" | "use";
export type ChartId = "steady" | "reversal" | "ladder";
export type Policy = "raw" | "w1000" | "e700" | "table" | "oracle" | "shuffled";

export interface CurvePoint {
  x: number;
  y: number;
  lo: number | null;
  hi: number | null;
}

export interface Curve {
  id: string;
  label: string;
  kind: "model" | "baseline";
  points: CurvePoint[];
}

export interface Chart {
  id: ChartId;
  title: string;
  x_label: string;
  y_label: string;
  x_log: boolean;
  y_min: number;
  y_max: number;
  curves: Curve[];
  takeaway: string;
}

export interface SubScore {
  id: SubScoreId;
  label: string;
  score: number | null;
  lo: number | null;
  hi: number | null;
  how: string;
  cells_used: number;
  note: string | null;
}

export interface HarnessResult {
  policy: Policy;
  label: string;
  rescue: number | null;
  value_added: number | null;
  tokens_per_decision: number;
  usd_per_life: number;
}

export interface HypothesisResult {
  id: "H1" | "H2" | "H3";
  statement: string;
  verdict: "supported" | "not supported" | "untestable";
  effect: number | null;
  lo: number | null;
  hi: number | null;
  p_holm: number | null;
  seeds_used: number | null;
  seeds_expected: number | null;
  note: string | null;
}

export interface ModelCard {
  model_id: string;
  display: string;
  is_demo: boolean;
  flock_score: number | null;
  subscores: SubScore[];
  charts: Chart[];
  harness: HarnessResult[];
  hypotheses: HypothesisResult[];
  max_tokens_tested: number;
  probabilities_source: "model" | "verbalized";
  calls: number;
  input_tokens: number;
  usd_spent: number;
  seeds: number;
  verdict_line: string;
  generated_at: string;
  flock_shared: number | null;
  shared_length_tokens: number;
  registration_url: string | null;
}

export interface IndexEntry {
  model_id: string;
  display: string;
  flock_score: number | null;
  subscores: Partial<Record<SubScoreId, number | null>>;
  max_tokens_tested: number;
}

export interface SiteIndex {
  is_demo: boolean;
  generated_at: string;
  spec_version: string;
  models: IndexEntry[];
  shared_length_tokens: number;
  disclaimers: string[];
  registration_url: string | null;
}
