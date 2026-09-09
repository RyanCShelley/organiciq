"use client";

import { useMemo, useState } from "react";

import { FieldLabel, Input, Select } from "@/components/ui/Input";

export type SearchableSelectOption = {
  value: string;
  label: string;
};

export function SearchableSelect({
  label,
  options,
  value,
  onChange,
  searchPlaceholder = "Search…",
  emptyLabel = "Select…",
}: {
  label: string;
  options: SearchableSelectOption[];
  value: string;
  onChange: (value: string) => void;
  searchPlaceholder?: string;
  emptyLabel?: string;
}) {
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return options;
    return options.filter(
      (opt) =>
        opt.label.toLowerCase().includes(q) || opt.value.toLowerCase().includes(q),
    );
  }, [options, query]);

  const selectedStillVisible = !value || filtered.some((opt) => opt.value === value);

  return (
    <div className="flex min-w-[320px] flex-col gap-2">
      <FieldLabel label={label}>
        <Input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={searchPlaceholder}
          className="mt-1"
          autoComplete="off"
        />
      </FieldLabel>
      <Select
        className="min-w-[320px]"
        value={selectedStillVisible ? value : ""}
        onChange={(e) => onChange(e.target.value)}
        size={Math.min(12, Math.max(4, filtered.length + 1))}
      >
        <option value="">{emptyLabel}</option>
        {filtered.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </Select>
      <p className="text-[0.6875rem] text-[var(--text-tertiary)]">
        {filtered.length === options.length
          ? `${options.length} option${options.length === 1 ? "" : "s"}`
          : `${filtered.length} of ${options.length} match`}
      </p>
    </div>
  );
}
