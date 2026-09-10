import Link from "next/link";

const PLATFORM_LINKS = [
  { href: "/platform", label: "Overview" },
  { href: "/platform/data-health", label: "Data health" },
  { href: "/platform/jobs", label: "Sync jobs" },
  { href: "/platform/settings", label: "Settings" },
];

export function PlatformNav({ active }: { active: string }) {
  return (
    <div className="segmented mb-4" role="group" aria-label="Platform sections">
      {PLATFORM_LINKS.map((link) => {
        const isActive = active === link.href;
        return (
          <Link
            key={link.href}
            href={link.href}
            aria-current={isActive ? "page" : undefined}
            className={isActive ? "segmented-item segmented-item-active" : "segmented-item"}
          >
            {link.label}
          </Link>
        );
      })}
    </div>
  );
}
