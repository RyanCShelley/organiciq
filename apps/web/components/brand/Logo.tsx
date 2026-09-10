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
        "inline-flex items-start font-[family-name:var(--font-display)] text-[1.0625rem] font-black leading-none tracking-[-0.02em]",
        inverse ? "text-[var(--sidebar-fg)]" : "text-[var(--text-primary)]",
        className,
      )}
    >
      <span>
        Organic<span className="brand-gradient-text">IQ</span>
      </span>
      <sup
        className={cn(
          "ml-0.5 text-[0.5em] font-semibold leading-none",
          inverse ? "text-[var(--sidebar-fg-muted)]" : "text-[var(--text-tertiary)]",
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
