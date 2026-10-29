"use client";

import { usePathname, useRouter } from "next/navigation";

import type { Client } from "@/lib/api";

export function ClientSelect({ clients }: { clients: Client[] }) {
  const router = useRouter();
  // The layout cannot see the route's params, so the selection comes from the path.
  const first = usePathname().split("/")[1];
  const current = clients.some((c) => c.slug === first) ? first : undefined;

  return (
    <select
      aria-label="Client"
      value={current ?? ""}
      onChange={(event) => router.push(`/${event.target.value}`)}
      className="max-w-[16rem] rounded-md border border-white/20 bg-white/10 px-3 py-1.5 text-sm text-white focus:outline-none focus:ring-2 focus:ring-[var(--brand-teal)]"
    >
      {current ? null : (
        <option value="" className="text-black">
          Choose a client
        </option>
      )}
      {clients.map((client) => (
        <option key={client.id} value={client.slug} className="text-black">
          {client.client_name}
        </option>
      ))}
    </select>
  );
}
