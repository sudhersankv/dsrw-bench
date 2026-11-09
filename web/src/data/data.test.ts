import { describe, expect, it } from "vitest";
import { generateFixtures } from "../../fixtures/generate";
import { compact, score, usd } from "./format";
import { loadCard, loadIndex } from "./load";
import { DataError, parseModelCard, parseSiteIndex } from "./parse";
import { rankModels } from "./rank";
import type { IndexEntry } from "./types";

const fixtures = generateFixtures();

async function fixtureFetch(url: string): Promise<Response> {
  const body = fixtures.get(url);
  return body === undefined ? new Response("no", { status: 404 }) : new Response(JSON.stringify(body));
}

function entry(model_id: string, flock_score: number | null): IndexEntry {
  return { model_id, display: model_id, flock_score, subscores: {}, max_tokens_tested: 16000 };
}

describe("data loading", () => {
  it("parses the fixture index and every card it lists", async () => {
    const index = await loadIndex(fixtureFetch);
    expect(index.is_demo).toBe(true);
    expect(index.models.length).toBeGreaterThan(1);
    for (const model of index.models) {
      const card = await loadCard(model.model_id, fixtureFetch);
      expect(card.is_demo).toBe(true);
      expect(card.subscores).toHaveLength(4);
      expect(card.charts.map((c) => c.id).sort()).toEqual(["ladder", "reversal", "steady"]);
    }
  });

  it("reports a missing index as a data error", async () => {
    await expect(loadIndex(async () => new Response("x", { status: 404 }))).rejects.toBeInstanceOf(DataError);
  });

  it("keeps null scores as not testable and defaults missing optionals", () => {
    const index = parseSiteIndex({
      is_demo: false,
      generated_at: "2026-11-08",
      models: [{ model_id: "m", display: "M", flock_score: null, subscores: { history: null }, max_tokens_tested: 1 }],
      shared_length_tokens: 16000,
    });
    expect(index.models[0].flock_score).toBeNull();
    expect(index.models[0].subscores.adapt).toBeNull();
    expect(index.disclaimers).toEqual([]);
  });

  it("rejects a malformed card with a pointed message", () => {
    expect(() => parseModelCard({ model_id: 3 })).toThrow(/model_id/);
  });
});

describe("ranking", () => {
  it("orders by flock score with nulls last and shares ties", () => {
    const ranked = rankModels([entry("a", 40), entry("b", null), entry("c", 70), entry("d", 40)]);
    expect(ranked.map((r) => r.entry.model_id)).toEqual(["c", "a", "d", "b"]);
    expect(ranked.map((r) => r.rank)).toEqual([1, 2, 2, null]);
  });

  it("handles one or no models", () => {
    expect(rankModels([])).toEqual([]);
    expect(rankModels([entry("solo", null)])[0].rank).toBeNull();
  });
});

describe("formatting", () => {
  it("formats scores, compact numbers and dollars", () => {
    expect(score(null)).toBe("Not testable");
    expect(score(61.6)).toBe("62");
    expect(compact(256000)).toBe("256K");
    expect(compact(1500000)).toBe("1.5M");
    expect(usd(163.84)).toBe("$163.84");
  });
});
