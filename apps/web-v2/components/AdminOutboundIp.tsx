"use client";

import { useState, useTransition } from "react";

import { outboundIpAction } from "@/app/(app)/admin/actions";
import { Spinner } from "@/components/ui/Spinner";

/** The address the API sends page requests from, to check against what a host (SiteGround) has been told to allow. */
export function AdminOutboundIp() {
  const [pending, start] = useTransition();
  const [result, setResult] = useState<{ address: string; user_agent: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const check = () =>
    start(async () => {
      const r = await outboundIpAction();
      if (r.ok) { setResult(r.value); setError(null); } else setError(r.error);
    });
  return (
    <section className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5">
      <h2 className="text-lg font-bold">Where page requests come from</h2>
      <p className="mt-1 text-sm text-[var(--text-secondary)]">Hosts that block our page reader (SiteGround&apos;s captcha) need to be told its address. This asks the API which address it is sending from right now.</p>
      <button type="button" onClick={check} disabled={pending} className="mt-3 rounded-lg border border-[var(--border)] bg-white px-4 py-2 text-sm font-semibold disabled:opacity-50">
        {pending ? <><Spinner />Checking…</> : "Check the address"}
      </button>
      {error ? <p role="alert" className="mt-3 text-sm text-red-800">{error}</p> : null}
      {result ? <p className="mt-3 text-sm">Sending from <span className="font-mono font-semibold">{result.address}</span> as <span className="font-mono">{result.user_agent}</span>. This should be one of the three static addresses on the API service in Railway.</p> : null}
    </section>
  );
}
