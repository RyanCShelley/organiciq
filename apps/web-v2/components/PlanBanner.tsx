"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";

/** Shown on a tool when the person arrived from a part of the plan: says so, and gives the way back. */
export function PlanBanner({ doing }: { doing: string }) {
  const { clientSlug } = useParams<{ clientSlug: string }>();
  const from = useSearchParams().get("from");
  if (from !== "plan") return null;
  return (
    <div className="mb-4 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-4 py-2 text-sm">
      <span>
        <span className="font-semibold">From your plan.</span> {doing}
      </span>
      <Link href={`/${clientSlug}/engine`} className="font-semibold text-[var(--brand-teal)] hover:underline">
        Back to the plan
      </Link>
    </div>
  );
}
