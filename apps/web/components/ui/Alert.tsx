import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

type AlertVariant = "info" | "warning" | "danger" | "success";

const variantClass: Record<AlertVariant, string> = {
  info: "alert alert-info",
  warning: "alert alert-warning",
  danger: "alert alert-danger",
  success: "alert alert-success",
};

export function Alert({
  variant = "info",
  className,
  children,
}: {
  variant?: AlertVariant;
  className?: string;
  children: ReactNode;
}) {
  return <div className={cn(variantClass[variant], className)}>{children}</div>;
}
