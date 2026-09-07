import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";

import { cn } from "@/lib/cn";

export function FilterField({
  label,
  className,
  children,
  layout = "inline",
}: {
  label: string;
  className?: string;
  children: ReactNode;
  layout?: "inline" | "stacked";
}) {
  if (layout === "stacked") {
    return (
      <label className={cn("filter-field-stacked", className)}>
        <span className="filter-field-label">{label}</span>
        {children}
      </label>
    );
  }

  return (
    <label className={cn("filter-field-inline", className)}>
      <span className="filter-field-label-inline">{label}</span>
      {children}
    </label>
  );
}

export function FilterSelect({
  className,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={cn("filter-control", className)} {...props} />;
}

export function FilterInput({
  className,
  ...props
}: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn("filter-control", className)} {...props} />;
}
