import Link from "next/link";

import { GROWTH_ACTION_FILTERS } from "@/lib/decision-engine";

export function GrowthActionFilter({
  hrefBase,
  from,
  to,
  active,
}: {
  hrefBase: string;
  from: string;
  to: string;
  active: string;
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {GROWTH_ACTION_FILTERS.map((option) => {
        const params = new URLSearchParams({ from, to });
        if (option.value !== "all") params.set("lever", option.value);
        const href = `${hrefBase}?${params.toString()}`;
        const isActive = active === option.value;
        return (
          <Link
            key={option.value}
            href={href}
            className={isActive ? "btn btn-primary btn-sm" : "btn btn-ghost btn-sm"}
          >
            {option.label}
          </Link>
        );
      })}
    </div>
  );
}
