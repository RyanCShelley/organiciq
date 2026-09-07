import Link from "next/link";

const PLATFORM_LINKS = [
  { href: "/platform", label: "Overview" },
  { href: "/platform/data-health", label: "Data Health" },
  { href: "/platform/jobs", label: "Sync Jobs" },
  { href: "/platform/settings", label: "Settings" },
];

export function PlatformNav({ active }: { active: string }) {
  return (
    <div className="mb-6 flex flex-wrap gap-2">
      {PLATFORM_LINKS.map((link) => {
        const isActive = active === link.href;
        return (
          <Link
            key={link.href}
            href={link.href}
            className={isActive ? "btn btn-primary btn-sm" : "btn btn-ghost btn-sm"}
          >
            {link.label}
          </Link>
        );
      })}
    </div>
  );
}
