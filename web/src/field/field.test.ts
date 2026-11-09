import { describe, expect, it } from "vitest";
import { buildFarm, centroid, contains, fieldAt, polygonArea } from "./geometry";
import { askDay, gradeOf, isGood, questionsFor, readerPick, tally, viewTokens } from "./readers";
import { createRng } from "./rng";
import { BLOCK_END, DIARY_DAYS, generateWorld, SWAP_DAY } from "./world";

describe("the game", () => {
  it("holds the question until the diary has evidence", () => {
    expect(askDay(generateWorld("steady", 1))).toBeGreaterThan(100);
    expect(askDay(generateWorld("reversal", 1))).toBeGreaterThan(SWAP_DAY);
    expect(askDay(generateWorld("fog", 1))).toBeGreaterThan(BLOCK_END);
  });

  it("grades a field by its true danger, not just right or wrong", () => {
    const world = generateWorld("steady", 2);
    const middle = [0, 1, 2, 3].find((f) => f !== world.safeNow && f !== world.hotNow)!;
    expect(gradeOf(world, "act", world.safeNow!)).toBe("Safest");
    expect(gradeOf(world, "act", world.hotNow)).toBe("Bitten");
    expect(gradeOf(world, "act", middle)).toBe("Risky");
    expect(isGood("Risky")).toBe(false);
  });

  it("asks both the report and the avoid question on the fog level", () => {
    const world = generateWorld("fog", 3);
    expect(questionsFor(world).map((q) => q.kind)).toEqual(["report", "decide"]);
    expect(gradeOf(world, "report", world.hotNow)).toBe("Right");
    expect(questionsFor(generateWorld("steady", 3)).map((q) => q.kind)).toEqual(["act"]);
  });
});

describe("field geometry", () => {
  it("partitions the map into four usable fields, the same for the same seed", () => {
    const farm = buildFarm(3);
    expect(farm.pastures).toHaveLength(4);
    const total = farm.pastures.reduce((sum, polygon) => sum + polygonArea(polygon), 0);
    expect(total).toBeCloseTo(farm.width * farm.height, 3);
    farm.pastures.forEach((polygon) => {
      expect(polygonArea(polygon)).toBeGreaterThan(farm.width * farm.height * 0.1);
      expect(contains(polygon, centroid(polygon))).toBe(true);
    });
    expect(buildFarm(3)).toEqual(farm);
  });

  it("finds which field a point falls in", () => {
    const farm = buildFarm(9);
    farm.centroids.forEach((point, index) => expect(fieldAt(farm, point)).toBe(index));
  });
});

describe("world generation", () => {
  it("is deterministic per seed and differs across seeds", () => {
    expect(generateWorld("steady", 2)).toEqual(generateWorld("steady", 2));
    expect(generateWorld("steady", 2).names).not.toEqual(generateWorld("steady", 3).names);
  });

  it("makes old evidence misleading after the swap", () => {
    const world = generateWorld("reversal", 5);
    expect(world.oldHot).not.toBeNull();
    expect(world.safeNow).toBe(world.oldHot);
    const beforeSwap = tally(world, "whole", SWAP_DAY - 1);
    expect(beforeSwap[world.oldHot!].wolves).toBeGreaterThan(beforeSwap[world.hotNow].wolves);
    expect(readerPick(world, "window", DIARY_DAYS - 1)).toBe(world.safeNow);
  });

  it("hides the old clue from a short window on the fog test", () => {
    const world = generateWorld("fog", 4);
    expect(tally(world, "whole", BLOCK_END).some((c) => c.wolves > 0)).toBe(true);
    expect(readerPick(world, "window", DIARY_DAYS - 1)).toBeNull();
    expect(readerPick(world, "whole", DIARY_DAYS - 1)).toBe(world.hotNow);
  });

  it("charges tokens in proportion to what is shown", () => {
    expect(viewTokens("whole", 999)).toBe(8000);
    expect(viewTokens("window", 2999)).toBe(8000);
    expect(viewTokens("tally", 2999)).toBe(100);
  });

  it("seeded rng repeats", () => {
    const a = createRng(5);
    const b = createRng(5);
    expect([a(), a()]).toEqual([b(), b()]);
  });
});
