"use client";

import { useRouter } from "next/navigation";

import { Kpi, card, day, num, td, th } from "@/components/content/parts";
import type { Client } from "@/lib/api";
import { money, pct, type AdsGroup, type AdsReport, type AdsTotals } from "@/lib/ads";
import { monthLabel } from "@/lib/focus";

const change = (now: number | null | undefined, before: number | null | undefined): string | undefined => {
  if (now == null || before == null || before === 0) return undefined;
  const c = Math.round((now / before - 1) * 100);
  return `${c >= 0 ? "+" : ""}${c}% on last month`;
};

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className={card}>
      <h2 className="px-5 pt-4 text-lg font-bold">{title}</h2>
      <div className="overflow-x-auto px-2 pb-3 pt-2">{children}</div>
    </section>
  );
}

function GroupTable({ rows, first, total }: { rows: AdsGroup[]; first: string; total: AdsTotals }) {
  return (
    <table className="w-full text-sm">
      <thead>
        <tr><th className={th}>{first}</th><th className={`${th} text-right`}>Impr.</th><th className={`${th} text-right`}>Clicks</th><th className={`${th} text-right`}>Cost</th><th className={`${th} text-right`}>CTR</th><th className={`${th} text-right`}>Avg CPC</th></tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.name} className="border-t border-[var(--border)]">
            <td className="px-3 py-2">{r.name}</td>
            <td className={`${td} text-right`}>{num(r.impressions)}</td>
            <td className={`${td} text-right`}>{num(r.clicks)}</td>
            <td className={`${td} text-right`}>{money(r.cost)}</td>
            <td className={`${td} text-right`}>{r.ctr == null ? "–" : `${r.ctr.toFixed(2)}%`}</td>
            <td className={`${td} text-right`}>{money(r.avg_cpc)}</td>
          </tr>
        ))}
        <tr className="border-t-2 border-[var(--text-primary,#0f172a)] font-bold">
          <td className="px-3 py-2">Total</td>
          <td className={`${td} text-right`}>{num(total.impressions)}</td>
          <td className={`${td} text-right`}>{num(total.clicks)}</td>
          <td className={`${td} text-right`}>{money(total.cost)}</td>
          <td className={`${td} text-right`}>{total.ctr == null ? "–" : `${total.ctr.toFixed(2)}%`}</td>
          <td className={`${td} text-right`}>{money(total.avg_cpc)}</td>
        </tr>
      </tbody>
    </table>
  );
}

export function AdsAccelerator({ client, month, months, data, error }: { client: Client; month: string; months: string[]; data: AdsReport | null; error: string | null }) {
  const router = useRouter();
  const go = (m: string) => router.push(`/${client.slug}/ads?month=${m}`);
  const body = (() => {
    if (error) return <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{error}</p>;
    if (!data) return null;
    if (!data.enabled) return <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">{client.client_name} is not on Ads Accelerator. Choose it in Client settings to see ads here.</p>;
    if (!data.available) return <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">{data.reason}</p>;
    const t = data.totals;
    const p = data.previous;
    const maxClicks = Math.max(1, ...data.weekly.map((w) => w.clicks));
    return (
      <>
        {data.source === "demo" ? <p className="rounded-lg bg-blue-50 p-3 text-sm text-blue-900">These numbers are made up, to show how the page will look. Nothing here comes from Google Ads yet.</p> : null}

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <Kpi label="Impressions" value={num(t.impressions)} note={change(t.impressions, p?.impressions)} />
          <Kpi label="Clicks" value={num(t.clicks)} note={change(t.clicks, p?.clicks)} />
          <Kpi label="Click-through rate" value={t.ctr == null ? "–" : `${t.ctr.toFixed(2)}%`} />
          <Kpi label="Avg cost per click" value={money(t.avg_cpc)} />
          <Kpi label="Cost" value={money(t.cost)} note={change(t.cost, p?.cost)} />
        </div>

        <Section title="Account overview">
          <table className="w-full text-sm">
            <thead><tr><th className={th}>Metric</th><th className={`${th} text-right`}>{monthLabel(month)}</th><th className={`${th} text-right`}>Month before</th></tr></thead>
            <tbody>
              {([
                ["Impressions", num(t.impressions), p ? num(p.impressions) : "–"],
                ["Clicks", num(t.clicks), p ? num(p.clicks) : "–"],
                ["Cost", money(t.cost), p ? money(p.cost) : "–"],
                ["Click-through rate", t.ctr == null ? "–" : `${t.ctr.toFixed(2)}%`, p?.ctr == null ? "–" : `${p.ctr.toFixed(2)}%`],
                ["Average cost per click", money(t.avg_cpc), p ? money(p.avg_cpc) : "–"],
                ["Share of eligible searches shown on", pct(t.share), p ? pct(p.share) : "–"],
                ["Conversions recorded", t.conversions.toLocaleString(), p ? p.conversions.toLocaleString() : "–"],
                ["Cost per conversion", money(t.cost_per_conversion), p ? money(p.cost_per_conversion) : "–"],
              ] as const).map(([label, now, before]) => (
                <tr key={label} className="border-t border-[var(--border)]"><td className="px-3 py-2">{label}</td><td className={`${td} text-right`}>{now}</td><td className={`${td} text-right text-[var(--text-secondary)]`}>{before}</td></tr>
              ))}
            </tbody>
          </table>
        </Section>

        <Section title="Week by week">
          <table className="w-full text-sm">
            <thead><tr><th className={th}>Week</th><th className={`${th} text-right`}>Impressions</th><th className={th}>Clicks</th><th className={`${th} text-right`}>Cost</th><th className={`${th} text-right`}>Avg CPC</th></tr></thead>
            <tbody>
              {data.weekly.map((w) => (
                <tr key={w.week} className="border-t border-[var(--border)]">
                  <td className="px-3 py-2">{w.week}</td>
                  <td className={`${td} text-right`}>{num(w.impressions)}</td>
                  <td className={td}><div className="flex items-center gap-2"><span className="w-8 text-right">{num(w.clicks)}</span><span className="h-2 rounded bg-[var(--brand-teal)]" style={{ width: `${Math.max(2, (w.clicks / maxClicks) * 140)}px` }} aria-hidden /></div></td>
                  <td className={`${td} text-right`}>{money(w.cost)}</td>
                  <td className={`${td} text-right`}>{money(w.avg_cpc)}</td>
                </tr>
              ))}
              <tr className="border-t-2 border-[var(--text-primary,#0f172a)] font-bold">
                <td className="px-3 py-2">Total</td><td className={`${td} text-right`}>{num(t.impressions)}</td><td className={td}>{num(t.clicks)}</td><td className={`${td} text-right`}>{money(t.cost)}</td><td className={`${td} text-right`}>{money(t.avg_cpc)}</td>
              </tr>
            </tbody>
          </table>
        </Section>

        <Section title="Performance by ad group">
          <GroupTable rows={data.groups} first="Ad group" total={t} />
        </Section>

        <Section title="What people searched for">
          {data.terms.length === 0 ? <p className="px-3 py-2 text-sm text-[var(--text-secondary)]">Google listed no individual searches for this month.</p> : (
            <table className="w-full text-sm">
              <thead><tr><th className={th}>Search</th><th className={th}>Ad group</th><th className={`${th} text-right`}>Clicks</th><th className={`${th} text-right`}>Cost</th></tr></thead>
              <tbody>
                {data.terms.map((r) => (
                  <tr key={`${r.term}|${r.ad_group}`} className="border-t border-[var(--border)]"><td className="px-3 py-2">{r.term}</td><td className="px-3 py-2 text-[var(--text-secondary)]">{r.ad_group}</td><td className={`${td} text-right`}>{num(r.clicks)}</td><td className={`${td} text-right`}>{money(r.cost)}</td></tr>
                ))}
              </tbody>
            </table>
          )}
        </Section>

        <div className="grid gap-6 lg:grid-cols-2">
          <Section title="Markets"><GroupTable rows={data.markets} first="Market" total={t} /></Section>
          <Section title="Devices"><GroupTable rows={data.devices} first="Device" total={t} /></Section>
        </div>

        {data.period.through ? <p className="text-xs text-[var(--text-tertiary)]">Data through {day(data.period.through)}.</p> : null}
      </>
    );
  })();

  return (
    <section className="max-w-6xl space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Ads Accelerator</h1>
      </header>
      <div className="flex flex-wrap items-end gap-3 text-sm">
        <label className="text-xs font-semibold">
          Month
          <select value={month} onChange={(e) => go(e.target.value)} className="mt-1 block rounded-lg border border-[var(--border)] bg-white px-2 py-2 text-sm font-normal">
            {months.map((m) => <option key={m} value={m}>{monthLabel(m)}</option>)}
          </select>
        </label>
      </div>
      {body}
    </section>
  );
}
