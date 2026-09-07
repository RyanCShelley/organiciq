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
        "page-gutter-x mx-auto w-full max-w-7xl py-5",
        className,
      )}
    >
      {children}
    </div>
  );
}
