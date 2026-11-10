import Link from "next/link";

import { Chips, StatusLine, card } from "@/components/portal/BriefParts";
import type { ClientRec } from "@/lib/portal";

/** Every published recommendation, most urgent first: the client's action plan. */
export function ActionPlan({ slug, recs }: { slug: string; recs: ClientRec[] }) {
  if (recs.length === 0) return <p className={`${card} p-5 text-sm text-[var(--text-secondary)]`}>Nothing has been published yet. When your consultant publishes a recommendation, it appears here with what to do and how we will know it worked.</p>;
  return (
    <ul className={`${card} divide-y divide-[var(--border)]`}>
      {recs.map((r) => (
        <li key={r.id}>
          <Link href={`/consulting/${slug}/action-plan/${r.id}`} className="block space-y-1 px-5 py-4 hover:bg-[var(--background)]">
            <Chips rec={r} />
            <div className="font-semibold">{r.title}</div>
            {r.action ? <div className="text-sm text-[var(--text-secondary)]">{r.action}</div> : null}
            <div className="flex flex-wrap items-center gap-3"><StatusLine rec={r} />{r.owner ? <span className="text-xs text-[var(--text-tertiary)]">Owner: {r.owner}</span> : null}{r.effort_min ? <span className="text-xs text-[var(--text-tertiary)]">About {r.effort_min} minutes</span> : null}</div>
          </Link>
        </li>
      ))}
    </ul>
  );
}
