"use client";

import Image from "next/image";
import Link from "next/link";

import { BRAND } from "@/lib/brand";
import { cn } from "@/lib/cn";

export function LogoWordmark({
  className,
  inverse = false,
}: {
  className?: string;
  inverse?: boolean;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-start font-[family-name:var(--font-display)] text-[1.0625rem] font-bold leading-none tracking-tight",
        inverse ? "text-[var(--base-2)]" : "text-[var(--text-primary)]",
        className,
      )}
    >
      <span>
        Organic<span className={inverse ? "brand-gradient-text" : "text-[var(--brand-teal)]"}>IQ</span>
      </span>
      <sup
        className={cn(
          "ml-0.5 text-[0.5em] font-semibold leading-none",
          inverse ? "text-[var(--base)]" : "text-[var(--text-tertiary)]",
        )}
        aria-hidden
      >
        ™
      </sup>
    </span>
  );
}

export function Logo({
  href = "/dashboard",
  variant = "wordmark",
}: {
  href?: string;
  variant?: "wordmark" | "partner";
}) {
  if (variant === "partner") {
    return (
      <Link href={href} className="group inline-flex items-center gap-3">
        <Image
          src={BRAND.logoPath}
          alt={`${BRAND.companyName} logo`}
          width={148}
          height={37}
          priority
          className="h-auto w-auto max-h-9"
        />
      </Link>
    );
  }

  return (
    <Link href={href} className="group inline-flex items-center" aria-label={`${BRAND.logoWordmark} home`}>
      <LogoWordmark />
    </Link>
  );
}
