import { existsSync, readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { parseModelCard, parseSiteIndex } from "./parse";

const dataDir = resolve(__dirname, "../../public/data");

function readJson(...parts: string[]): unknown {
  return JSON.parse(readFileSync(resolve(dataDir, ...parts), "utf-8"));
}

// Runs only after `swb demo` or `swb analyze` has written real pipeline output.
describe.skipIf(!existsSync(resolve(dataDir, "index.json")))("swb analyze output", () => {
  it("parses the index and every card it lists", () => {
    const index = parseSiteIndex(readJson("index.json"));
    expect(index.models.length).toBeGreaterThan(0);
    for (const model of index.models) {
      const card = parseModelCard(readJson("models", `${model.model_id}.json`));
      expect(card.model_id).toBe(model.model_id);
      expect(card.is_demo).toBe(index.is_demo);
      expect(card.subscores).toHaveLength(4);
      expect(card.charts.map((c) => c.id).sort()).toEqual(["ladder", "reversal", "steady"]);
    }
    expect(readdirSync(resolve(dataDir, "models"))).toHaveLength(index.models.length);
  });
});
