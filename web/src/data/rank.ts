import type { IndexEntry } from "./types";

export interface RankedEntry {
  entry: IndexEntry;
  /** 1-based, shared on ties; null for models without a flock score. */
  rank: number | null;
}

function compareEntries(a: IndexEntry, b: IndexEntry): number {
  if (a.flock_score === null && b.flock_score === null) return a.display.localeCompare(b.display);
  if (a.flock_score === null) return 1;
  if (b.flock_score === null) return -1;
  return b.flock_score - a.flock_score || a.display.localeCompare(b.display);
}

export function rankModels(entries: IndexEntry[]): RankedEntry[] {
  const sorted = [...entries].sort(compareEntries);
  let lastScore: number | null = null;
  let lastRank = 0;
  return sorted.map((entry, index) => {
    if (entry.flock_score === null) return { entry, rank: null };
    const rank = entry.flock_score === lastScore ? lastRank : index + 1;
    lastScore = entry.flock_score;
    lastRank = rank;
    return { entry, rank };
  });
}
