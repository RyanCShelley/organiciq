"use client";

import { useState } from "react";

/** "https://www.Acme.com/path" -> "acme.com"; null when nothing usable is left. */
function hostOf(domain: string | null | undefined): string | null {
  const host = (domain ?? "")
    .trim()
    .toLowerCase()
    .replace(/^[a-z]+:\/\//, "")
    .replace(/^www\./, "")
    .split(/[/?#]/)[0];
  return host.includes(".") ? host : null;
}

/**
 * The client's site icon, with the coloured initials chip as the fallback when
 * the domain has no icon or the request fails.
 */
export function ClientFavicon({
  domain,
  initials,
  background,
  className,
  textClassName,
  size,
}: {
  domain: string | null | undefined;
  initials: string;
  background: string;
  /** Box size and corner radius classes, e.g. "h-7 w-7 rounded-[7px]". */
  className: string;
  textClassName: string;
  /** Pixel size of the box, used to ask for a sharp (2x) icon. */
  size: number;
}) {
  const host = hostOf(domain);
  const [failed, setFailed] = useState(false);

  if (host && !failed) {
    return (
      <span
        aria-hidden
        className={`flex flex-none items-center justify-center overflow-hidden border border-[var(--border)] bg-white ${className}`}
      >
        {/* eslint-disable-next-line @next/next/no-img-element -- third-party icon, sized by the box */}
        <img
          src={`https://www.google.com/s2/favicons?domain=${encodeURIComponent(host)}&sz=${size * 2}`}
          alt=""
          width={size - 8}
          height={size - 8}
          loading="lazy"
          onError={() => setFailed(true)}
        />
      </span>
    );
  }

  return (
    <span
      aria-hidden
      className={`flex flex-none items-center justify-center font-bold text-white ${className} ${textClassName}`}
      style={{ background }}
    >
      {initials}
    </span>
  );
}
