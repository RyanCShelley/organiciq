"use client";

import { CalendarDays } from "lucide-react";

import { FilterField, FilterInput, FilterSelect } from "@/components/ui/FilterField";
import {
  RANGE_OPTIONS,
  formatDateLabel,
  isoDaysAgo,
  useWorkspaceParams,
  type RangeKey,
} from "@/lib/workspace-params";

export function DateRangeControls({
  clientId,
  from,
  to,
}: {
  clientId: string;
  from: string;
  to: string;
}) {
  const { pending, activeFrom, activeTo, rangeKey, apply } = useWorkspaceParams({
    clientId,
    from,
    to,
    persistDefault: true,
  });
  const isCustom = rangeKey === "custom";

  function onRangeChange(key: RangeKey) {
    if (key === "custom") {
      apply({ range: "custom" });
      return;
    }
    const option = RANGE_OPTIONS.find((row) => row.key === key);
    if (!option?.days) return;
    apply({ ...isoDaysAgo(option.days), range: key });
  }

  return (
    <div className="filter-bar">
      <FilterField label="Date range">
        <div className="filter-control-wrap">
          <CalendarDays className="filter-control-icon" aria-hidden />
          <FilterSelect
            className="filter-control-with-icon w-[8.75rem]"
            value={rangeKey}
            disabled={pending}
            onChange={(event) => onRangeChange(event.target.value as RangeKey)}
          >
            {RANGE_OPTIONS.map((option) => (
              <option key={option.key} value={option.key}>
                {option.label}
              </option>
            ))}
          </FilterSelect>
        </div>
      </FilterField>

      {isCustom ? (
        <>
          <FilterField label="From">
            <FilterInput
              type="date"
              className="w-[9rem]"
              value={activeFrom}
              onChange={(event) => apply({ from: event.target.value, range: "custom" })}
            />
          </FilterField>
          <FilterField label="To">
            <FilterInput
              type="date"
              className="w-[9rem]"
              value={activeTo}
              onChange={(event) => apply({ to: event.target.value, range: "custom" })}
            />
          </FilterField>
        </>
      ) : (
        <>
          <span className="toolbar-divider" aria-hidden />
          <div className="filter-meta">
            <CalendarDays className="h-3.5 w-3.5 shrink-0 text-[var(--text-tertiary)]" aria-hidden />
            <span>
              {formatDateLabel(activeFrom)} – {formatDateLabel(activeTo)}
            </span>
          </div>
        </>
      )}
    </div>
  );
}
