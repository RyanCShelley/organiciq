import type { ReactNode } from "react";

export const inputClass =
  "w-full rounded-lg border border-[var(--border)] bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[var(--brand-teal)]";

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="block text-sm">
      <span className="font-semibold">{label}</span>
      <span className="mt-1 block">{children}</span>
      {hint ? <span className="mt-1 block text-xs text-[var(--text-secondary)]">{hint}</span> : null}
    </label>
  );
}

export function Card({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6">
      {title ? <h2 className="mb-4 text-sm font-semibold">{title}</h2> : null}
      {children}
    </div>
  );
}

export function SaveBar({
  pending,
  saved,
  error,
  disabled,
  label = "Save changes",
  savedLabel = "Saved.",
  why,
}: {
  pending: boolean;
  saved: boolean;
  error: string | null;
  disabled?: boolean;
  label?: string;
  savedLabel?: string;
  /** Said beside the button while it is disabled, so a greyed-out Save is never a mystery. */
  why?: string;
}) {
  return (
    <div className="mt-6">
      <div className="flex items-center gap-3">
        <button
          type="submit"
          disabled={pending || disabled}
          className="rounded-lg bg-[var(--brand-dark)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
        >
          {label}
        </button>
        {disabled && why ? <span className="text-sm text-[var(--text-secondary)]">{why}</span> : null}
        {saved ? <span className="text-sm text-[var(--text-secondary)]">{savedLabel}</span> : null}
      </div>
      {error ? (
        <p role="alert" className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-800">
          {error}
        </p>
      ) : null}
    </div>
  );
}
