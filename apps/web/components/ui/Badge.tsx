import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

type BadgeVariant = "neutral" | "success" | "warning" | "danger" | "accent";

const variantClass: Record<BadgeVariant, string> = {
  neutral: "badge badge-neutral",
  success: "badge badge-success",
  warning: "badge badge-warning",
  danger: "badge badge-danger",
  accent: "badge badge-accent",
};

export function Badge({
  variant = "neutral",
  className,
  children,
}: {
  variant?: BadgeVariant;
  className?: string;
  children: ReactNode;
}) {
  return <span className={cn(variantClass[variant], className)}>{children}</span>;
}
