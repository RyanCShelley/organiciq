import { Change } from "@/components/review/Sections";
import type { Bi } from "@/lib/bi";
import type { PromptRow } from "@/lib/portal";
import type { Review, VisibilityTerm } from "@/lib/review";

const th = "px-2 py-2 text-left text-xs font-semibold uppercase tracking-wide text-[var(--text-tertiary)]";
const td = "px-2 py-2 tabular-nums";
const box = "rounded-2xl border border-[var(--border)] bg-white p-5";
const n = (v: number | null | undefined, d = 0) => (v == null ? "–" : v.toLocaleString(undefined, { maximumFractionDigits: d }));
const PLATFORMS: Record<string, string> = { openai: "ChatGPT", chatgpt: "ChatGPT", anthropic: "Claude", claude: "Claude", gemini: "Gemini", perplexity: "Perplexity" };
const CODE: Record<string, { label: string; cls: string }> = {
  "C+M": { label: "Named and linked", cls: "bg-green-50 text-green-800" },
  C: { label: "Linked", cls: "bg-green-50 text-green-800" },
  M: { label: "Named", cls: "bg-[var(--bg-accent,#e6f1fb)] text-[var(--brand-teal)]" },
};

function Block({ title, source, note, children }: { title: string; source: string; note?: string; children: React.ReactNode }) {
  return (
    <div className={box}>
      <div className="flex items-baseline justify-between gap-3"><h3 className="text-sm font-semibold">{title}</h3><span className="text-[0.7rem] font-medium uppercase tracking-wide text-[var(--text-tertiary)]">{source}</span></div>
      {note ? <p className="mt-1 text-xs text-[var(--text-secondary)]">{note}</p> : null}
      <div className="mt-3 overflow-x-auto">{children}</div>
    </div>
  );
}

const terms = (review: Review): VisibilityTerm[] => (review.visibility?.buckets ?? []).flatMap((b) => b.terms);

/** Where the site shows up, engine by engine: Google, Bing, the rank tracker, and the AI platforms prompt by prompt. */
export function VisibilityDetail({ review, keywords, prompts, runs, runDates }: { review: Review; keywords: Bi["keywords"] | null; prompts: PromptRow[]; runs: number; runDates: string[] }) {
  const all = terms(review);
  const search = review.search;
  const bing = review.visibility?.bing;
  const bingTerms = all.filter((t) => (t.bing.impressions.current ?? 0) > 0);
  const tracked = keywords?.keywords ?? [];
  const platforms = [...new Set(prompts.flatMap((p) => Object.keys(p.by_platform)))].sort();
  return (
    <div className="mt-4 space-y-4">
      <Block title="Google" source="Search Console" note="Your whole site, this month against last, then your tracked terms.">
        <div className="mb-3 grid gap-3 sm:grid-cols-4">
          {[["Impressions", search.impressions, 0], ["Clicks", search.clicks, 0], ["Average position", search.average_position, 1]].map(([label, p, d]) => {
            const pair = p as { current: number | null; previous: number | null; change_pct: number | null };
            return (
              <div key={label as string}><div className="text-xs text-[var(--text-secondary)]">{label as string}</div><div className="text-2xl font-bold tabular-nums">{n(pair.current, d as number)}</div>{label === "Average position" ? <div className="text-xs text-[var(--text-tertiary)]">lower is better{pair.previous != null ? `, was ${n(pair.previous, 1)}` : ""}</div> : <Change pct={pair.change_pct} />}</div>
            );
          })}
        </div>
        {all.length ? (
          <table className="w-full text-sm">
            <thead><tr><th className={th}>Term</th><th className={th}>Where it shows</th><th className={`${th} text-right`}>Impressions</th><th className={`${th} text-right`}>Clicks</th><th className={`${th} text-right`}>Position</th></tr></thead>
            <tbody>
              {all.map((t) => (
                <tr key={t.keyword} className="border-t border-[var(--border)]">
                  <td className="px-2 py-2 font-medium">{t.keyword}</td><td className="px-2 py-2 text-[var(--text-secondary)]">{t.status}</td>
                  <td className={`${td} text-right`}>{n(t.google.impressions.current)}</td><td className={`${td} text-right`}>{n(t.google.clicks.current)}</td><td className={`${td} text-right`}>{n(t.google.position.current, 1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <p className="text-sm text-[var(--text-secondary)]">No tracked terms are set up for this site yet.</p>}
      </Block>

      <Block title="Bing" source="Bing Webmaster" note={bing?.note ?? "Bing reports weekly. A week counts toward the month it starts in."}>
        {bing?.has_data && bingTerms.length ? (
          <table className="w-full text-sm">
            <thead><tr><th className={th}>Term</th><th className={`${th} text-right`}>Impressions</th><th className={`${th} text-right`}>Clicks</th><th className={`${th} text-right`}>Position</th></tr></thead>
            <tbody>{bingTerms.map((t) => <tr key={t.keyword} className="border-t border-[var(--border)]"><td className="px-2 py-2 font-medium">{t.keyword}</td><td className={`${td} text-right`}>{n(t.bing.impressions.current)}</td><td className={`${td} text-right`}>{n(t.bing.clicks.current)}</td><td className={`${td} text-right`}>{n(t.bing.position.current, 1)}</td></tr>)}</tbody>
          </table>
        ) : <p className="text-sm text-[var(--text-secondary)]">{bing?.has_data ? "None of your tracked terms had a Bing impression this month." : "Bing Webmaster is not connected for this site, so there are no Bing numbers."}</p>}
      </Block>

      <Block title="Rank tracker" source="SE Ranking" note="The keywords we check daily at a fixed location. A keyword not found in the top 100 counts as outside.">
        {tracked.length ? (
          <table className="w-full text-sm">
            <thead><tr><th className={th}>Keyword</th><th className={`${th} text-right`}>Position</th><th className={`${th} text-right`}>Start of month</th><th className={`${th} text-right`}>Change</th><th className={`${th} text-right`}>Searches a month</th></tr></thead>
            <tbody>
              {tracked.map((k) => (
                <tr key={k.keyword} className="border-t border-[var(--border)]">
                  <td className="px-2 py-2 font-medium">{k.keyword}</td><td className={`${td} text-right`}>{k.end ?? "outside"}</td><td className={`${td} text-right`}>{k.start ?? "outside"}</td>
                  <td className={`${td} text-right`}>{k.change == null ? <span className="text-[var(--text-tertiary)]">{k.state === "new" ? "new" : k.state === "lost" ? "lost" : "–"}</span> : <span className={`font-semibold ${k.change > 0 ? "text-green-700" : k.change < 0 ? "text-red-700" : "text-[var(--text-secondary)]"}`}>{k.change > 0 ? "▲" : k.change < 0 ? "▼" : ""} {Math.abs(k.change)}</span>}</td>
                  <td className={`${td} text-right`}>{n(k.volume)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <p className="text-sm text-[var(--text-secondary)]">The rank tracker has no check inside this month.</p>}
      </Block>

      <Block title="AI answers, prompt by prompt" source="AI platform checks" note={prompts.length ? `We ask each AI platform the questions your customers ask and see whether it names or links to you. A sample from ${runs} check${runs === 1 ? "" : "s"}${runDates.length ? ` (latest ${runDates[runDates.length - 1]})` : ""}, not every AI answer. Questions that already name your brand are left out.` : undefined}>
        {prompts.length ? (
          <table className="w-full text-sm">
            <thead><tr><th className={th}>Prompt</th>{platforms.map((p) => <th key={p} className={th}>{PLATFORMS[p] ?? p}</th>)}<th className={`${th} text-right`}>Score</th><th className={th}>Others named</th></tr></thead>
            <tbody>
              {prompts.map((p) => (
                <tr key={p.query} className="border-t border-[var(--border)] align-top">
                  <td className="max-w-xs px-2 py-2 font-medium">{p.query}{p.topic_cluster ? <div className="text-xs font-normal text-[var(--text-tertiary)]">{p.topic_cluster}</div> : null}</td>
                  {platforms.map((pl) => {
                    const c = CODE[p.by_platform[pl] ?? ""];
                    return <td key={pl} className="px-2 py-2">{c ? <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${c.cls}`}>{c.label}</span> : <span className="text-xs text-[var(--text-tertiary)]">Not shown</span>}</td>;
                  })}
                  <td className={`${td} text-right`}>{p.score}/{p.max_score}{p.change != null && p.change !== 0 ? <span className={`ml-1 text-xs font-semibold ${p.change > 0 ? "text-green-700" : "text-red-700"}`}>{p.change > 0 ? "+" : ""}{p.change}</span> : null}</td>
                  <td className="px-2 py-2 text-xs text-[var(--text-secondary)]">{p.top_competitors.map((c) => c.name).join(", ") || "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <p className="text-sm text-[var(--text-secondary)]">No AI visibility check has finished for this site yet, so there are no prompt results.</p>}
      </Block>
    </div>
  );
}
