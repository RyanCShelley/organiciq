export const FOCUSES = [
  { value: "visibility", label: "Visibility", hint: "Rankings and impressions" },
  { value: "traffic", label: "Traffic", hint: "Organic sessions" },
  { value: "leads", label: "Leads", hint: "Conversions from organic" },
] as const;

export type FocusValue = (typeof FOCUSES)[number]["value"];

export type ClientFocus = {
  month: string; // YYYY-MM
  focus: FocusValue;
  bucket_id: string | null;
  bucket_name: string | null;
};

export type FocusActionResult = { ok: true } | { ok: false; error: string };

export function currentMonth(now: Date = new Date()): string {
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

export function monthLabel(month: string): string {
  const [year, m] = month.split("-").map(Number);
  return new Date(year, m - 1, 1).toLocaleDateString("en-US", { month: "long", year: "numeric" });
}
