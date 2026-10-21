// Model identity colours: slots 1-4 of the validated categorical palette, in
// fixed order (identity follows the model, never its rank).
export const MODEL_COLOURS: Record<string, string> = {
  llm: "#2a78d6",
  jev: "#eb6834",
  luna: "#1baf7a",
  clef: "#eda100",
};

export const MODEL_INITIAL: Record<string, string> = { llm: "AI", jev: "J", luna: "L", clef: "C" };

export function clock(seconds: number | null | undefined): string {
  if (seconds == null || !isFinite(seconds)) return "0:00.00";
  const m = Math.floor(seconds / 60);
  const s = seconds - m * 60;
  return `${m}:${s.toFixed(2).padStart(5, "0")}`;
}

export function secs(v: number | null | undefined, digits = 2): string {
  if (v == null) return "—";
  return v >= 60 ? clock(v) : `${v.toFixed(digits)} s`;
}

export function num(v: number | null | undefined, digits = 1): string {
  return v == null ? "—" : v.toFixed(digits);
}

export function signed(v: number | null | undefined, digits = 2): string {
  if (v == null) return "—";
  return (v > 0 ? "+" : "") + v.toFixed(digits);
}

export const STATUS_LABEL: Record<string, string> = {
  solved: "SOLVED ✓",
  move_limit: "RAN OUT OF MOVES",
  time_limit: "OUT OF TIME",
  invalid_output: "INVALID OUTPUT",
  api_error: "API ERROR",
  budget_limit: "API BUDGET REACHED",
};

export function ordinal(n: number): string {
  return n === 1 ? "st" : n === 2 ? "nd" : n === 3 ? "rd" : "th";
}

export const PROVIDER_LABEL: Record<string, string> = {
  mock: "MOCK (simulated)",
  openrouter: "OPENROUTER (live API)",
};
