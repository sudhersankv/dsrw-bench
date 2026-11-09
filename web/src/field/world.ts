import { createRng, pick, randInt, shuffled, type Rng } from "./rng";

export type TestId = "steady" | "reversal" | "fog";
export type DayKind = "wolf" | "harmless" | "fog";

export interface Day {
  grazed: number;
  kind: DayKind;
  item: string;
}

export interface World {
  test: TestId;
  seed: number;
  names: string[];
  days: Day[];
  /** Pasture index that is dangerous at the end of the diary. */
  hotNow: number;
  /** Safest pasture at the end of the diary; null on the fog test, where only the clue matters. */
  safeNow: number | null;
  /** Reversal only: the pasture that was dangerous before the swap. */
  oldHot: number | null;
  swapDay: number | null;
  blockStart: number | null;
  blockEnd: number | null;
  /** Tomorrow's true wolf risk per pasture. */
  tomorrow: number[];
}

export const DIARY_DAYS = 3000;
export const SWAP_DAY = 2000;
export const BLOCK_START = 1600;
export const BLOCK_END = 1699;
export const WINDOW_DAYS = 1000;

const HARMLESS = ["crow", "butterfly", "rabbit", "hawk", "beetle", "deer", "heron"] as const;
const ONSETS = ["D", "K", "M", "S", "V", "Th", "Br", "Gl", "Zh", "Pr", "Tr", "Sk"] as const;
const VOWELS = ["a", "e", "i", "o", "u", "ae", "io"] as const;
const CODAS = ["rro", "ll", "b", "le", "sk", "ndra", "th", "rn", "lb", "ck"] as const;

/** Seeded non-word names in the style of the benchmark's pastures. */
export function pastureNames(rng: Rng): string[] {
  const names = new Set<string>();
  while (names.size < 4) names.add(pick(rng, ONSETS) + pick(rng, VOWELS) + pick(rng, CODAS));
  return [...names];
}

/** Rates per pasture before the end of the diary and, for reversal, after the swap. */
function ratesFor(test: TestId, hot: number, safe: number): { before: number[]; after: number[] } {
  if (test === "steady") {
    const rates = [0.25, 0.25, 0.25, 0.25];
    rates[hot] = 0.36;
    rates[safe] = 0.14;
    return { before: rates, after: rates };
  }
  const before = [0.25, 0.25, 0.25, 0.25];
  before[hot] = 0.45;
  before[safe] = 0.05;
  const after = [...before];
  after[hot] = 0.05;
  after[safe] = 0.45;
  return { before, after: test === "reversal" ? after : before };
}

function makeDay(rng: Rng, grazed: number, wolfRate: number, kind: DayKind | null): Day {
  if (kind === "fog") return { grazed, kind, item: "Fog" };
  if (rng() < wolfRate) return { grazed, kind: "wolf", item: "wolf" };
  return { grazed, kind: "harmless", item: pick(rng, HARMLESS) };
}

function fogDays(rng: Rng, target: number): Day[] {
  return Array.from({ length: DIARY_DAYS }, (_, day): Day => {
    const grazed = randInt(rng, 4);
    if (day < BLOCK_START || day > BLOCK_END) return makeDay(rng, grazed, 0, "fog");
    return makeDay(rng, grazed, grazed === target ? 0.6 : 0.2, null);
  });
}

function openDays(rng: Rng, before: number[], after: number[], swapDay: number | null): Day[] {
  return Array.from({ length: DIARY_DAYS }, (_, day): Day => {
    const grazed = randInt(rng, 4);
    const rates = swapDay !== null && day >= swapDay ? after : before;
    return makeDay(rng, grazed, rates[grazed], null);
  });
}

export function generateWorld(test: TestId, seed: number): World {
  const rng = createRng(seed * 7919 + test.length * 31);
  const names = pastureNames(rng);
  const [hot, safe] = shuffled(rng, [0, 1, 2, 3]);
  const { before, after } = ratesFor(test, hot, safe);
  const reversal = test === "reversal";
  const days = test === "fog" ? fogDays(rng, hot) : openDays(rng, before, after, reversal ? SWAP_DAY : null);
  return {
    test,
    seed,
    names,
    days,
    hotNow: reversal ? safe : hot,
    safeNow: test === "fog" ? null : reversal ? hot : safe,
    oldHot: reversal ? hot : null,
    swapDay: reversal ? SWAP_DAY : null,
    blockStart: test === "fog" ? BLOCK_START : null,
    blockEnd: test === "fog" ? BLOCK_END : null,
    tomorrow: reversal ? after : before,
  };
}

export function diaryLine(world: World, day: number): string {
  const entry = world.days[day];
  const name = world.names[entry.grazed];
  return entry.kind === "fog" ? `Grazed ${name}. Fog.` : `Grazed ${name}. Saw a ${entry.item}.`;
}
