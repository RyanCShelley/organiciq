"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { updateClientAction } from "@/app/(app)/[clientSlug]/settings/client-actions";
import { createClientAction } from "@/app/(app)/new-client/actions";
import { Card, Field, SaveBar, inputClass } from "@/components/ui/form";
import type { Client } from "@/lib/api";
import {
  SEARCH_MARKETS,
  SERVICES,
  STATUSES,
  configFromService,
  lines,
  serviceFromConfig,
  type ServiceValue,
} from "@/lib/client-settings";
import type { Tier } from "@/lib/clients";

/** Runs a save and tracks pending / saved / error for the form around it. */
function useSave() {
  const [pending, startTransition] = useTransition();
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  function run(task: () => Promise<{ ok: true } | { ok: false; error: string }>) {
    setSaved(false);
    setError(null);
    startTransition(async () => {
      const result = await task();
      if (result.ok) setSaved(true);
      else setError(result.error);
    });
  }
  return { pending, saved, error, run, markDirty: () => setSaved(false) };
}

function TierSelect({
  tiers,
  value,
  onChange,
}: {
  tiers: Tier[];
  value: string;
  onChange: (id: string) => void;
}) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} required className={inputClass}>
      <option value="" disabled>
        Choose a tier
      </option>
      {tiers.map((tier) => (
        <option key={tier.id} value={tier.id}>
          {tier.tier_name}
        </option>
      ))}
    </select>
  );
}

function ServiceSelect({
  value,
  onChange,
}: {
  value: ServiceValue | "";
  onChange: (value: ServiceValue) => void;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value as ServiceValue)}
      required
      className={inputClass}
    >
      <option value="" disabled>
        Choose the services
      </option>
      {SERVICES.map((s) => (
        <option key={s.value} value={s.value}>
          {s.label}
        </option>
      ))}
    </select>
  );
}

export function GeneralForm({ client, tiers }: { client: Client; tiers: Tier[] }) {
  const save = useSave();
  const [service, setService] = useState<ServiceValue | "">(serviceFromConfig(client.service_reporting));
  const [name, setName] = useState(client.client_name);
  const [domain, setDomain] = useState(client.domain);
  const [tierId, setTierId] = useState(client.tier_id);
  const [status, setStatus] = useState<string>(client.status);
  const [start, setStart] = useState(client.start_date ?? "");
  const [sheet, setSheet] = useState(client.account_sheet_url ?? "");
  const tier = tiers.find((t) => t.id === tierId);

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        if (!service) return;
        save.run(() =>
          updateClientAction(client.id, client.slug, {
            service_reporting: configFromService(service),
            client_name: name.trim(),
            domain: domain.trim(),
            tier_id: tierId,
            status,
            start_date: start || null,
            account_sheet_url: sheet.trim() || null,
          }),
        );
      }}
      onChange={save.markDirty}
    >
      <Card>
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Agency services">
            <ServiceSelect value={service} onChange={setService} />
          </Field>
          <Field label="Company name" hint="Used for branding and AI-search prompts.">
            <input value={name} onChange={(e) => setName(e.target.value)} required className={inputClass} />
          </Field>
          <Field label="Website URL / domain">
            <input value={domain} onChange={(e) => setDomain(e.target.value)} required className={inputClass} />
          </Field>
          <Field label="OrganicIQ tier">
            <TierSelect tiers={tiers} value={tierId} onChange={setTierId} />
          </Field>
          <Field label="Status">
            <select value={status} onChange={(e) => setStatus(e.target.value)} className={inputClass}>
              {STATUSES.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Contract start date">
            <input type="date" value={start} onChange={(e) => setStart(e.target.value)} className={inputClass} />
          </Field>
        </div>
        <div className="mt-4">
          <Field label="Google Sheet account record">
            <input
              value={sheet}
              onChange={(e) => setSheet(e.target.value)}
              placeholder="https://docs.google.com/spreadsheets/d/…"
              className={inputClass}
            />
          </Field>
          {sheet.trim() ? (
            <a
              href={sheet.trim()}
              target="_blank"
              rel="noreferrer"
              className="mt-1 inline-block text-sm font-semibold text-[var(--brand-teal)] hover:underline"
            >
              Open account record ↗
            </a>
          ) : null}
        </div>
        {tier ? (
          <p className="mt-4 rounded-lg bg-[var(--bg)] p-3 text-sm text-[var(--text-secondary)]">
            <span className="font-semibold text-[var(--text-primary)]">{tier.tier_name}</span> plan:{" "}
            {tier.growth_action_allowance} growth action{tier.growth_action_allowance === 1 ? "" : "s"} a
            month, watchlist checked {tier.watchlist_cadence.replace("_", "-")}.
          </p>
        ) : null}
        <SaveBar pending={save.pending} saved={save.saved} error={save.error} disabled={!service} />
      </Card>
    </form>
  );
}

export function AdvancedForm({ client }: { client: Client }) {
  const save = useSave();
  const [folder, setFolder] = useState(client.path_prefix ?? "");
  const [market, setMarket] = useState(client.primary_market ?? "United States");
  const [timezone, setTimezone] = useState(client.timezone);
  const [maxPages, setMaxPages] = useState(client.crawl_page_limit?.toString() ?? "");
  const [aliases, setAliases] = useState((client.brand_aliases ?? []).join("\n"));

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        save.run(() =>
          updateClientAction(client.id, client.slug, {
            path_prefix: folder.trim() || null,
            primary_market: market,
            timezone: timezone.trim(),
            crawl_page_limit: maxPages.trim() ? Number(maxPages) : null,
            brand_aliases: lines(aliases),
          }),
        );
      }}
      onChange={save.markDirty}
    >
      <Card>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            label="Site folder (optional)"
            hint="Only when the brand's site is a section of a larger domain, such as /unmanned on a parent site. Blank means the whole domain."
          >
            <input value={folder} onChange={(e) => setFolder(e.target.value)} placeholder="Blank = whole domain" className={inputClass} />
          </Field>
          <Field label="Search market" hint="The SE Ranking index used for rankings. A country, not a city.">
            <select value={market} onChange={(e) => setMarket(e.target.value)} className={inputClass}>
              {SEARCH_MARKETS.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Timezone">
            <input value={timezone} onChange={(e) => setTimezone(e.target.value)} required className={inputClass} />
          </Field>
          <Field label="Max pages per crawl" hint="Blank uses 500. The ceiling is 5,000. Admin only.">
            <input
              type="number"
              min={1}
              max={5000}
              value={maxPages}
              onChange={(e) => setMaxPages(e.target.value)}
              placeholder="500 (default)"
              className={inputClass}
            />
          </Field>
        </div>
        <div className="mt-4">
          <Field
            label="Other names the brand is searched by (optional)"
            hint="One per line. The name and domain are already covered. A search that names the business is navigation, so no page change moves it and the plan won't prescribe one."
          >
            <textarea value={aliases} onChange={(e) => setAliases(e.target.value)} rows={3} className={inputClass} />
          </Field>
        </div>
        <SaveBar pending={save.pending} saved={save.saved} error={save.error} />
      </Card>
    </form>
  );
}

export function CompetitorsForm({ client }: { client: Client }) {
  const save = useSave();
  const [domains, setDomains] = useState((client.competitor_domains ?? []).join("\n"));
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        save.run(() =>
          updateClientAction(client.id, client.slug, { competitor_domains: lines(domains) }),
        );
      }}
      onChange={save.markDirty}
    >
      <Card title="Competitors">
        <Field label="Competitor domains" hint="One per line, for example competitor.com. The client's own domain is ignored.">
          <textarea value={domains} onChange={(e) => setDomains(e.target.value)} rows={8} className={inputClass} />
        </Field>
        <SaveBar pending={save.pending} saved={save.saved} error={save.error} />
      </Card>
    </form>
  );
}

export function SitemapForm({ client }: { client: Client }) {
  const save = useSave();
  const [url, setUrl] = useState(client.sitemap_url ?? "");
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        save.run(() => updateClientAction(client.id, client.slug, { sitemap_url: url.trim() || null }));
      }}
      onChange={save.markDirty}
    >
      <Card title="Website sitemap">
        <p className="mb-4 text-sm text-[var(--text-secondary)]">
          What the monthly site crawl reads. This is the whole website, separate from the blog feeds
          below. Leave it blank and the crawler looks in robots.txt and the usual places. Set it
          only if the site hides its sitemap somewhere unusual.
        </p>
        <Field label="Sitemap URL (optional)">
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="Found automatically: set only if it isn't"
            className={inputClass}
          />
        </Field>
        <SaveBar pending={save.pending} saved={save.saved} error={save.error} />
      </Card>
    </form>
  );
}

export function NewClientForm({ tiers }: { tiers: Tier[] }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [service, setService] = useState<ServiceValue | "">("");
  const [name, setName] = useState("");
  const [domain, setDomain] = useState("");
  const [tierId, setTierId] = useState("");
  const [start, setStart] = useState("");

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        if (!service) return;
        setError(null);
        startTransition(async () => {
          const result = await createClientAction({
            service_reporting: configFromService(service),
            client_name: name.trim(),
            domain: domain.trim(),
            tier_id: tierId,
            start_date: start || null,
          });
          if (result.ok) router.push(`/${result.slug}/settings`);
          else setError(result.error);
        });
      }}
    >
      <Card>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Agency services">
            <ServiceSelect value={service} onChange={setService} />
          </Field>
          <Field label="OrganicIQ tier">
            <TierSelect tiers={tiers} value={tierId} onChange={setTierId} />
          </Field>
          <Field label="Company name" hint="Used for branding and AI-search prompts.">
            <input value={name} onChange={(e) => setName(e.target.value)} required className={inputClass} />
          </Field>
          <Field label="Website URL / domain">
            <input value={domain} onChange={(e) => setDomain(e.target.value)} placeholder="example.com" required className={inputClass} />
          </Field>
          <Field label="Contract start date">
            <input type="date" value={start} onChange={(e) => setStart(e.target.value)} className={inputClass} />
          </Field>
        </div>
        <div className="mt-6 flex items-center gap-3">
          <button
            type="submit"
            disabled={pending || !service || !tierId}
            className="rounded-lg bg-[var(--brand-teal)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
          >
            Add client
          </button>
          <span className="text-sm text-[var(--text-secondary)]">
            The rest (sitemap, competitors, connections, conversions) is set up on the next screen.
          </span>
        </div>
        {error ? (
          <p role="alert" className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-800">
            {error}
          </p>
        ) : null}
      </Card>
    </form>
  );
}
