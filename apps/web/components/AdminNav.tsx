import Link from "next/link";

const ADMIN_LINKS = [
  { href: "/admin/clients", label: "Clients" },
  { href: "/admin/integrations", label: "Integrations" },
  { href: "/admin/data-health", label: "Data Health" },
  { href: "/admin/jobs", label: "Sync Jobs" },
  { href: "/admin/configuration", label: "Configuration" },
];

export function AdminNav({ active }: { active: string }) {
  return (
    <div className="mb-6 flex flex-wrap gap-2">
      {ADMIN_LINKS.map((link) => {
        const isActive = active === link.href;
        return (
          <Link
            key={link.href}
            href={link.href}
            className={`rounded-full px-3 py-1.5 text-sm ${
              isActive ? "nav-link-active" : "btn btn-ghost btn-sm"
            }`}
          >
            {link.label}
          </Link>
        );
      })}
    </div>
  );
}
