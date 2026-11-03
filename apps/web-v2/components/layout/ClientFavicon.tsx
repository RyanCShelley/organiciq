"use client";

import { useState } from "react";

import type { Client } from "@/lib/api";

const initials = (name: string) =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase())
    .join("");

/** The client's favicon, from its domain. A letter tile stands in while it loads and when the site has none. */
export function ClientFavicon({ client, size = 28 }: { client: Pick<Client, "client_name" | "domain">; size?: number }) {
  const [failed, setFailed] = useState(false);
  const host = (client.domain || "").replace(/^https?:\/\//, "").split("/")[0];
  return (
    <span
      className="relative grid shrink-0 place-items-center overflow-hidden rounded-[7px] bg-[var(--brand-teal-soft)] text-[0.7rem] font-semibold text-[var(--brand-dark)]"
      style={{ width: size, height: size }}
      aria-hidden
    >
      {initials(client.client_name)}
      {host && !failed ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={`https://www.google.com/s2/favicons?domain=${encodeURIComponent(host)}&sz=64`}
          alt=""
          width={size}
          height={size}
          onError={() => setFailed(true)}
          className="absolute inset-0 h-full w-full bg-white object-contain p-1"
        />
      ) : null}
    </span>
  );
}
