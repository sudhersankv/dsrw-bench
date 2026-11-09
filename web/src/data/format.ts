export const NOT_TESTABLE = "Not testable";

export function score(value: number | null): string {
  return value === null ? NOT_TESTABLE : value.toFixed(0);
}

function trim(value: number): string {
  return value.toFixed(Math.abs(value) < 10 ? 2 : 1).replace(/\.?0+$/, "");
}

/** 16000 → "16K", 1500000 → "1.5M". */
export function compact(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1e6) return `${trim(value / 1e6)}M`;
  if (abs >= 1000) return `${trim(value / 1000)}K`;
  return trim(value);
}

export function usd(value: number): string {
  if (value === 0) return "$0";
  return value < 0.01 ? `$${value.toFixed(4)}` : `$${value.toFixed(2)}`;
}

export function signed(value: number | null, digits = 2): string {
  if (value === null) return "n/a";
  return `${value > 0 ? "+" : ""}${value.toFixed(digits)}`;
}

export function tokens(value: number): string {
  return `${compact(value)} tokens`;
}

export function longDate(iso: string): string {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });
}
