"use client";

import { ExternalLink } from "lucide-react";
import { useState, useTransition } from "react";

import { updateClientSettingsAction } from "@/app/(app)/actions";
import { LeadGoalSchedule } from "@/components/LeadGoalSchedule";
import { BaselineSnapshotPanel } from "@/components/BaselineSnapshotPanel";
import { TeamworkTasklistField } from "@/components/TeamworkTasklistField";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { FieldLabel, Input, Select } from "@/components/ui/Input";
import type { Client, Tier } from "@/lib/api";
import { isEnterpriseTier, resolvePlanAllowances } from "@/lib/plan-allowances";

const STATUS_OPTIONS = [
  { value: "active", label: "Active" },
  { value: "onboarding", label: "Onboarding" },
  { value: "paused", label: "Paused" },
  { value: "archived", label: "Archived" },
];

/**
 * Mirrors the API's own constants (ingestion/seranking/client.py). The server
 * clamps independently — these only shape the form.
 */
const AI_SEARCH_DEFAULT_PROMPTS = 5;
const AI_SEARCH_MAX_PROMPTS = 50;
const AI_SEARCH_CREDITS_PER_PROMPT = 200;

/** Mirrors ingestion/crawler/fetch.py. The server clamps independently. */
const CRAWL_DEFAULT_PAGES = 500;
const CRAWL_MAX_PAGES = 5000;

const CADENCE_OPTIONS = [
  { value: "monthly", label: "Monthly" },
  { value: "bi_weekly", label: "Bi-weekly" },
  { value: "weekly", label: "Weekly" },
];

function formatCadence(cadence?: string | null): string {
  switch (cadence) {
    case "weekly":
      return "weekly";
    case "bi_weekly":
      return "bi-weekly";
    case "monthly":
    case undefined:
    case null:
    case "":
      return "monthly";
    default:
      return cadence.replaceAll("_", "-");
  }
}

/**
 * The markets SE Ranking has an index for.
 *
 * Spelled as `resolve_source` matches them, so a saved value resolves to a
 * real index rather than silently falling back.
 */
const SEARCH_MARKETS = [
  { value: "United States" },
  { value: "United Kingdom" },
  { value: "Canada" },
  { value: "Australia" },
] as const;

export function ClientSettingsForm({
  client,
  tiers,
  hasLeadConversions = false,
  canEditPlan = true,
}: {
  client: Client;
  tiers: Tier[];
  hasLeadConversions?: boolean;
  /** Admins only. The API refuses plan and ceiling changes from anyone else. */
  canEditPlan?: boolean;
}) {
  const [pending, startTransition] = useTransition();
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tierId, setTierId] = useState(client.tier_id);
  const selectedTier = tiers.find((tier) => tier.id === tierId) ?? tiers[0];
  const enterprise = isEnterpriseTier(selectedTier);
  const allowances = resolvePlanAllowances(client, selectedTier);

  return (
    <form
      className="space-y-5"
      action={(formData) => {
        setMessage(null);
        setError(null);
        startTransition(async () => {
          const result = await updateClientSettingsAction(formData);
          if (result.ok) setMessage("Client settings saved.");
          else setError(result.error);
        });
      }}
    >
      <input type="hidden" name="clientId" value={client.id} />
      <input type="hidden" name="is_enterprise" value={enterprise ? "1" : "0"} />
      {canEditPlan ? null : <input type="hidden" name="plan_locked" value="1" />}

      {error ? <Alert variant="danger">{error}</Alert> : null}
      {message ? <Alert variant="success">{message}</Alert> : null}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <FieldLabel label="Company name">
          <Input name="client_name" defaultValue={client.client_name} required />
        </FieldLabel>
        <FieldLabel label="Website URL / domain">
          <Input name="domain" defaultValue={client.domain} required />
        </FieldLabel>
        {/* Beside the domain, because together they say what this client's site
            *is*. Filed under the crawl settings it read as a crawl option, and
            was the last place anyone looked for it. */}
        <FieldLabel label="Site folder (optional)">
          <Input
            name="path_prefix"
            defaultValue={client.path_prefix ?? ""}
            placeholder="Blank = whole domain"
          />
        </FieldLabel>
        <p className="text-xs text-[var(--text-secondary)] sm:col-span-2">
          Set <strong>Site folder</strong> only when this brand&rsquo;s site is a section
          of a larger domain — <code>robinsonheli.com</code> with{" "}
          <code>/unmanned</code>. Analytics, Search Console and the crawler are all held
          to that folder, so a sibling brand&rsquo;s pages are never counted here. The
          folder never belongs in the domain field.
        </p>
        {canEditPlan ? (
        <FieldLabel label="OrganicIQ tier">
          <Select
            name="tier_id"
            value={tierId}
            required
            onChange={(event) => setTierId(event.target.value)}
          >
            {tiers.map((tier) => (
              <option key={tier.id} value={tier.id}>
                {tier.tier_name}
              </option>
            ))}
          </Select>
        </FieldLabel>
        ) : (
          <FieldLabel label="OrganicIQ tier">
            <Input value={client.plan_label ?? "—"} disabled readOnly />
          </FieldLabel>
        )}
        <FieldLabel label="Status">
          <Select name="status" defaultValue={client.status}>
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        </FieldLabel>
        <FieldLabel label="Contract start date">
          <Input name="start_date" type="date" defaultValue={client.start_date ?? ""} />
        </FieldLabel>
        <FieldLabel label="Lead goal fallback">
          <Input
            name="monthly_lead_goal"
            type="number"
            min={0}
            defaultValue={client.monthly_lead_goal ?? ""}
            placeholder="From growth calculator"
          />
        </FieldLabel>
        {/* It picks which SE Ranking regional index the domain pull reads,
            and matches on a country. As free text it invited "Central NY",
            which matches nothing and falls back to the United States while
            looking filled in. */}
        <div className="flex flex-col gap-1">
          <FieldLabel label="Search market">
            <Select
              name="primary_market"
              defaultValue={
                SEARCH_MARKETS.some((m) => m.value === client.primary_market)
                  ? (client.primary_market as string)
                  : client.primary_market
                    ? "__other"
                    : ""
              }
            >
              <option value="">Not set — United States</option>
              {SEARCH_MARKETS.map((market) => (
                <option key={market.value} value={market.value}>
                  {market.value}
                </option>
              ))}
              {/* Whatever is already stored stays selectable, so opening
                  this page and saving cannot quietly rewrite it. */}
              {client.primary_market &&
              !SEARCH_MARKETS.some((m) => m.value === client.primary_market) ? (
                <option value="__other">
                  {client.primary_market} — not a search market, treated as
                  United States
                </option>
              ) : null}
            </Select>
          </FieldLabel>
          <p className="text-xs text-[var(--text-tertiary)]">
            Which SE Ranking index the domain pull reads. It is a country, not
            a city — the four above are the ones SE Ranking has.
          </p>
        </div>
        <FieldLabel label="Timezone">
          <Input name="timezone" defaultValue={client.timezone} />
        </FieldLabel>
      </div>

      <div className="rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface-muted)] p-4 space-y-3">
        <div>
          <p className="font-[family-name:var(--font-display)] text-[15px] font-extrabold text-[var(--text-primary)]">
            Lead goal by checkpoint
          </p>
        </div>
        <LeadGoalSchedule client={client} />
      </div>

      <div className="flex flex-col gap-1">
        <FieldLabel label="Google Sheet account record">
          <Input
            name="account_sheet_url"
            type="url"
            defaultValue={client.account_sheet_url ?? ""}
            placeholder="https://docs.google.com/spreadsheets/..."
          />
        </FieldLabel>
        {client.account_sheet_url ? (
          <a
            href={client.account_sheet_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex w-fit items-center gap-1.5 text-xs font-semibold text-[var(--brand-teal-hover)] hover:underline"
          >
            <ExternalLink className="h-3 w-3" aria-hidden />
            Open account record
          </a>
        ) : null}
      </div>

      {/* A list rather than a box to type an id into: an id read off a URL
          is how a task ends up in the wrong client's list, and nothing
          downstream would catch it. */}
      <TeamworkTasklistField value={client.teamwork_tasklist_id ?? null} />

      <div className="rounded-[var(--radius-lg,14px)] border border-[var(--border)] bg-[var(--surface)] p-5 space-y-4">
        <div>
          <p className="font-[family-name:var(--font-display)] text-[15px] font-extrabold text-[var(--text-primary)]">
            Dashboard baseline snapshot
          </p>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            Freeze starting monthly sessions, leads, and lead rate (from the growth calculator or
            kickoff numbers). Dashboard compares the current window against this snapshot.
          </p>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <FieldLabel label="Baseline as of">
            <Input
              name="baseline_as_of"
              type="date"
              defaultValue={client.baseline_as_of ?? ""}
            />
          </FieldLabel>
          <FieldLabel label="Monthly sessions">
            <Input
              name="baseline_monthly_sessions"
              type="number"
              min={0}
              defaultValue={client.baseline_monthly_sessions ?? ""}
              placeholder="From calculator"
            />
          </FieldLabel>
          <FieldLabel label="Monthly leads">
            <Input
              name="baseline_monthly_leads"
              type="number"
              min={0}
              defaultValue={client.baseline_monthly_leads ?? ""}
            />
          </FieldLabel>
          <FieldLabel label="Lead rate %">
            <Input
              name="baseline_lead_rate_pct"
              type="number"
              min={0}
              step="0.01"
              defaultValue={client.baseline_lead_rate_pct ?? ""}
              placeholder="Auto from leads ÷ sessions"
            />
          </FieldLabel>
          <FieldLabel label="Source">
            <Select name="baseline_source" defaultValue={client.baseline_source ?? "manual"}>
              <option value="manual">Manual</option>
              <option value="ga4_calculator">GA4 + calculator</option>
              <option value="calculator">Growth calculator</option>
              <option value="ga4">GA4 snapshot</option>
              <option value="kickoff">Kickoff / audit</option>
            </Select>
          </FieldLabel>
          <FieldLabel label="Notes" className="sm:col-span-2 lg:col-span-1">
            <Input
              name="baseline_notes"
              defaultValue={client.baseline_notes ?? ""}
              placeholder="e.g. Pre-engagement July 2025"
            />
          </FieldLabel>
        </div>
        <BaselineSnapshotPanel
          clientId={client.id}
          clientSlug={client.slug}
          hasLeadConversions={hasLeadConversions}
          savedAsOf={client.baseline_as_of ?? null}
          savedProjection={client.baseline_projection_json ?? null}
        />
      </div>

      {canEditPlan ? null : (
        <p className="text-sm text-[var(--text-secondary)]">
          The plan and its limits (allowances, AI prompt cap, crawl size) are changed by an
          admin.
        </p>
      )}

      {/* Cost ceiling, not a plan allowance — this one spends SE Ranking credits
          per prompt returned, so it lives outside the tier blocks. */}
      <div className="rounded-[var(--radius-lg,14px)] border border-[var(--border)] bg-[var(--surface)] p-5 space-y-4">
        <div>
          <p className="font-[family-name:var(--font-display)] text-[15px] font-extrabold text-[var(--text-primary)]">
            AI prompt discovery
          </p>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            Caps how many prompts one &ldquo;Find untracked prompts&rdquo; lookup on Watch List
            can buy for this client. Billed at {AI_SEARCH_CREDITS_PER_PROMPT} credits per prompt
            returned, so raise it only for accounts that justify the spend.
          </p>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <FieldLabel label="Max prompts per lookup">
            <Input
              name="ai_search_prompt_limit"
              disabled={!canEditPlan}
              type="number"
              min={1}
              max={AI_SEARCH_MAX_PROMPTS}
              defaultValue={client.ai_search_prompt_limit ?? ""}
              placeholder={`${AI_SEARCH_DEFAULT_PROMPTS} (default)`}
            />
          </FieldLabel>
          <p className="self-center text-xs text-[var(--text-secondary)]">
            Blank uses the default of {AI_SEARCH_DEFAULT_PROMPTS} prompts (
            {(AI_SEARCH_DEFAULT_PROMPTS * AI_SEARCH_CREDITS_PER_PROMPT).toLocaleString()}{" "}
            credits). The ceiling is {AI_SEARCH_MAX_PROMPTS}.
          </p>
        </div>
      </div>

      {/* Crawl budget, not a plan allowance: it bounds time spent on someone
          else's server, so it sits with the other operational ceilings. */}
      <div className="rounded-[var(--radius-lg,14px)] border border-[var(--border)] bg-[var(--surface)] p-5 space-y-4">
        <div>
          <p className="font-[family-name:var(--font-display)] text-[15px] font-extrabold text-[var(--text-primary)]">
            Site crawl
          </p>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            OrganicIQ crawls this site once a month for technical signals and
            structured data. Sites are staggered across the month, so this one has its
            own day.
          </p>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <FieldLabel label="Max pages per crawl">
            <Input
              name="crawl_page_limit"
              disabled={!canEditPlan}
              type="number"
              min={1}
              max={CRAWL_MAX_PAGES}
              defaultValue={client.crawl_page_limit ?? ""}
              placeholder={`${CRAWL_DEFAULT_PAGES} (default)`}
            />
          </FieldLabel>
          <p className="self-center text-xs text-[var(--text-secondary)]">
            Blank uses {CRAWL_DEFAULT_PAGES.toLocaleString()}. Raise it for large blogs
            or catalogues; the ceiling is {CRAWL_MAX_PAGES.toLocaleString()}. A crawl
            that stops at the limit says so on the sync job.
          </p>
        </div>
        <div className="flex flex-col gap-1">
          <FieldLabel label="Other names the brand is searched by (optional)">
            <textarea
              name="brand_aliases"
              rows={3}
              defaultValue={(client.brand_aliases ?? []).join("\n")}
              placeholder="One per line, e.g. acc technical services"
              className="w-full rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-sm"
            />
          </FieldLabel>
          <p className="text-xs text-[var(--text-secondary)]">
            The name and domain are already covered. Add the spellings people really
            type — a query that names the business is navigation, and no page change
            or link moves it, so the plan will not prescribe one.
          </p>
        </div>
        <div className="flex flex-col gap-1">
          <FieldLabel label="Sitemap URL (optional)">
            <Input
              name="sitemap_url"
              type="url"
              defaultValue={client.sitemap_url ?? ""}
              placeholder="Found automatically — set only if it isn't"
            />
          </FieldLabel>
          <p className="text-xs text-[var(--text-secondary)]">
            The crawler reads robots.txt and tries the usual locations. Set this only
            when a site hides its sitemap somewhere unusual, or serves HTML for every
            unknown path so nothing is discoverable.
          </p>
        </div>
      </div>

      {selectedTier && !enterprise ? (
        <div className="rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface-muted)] p-4">
          <p className="font-[family-name:var(--font-display)] text-[15px] font-extrabold text-[var(--text-primary)]">
            {selectedTier.tier_name} plan allowances
          </p>
          <dl className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <dt className="text-xs text-[var(--text-tertiary)]">Watchlist</dt>
              <dd className="text-sm font-semibold">
                {allowances.trackedKeywordLimit} keywords + AI prompts
              </dd>
              <dd className="text-xs text-[var(--text-secondary)]">
                Checked {formatCadence(allowances.watchlistCadence)}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-[var(--text-tertiary)]">New content</dt>
              <dd className="text-sm font-semibold">{allowances.contentAllowance} per quarter</dd>
            </div>
            <div>
              <dt className="text-xs text-[var(--text-tertiary)]">Content refresh</dt>
              <dd className="text-sm font-semibold">{allowances.updateAllowance} per quarter</dd>
            </div>
            <div>
              <dt className="text-xs text-[var(--text-tertiary)]">Growth Actions</dt>
              <dd className="text-sm font-semibold">
                {allowances.growthActionAllowance} per month
              </dd>
            </div>
          </dl>
          <p className="mt-2 text-xs text-[var(--text-secondary)]">
            Decision Engine uses the monthly Growth Action allowance for how many accepted
            recommendations count toward the plan — without changing scores.
          </p>
        </div>
      ) : null}

      {enterprise ? (
        <div className="rounded-[var(--radius-lg,14px)] border border-[var(--border)] bg-[var(--surface)] p-5 space-y-4">
          <div>
            <p className="font-[family-name:var(--font-display)] text-[15px] font-extrabold text-[var(--text-primary)]">
              Enterprise custom allowances
            </p>
            <p className="mt-1 text-sm text-[var(--text-secondary)]">
              Set agreement-specific amounts for this client. These override the catalog and drive
              Watch List limits and the Decision Engine growth-plan allowance.
            </p>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <FieldLabel label="Watchlist (keywords + AI prompts)">
              <Input
                name="custom_tracked_keyword_limit"
                disabled={!canEditPlan}
                type="number"
                min={0}
                required
                defaultValue={
                  client.custom_tracked_keyword_limit ??
                  (allowances.trackedKeywordLimit || "")
                }
              />
            </FieldLabel>
            <FieldLabel label="Watchlist cadence">
              <Select
                name="custom_watchlist_cadence"
                disabled={!canEditPlan}
                defaultValue={client.custom_watchlist_cadence ?? allowances.watchlistCadence}
              >
                {CADENCE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </Select>
            </FieldLabel>
            <FieldLabel label="New content per quarter">
              <Input
                name="custom_content_allowance"
                disabled={!canEditPlan}
                type="number"
                min={0}
                required
                defaultValue={
                  client.custom_content_allowance ?? (allowances.contentAllowance || "")
                }
              />
            </FieldLabel>
            <FieldLabel label="Content refresh per quarter">
              <Input
                name="custom_update_allowance"
                disabled={!canEditPlan}
                type="number"
                min={0}
                required
                defaultValue={
                  client.custom_update_allowance ?? (allowances.updateAllowance || "")
                }
              />
            </FieldLabel>
            <FieldLabel label="Growth Actions per month">
              <Input
                name="custom_growth_action_allowance"
                disabled={!canEditPlan}
                type="number"
                min={0}
                required
                defaultValue={
                  client.custom_growth_action_allowance ??
                  (allowances.growthActionAllowance || "")
                }
              />
            </FieldLabel>
          </div>
        </div>
      ) : null}

      <Button type="submit" variant="primary" disabled={pending}>
        {pending ? "Saving…" : "Save client settings"}
      </Button>
    </form>
  );
}
