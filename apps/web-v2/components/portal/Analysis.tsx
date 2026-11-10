import type { Highlights } from "@/lib/portal";

const COLUMNS = [
  { key: "going_well", title: "Going well", cls: "bg-green-50 border-green-200", head: "text-green-800" },
  { key: "to_watch", title: "To watch", cls: "bg-amber-50 border-amber-200", head: "text-amber-900" },
  { key: "gaps", title: "Biggest gaps", cls: "bg-red-50 border-red-200", head: "text-red-800" },
] as const;

/** The consultant's analysis as the client reads it: a short intro, then the three lists. An empty list is left out. */
export function Analysis({ intro, highlights }: { intro: string | null; highlights: Highlights }) {
  const shown = COLUMNS.filter((c) => highlights[c.key].length > 0);
  return (
    <div className="space-y-5">
      {intro ? <p className="whitespace-pre-line text-[0.95rem] leading-7">{intro}</p> : null}
      {shown.length ? (
        <div className={`grid gap-4 ${shown.length === 1 ? "" : shown.length === 2 ? "sm:grid-cols-2" : "lg:grid-cols-3"}`}>
          {shown.map((c) => (
            <section key={c.key} className={`rounded-2xl border p-5 ${c.cls}`}>
              <h3 className={`text-xs font-bold uppercase tracking-wide ${c.head}`}>{c.title}</h3>
              <ul className="mt-3 space-y-3 text-sm leading-6">{highlights[c.key].map((p, i) => <li key={i} className="flex gap-2"><span aria-hidden className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-current opacity-50" /><span>{p}</span></li>)}</ul>
            </section>
          ))}
        </div>
      ) : null}
    </div>
  );
}
