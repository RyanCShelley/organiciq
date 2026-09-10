import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

export function SectionHeader({
  title,
  description,
  actions,
  className,
  accent = false,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
  className?: string;
  /** Teal→lime vertical rule beside the title (dashboard sections). */
  accent?: boolean;
}) {
  return (
    <div className={cn("mb-3 flex flex-wrap items-end justify-between gap-4", className)}>
      <div className="min-w-0">
        <div className="flex items-center gap-2.5">
          {accent ? <span className="section-accent" aria-hidden /> : null}
          <h2 className="section-title">{title}</h2>
        </div>
        {description ? <p className="section-description">{description}</p> : null}
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </div>
  );
}

export function SubsectionTitle({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <h3 className={cn("subsection-title flex items-center gap-2", className)}>
      <span className="inline-block h-[3px] w-[22px] rounded-sm bg-[var(--brand-teal)]" aria-hidden />
      {children}
    </h3>
  );
}
