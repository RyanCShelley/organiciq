import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

type CardVariant = "default" | "elevated" | "highlight";

const variantClass: Record<CardVariant, string> = {
  default: "card",
  elevated: "card-elevated",
  highlight: "highlight-card",
};

export function Card({
  variant = "default",
  className,
  children,
  title,
}: {
  variant?: CardVariant;
  className?: string;
  children: ReactNode;
  title?: string;
}) {
  return (
    <div className={cn(variantClass[variant], className)} title={title}>
      {children}
    </div>
  );
}
