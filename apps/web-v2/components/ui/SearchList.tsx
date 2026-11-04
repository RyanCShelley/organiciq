"use client";

import { useMemo, useState } from "react";

import { inputClass } from "@/components/ui/form";
import type { Option } from "@/lib/connections";

/** A list you narrow by typing. Every word typed has to appear somewhere in an option's label. */
export function SearchList({
  options,
  value,
  onChange,
  label,
}: {
  options: Option[];
  value: string;
  onChange: (value: string) => void;
  label: string;
}) {
  const [query, setQuery] = useState("");

  const shown = useMemo(() => {
    const words = query.toLowerCase().split(/\s+/).filter(Boolean);
    if (words.length === 0) return options;
    return options.filter((option) => {
      const text = option.label.toLowerCase();
      return words.every((word) => text.includes(word));
    });
  }, [options, query]);

  return (
    <div className="w-full">
      <input
        type="search"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        onKeyDown={(event) => {
          // Enter must not submit the page; it picks the first match.
          if (event.key === "Enter") {
            event.preventDefault();
            if (shown[0]) onChange(shown[0].value);
          }
        }}
        placeholder={`Search ${options.length} ${label.toLowerCase()}…`}
        aria-label={`Search ${label}`}
        className={inputClass}
        autoFocus
      />
      <ul
        role="listbox"
        aria-label={label}
        className="mt-2 max-h-64 overflow-y-auto rounded-lg border border-[var(--border)] bg-white text-sm"
      >
        {shown.length === 0 ? (
          <li className="px-3 py-2 text-[var(--text-tertiary)]">No match for &ldquo;{query}&rdquo;.</li>
        ) : (
          shown.map((option) => {
            const selected = option.value === value;
            return (
              <li key={option.value} role="option" aria-selected={selected}>
                <button
                  type="button"
                  onClick={() => onChange(option.value)}
                  className={`block w-full px-3 py-2 text-left hover:bg-[var(--bg)] ${
                    selected ? "bg-[var(--brand-teal)]/10 font-semibold" : ""
                  }`}
                >
                  {option.label}
                </button>
              </li>
            );
          })
        )}
      </ul>
      <p className="mt-1 text-xs text-[var(--text-tertiary)]">
        {shown.length === options.length ? `${options.length} available` : `${shown.length} of ${options.length}`}
      </p>
    </div>
  );
}
