import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

export function ContentContainer({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <div
      className={cn(
        "page-gutter-x mx-auto w-full max-w-[var(--content-max)] py-6",
        className,
      )}
    >
      {children}
    </div>
  );
}
