import { BLOCK_END, SWAP_DAY, WINDOW_DAYS, type World } from "./world";

export type MemoryView = "whole" | "window" | "tally";

export interface ViewInfo {
  id: MemoryView;
  label: string;
  /** Cost per 32,000-day life queried daily, at 8 tokens per day and an example $0.04 per 1M. */
  usdPerLife: number;
  description: string;
}

export const VIEWS: ViewInfo[] = [
  { id: "whole", label: "Whole diary", usdPerLife: 163.84, description: "Every line since day one." },
  { id: "window", label: "Last 1,000 days", usdPerLife: 10.24, description: "Only the most recent lines." },
  { id: "tally", label: "Code tally", usdPerLife: 0.13, description: "Counts by field, recent days weighted more." },
];

export const EXAMPLE_PRICE_NOTE = "Cost per 32,000-day sheep life at an example $0.04 per 1M input tokens.";

const TOKENS_PER_DAY = 8;
const TALLY_TOKENS = 100;
const HALF_LIFE = 700;
const STEADY_ASK_DAY = 360;
const AFTER_SWAP_DAYS = 180;
const AFTER_CLUE_DAYS = 150;

export function viewTokens(view: MemoryView, day: number): number {
  const dayCount = day + 1;
  if (view === "tally") return TALLY_TOKENS;
  return (view === "window" ? Math.min(dayCount, WINDOW_DAYS) : dayCount) * TOKENS_PER_DAY;
}

function inView(view: MemoryView, day: number, upTo: number): boolean {
  return view !== "window" || day > upTo - WINDOW_DAYS;
}

/** A day counts fully unless the tally discounts it by age. */
function weight(view: MemoryView, day: number, upTo: number): number {
  return view === "tally" ? Math.pow(0.5, (upTo - day) / HALF_LIFE) : 1;
}

export interface FieldTally {
  visits: number;
  wolves: number;
}

export function tally(world: World, view: MemoryView, upTo: number): FieldTally[] {
  const counts = world.names.map((): FieldTally => ({ visits: 0, wolves: 0 }));
  for (let day = 0; day <= upTo; day++) {
    if (!inView(view, day, upTo)) continue;
    const entry = world.days[day];
    if (entry.kind === "fog") continue;
    const w = weight(view, day, upTo);
    counts[entry.grazed].visits += w;
    if (entry.kind === "wolf") counts[entry.grazed].wolves += w;
  }
  return counts;
}

/** What a simple counting reader would pick, or null if no evidence is left in view. */
export function readerPick(world: World, view: MemoryView, upTo: number): number | null {
  const counts = tally(world, view, upTo);
  const wantsMost = world.test === "fog";
  const estimates = counts.map((c) => (c.visits === 0 ? null : c.wolves / c.visits));
  if (estimates.every((e) => e === null || e === 0) && wantsMost) return null;
  let best: number | null = null;
  estimates.forEach((value, index) => {
    if (value === null) return;
    const current = best === null ? null : estimates[best];
    if (current === null || (wantsMost ? value > current : value < current)) best = index;
  });
  return best;
}

export type QuestionKind = "act" | "report" | "decide";

export interface GameQuestion {
  kind: QuestionKind;
  text: string;
}

export function questionsFor(world: World): GameQuestion[] {
  if (world.test === "fog") {
    return [
      { kind: "report", text: "Where has the diary seen the most wolves?" },
      { kind: "decide", text: "Which field should the sheep avoid tomorrow?" },
    ];
  }
  return [{ kind: "act", text: "Which field should the sheep graze tomorrow?" }];
}

/** The first day the question is fair: before it, the diary holds too little evidence. */
export function askDay(world: World): number {
  if (world.test === "fog") return BLOCK_END + AFTER_CLUE_DAYS;
  if (world.test === "reversal") return SWAP_DAY + AFTER_SWAP_DAYS;
  return STEADY_ASK_DAY;
}

export type Grade = "Safest" | "Risky" | "Bitten" | "Right" | "Wrong";

export function gradeOf(world: World, kind: QuestionKind, field: number): Grade {
  if (kind !== "act") return field === world.hotNow ? "Right" : "Wrong";
  if (field === world.safeNow) return "Safest";
  return field === world.hotNow ? "Bitten" : "Risky";
}

export function isGood(grade: Grade): boolean {
  return grade === "Safest" || grade === "Right";
}
