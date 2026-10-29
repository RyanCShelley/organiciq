"use client";

import { useState, useTransition } from "react";

import { updateClientAction } from "@/app/(app)/[clientSlug]/settings/client-actions";
import * as act from "@/app/(app)/[clientSlug]/settings/connections/actions";
import { Field, inputClass } from "@/components/ui/form";
import { SearchList } from "@/components/ui/SearchList";
import type { Client } from "@/lib/api";
import type { ActionResult } from "@/lib/client-settings";
import type { BingSite, Connections, IntegrationRow, Option, OptionsResult } from "@/lib/connections";

const STATUS_STYLE: Record<string, string> = {
  connected: "bg-green-50 text-green-800",
  error: "bg-red-50 text-red-800",
  unchecked: "bg-amber-50 text-amber-800",
  not_connected: "bg-[var(--bg)] text-[var(--text-secondary)]",
  disconnected: "bg-[var(--bg)] text-[var(--text-secondary)]",
};

function Badge({ status, label }: { status: string; label?: string }) {
  return (
    <span className={`rounded px-2 py-0.5 text-xs font-semibold ${STATUS_STYLE[status] ?? STATUS_STYLE.not_connected}`}>
      {label ?? status.replace("_", " ")}
    </span>
  );
}

/** A row says "connected" as soon as Google is, before a site is chosen: count it only once one is. */
function chosen(row: IntegrationRow | undefined): { status: string; label?: string } {
  if (!row || !row.external_property_id) return { status: "not_connected", label: "nothing chosen" };
  return { status: row.connection_status };
}

function Problem({ text }: { text: string | null }) {
  return text ? (
    <p role="alert" className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-800">
      {text}
    </p>
  ) : null;
}

/** Load a list from the provider, choose one, save it. */
function Picker({
  label,
  current,
  load,
  save,
  empty,
}: {
  label: string;
  current: string | null;
  load: () => Promise<OptionsResult>;
  save: (value: string, label: string) => Promise<ActionResult>;
  empty?: string;
}) {
  const [options, setOptions] = useState<Option[] | null>(null);
  const [choice, setChoice] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [pending, startTransition] = useTransition();

  function fetchOptions() {
    setError(null);
    startTransition(async () => {
      const result = await load();
      if (result.ok) setOptions(result.options);
      else setError(result.error);
    });
  }

  return (
    <div>
      <p className="text-sm">
        <span className="text-[var(--text-secondary)]">{label}: </span>
        <span className="font-medium">{current ?? "not chosen"}</span>
      </p>
      {options === null ? (
        <button
          type="button"
          disabled={pending}
          onClick={fetchOptions}
          className="mt-2 text-sm font-semibold text-[var(--brand-teal)] hover:underline disabled:opacity-50"
        >
          {pending ? "Loading…" : current ? "Change…" : "Choose…"}
        </button>
      ) : options.length === 0 ? (
        <p className="mt-2 text-sm text-[var(--text-secondary)]">{empty ?? "Nothing available to choose."}</p>
      ) : (
        <div className="mt-2 space-y-3">
          <SearchList options={options} value={choice} onChange={setChoice} label={label} />
          <div className="flex items-center gap-3">
            <button
              type="button"
              disabled={pending || !choice}
              onClick={() =>
                startTransition(async () => {
                  setError(null);
                  setSaved(false);
                  const label = options.find((o) => o.value === choice)?.label ?? choice;
                  const result = await save(choice, label);
                  if (result.ok) {
                    setSaved(true);
                    setOptions(null);
                    setChoice("");
                  } else setError(result.error);
                })
              }
              className="rounded-lg bg-[var(--brand-teal)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
            >
              Save{choice ? ` “${options.find((o) => o.value === choice)?.label.slice(0, 40) ?? ""}”` : ""}
            </button>
            <button
              type="button"
              onClick={() => {
                setOptions(null);
                setChoice("");
              }}
              className="text-sm text-[var(--text-secondary)] hover:underline"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
      {saved ? <p className="mt-2 text-sm text-[var(--text-secondary)]">Saved.</p> : null}
      <Problem text={error} />
    </div>
  );
}

function Section({
  title,
  badge,
  children,
}: {
  title: string;
  badge: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold">{title}</h2>
        {badge}
      </div>
      {children}
    </div>
  );
}

export function ConnectionsPanel({
  client,
  integrations,
  connections,
  oauth,
}: {
  client: Client;
  integrations: IntegrationRow[];
  connections: Connections;
  oauth?: { status: string; message?: string };
}) {
  const row = (provider: IntegrationRow["provider"]) => integrations.find((i) => i.provider === provider);
  const gsc = row("gsc");
  const ga4 = row("ga4");
  const ser = row("se_ranking");
  const [connectError, setConnectError] = useState<string | null>(null);
  const [connecting, startConnect] = useTransition();
  const [tasklist, setTasklist] = useState(connections.teamwork_tasklist_id ?? "");
  const [twResult, setTwResult] = useState<ActionResult | null>(null);
  const [twPending, startTw] = useTransition();
  const [bingText, setBingText] = useState("");
  const [bingError, setBingError] = useState<string | null>(null);
  const [bingPending, startBing] = useTransition();
  const bing: BingSite | null = connections.bing;

  return (
    <div className="space-y-6">
      {oauth?.status === "connected" ? (
        <p className="rounded-lg bg-green-50 p-3 text-sm text-green-800">
          Google connected. Choose the Search Console site and GA4 property below.
        </p>
      ) : null}
      {oauth?.status === "error" ? (
        <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">
          Google did not connect ({oauth.message ?? "unknown reason"}). Try again.
        </p>
      ) : null}

      <Section
        title="Google"
        badge={<Badge status={gsc?.connection_status === "connected" || ga4?.connection_status === "connected" ? "connected" : "not_connected"} />}
      >
        <p className="text-sm text-[var(--text-secondary)]">
          One Google sign-in covers Search Console and GA4 for <strong>every</strong> client. Admin only.
          Connecting again replaces the shared sign-in.
        </p>
        {connections.google_connect_configured ? (
          <button
            type="button"
            disabled={connecting}
            onClick={() =>
              startConnect(async () => {
                setConnectError(null);
                const result = await act.startGoogleConnectAction(client.id);
                if (result.ok) window.location.href = result.url;
                else setConnectError(result.error);
              })
            }
            className="mt-3 rounded-lg bg-[var(--brand-dark)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
          >
            {connecting ? "Opening Google…" : "Connect Google"}
          </button>
        ) : (
          <p className="mt-3 text-sm text-amber-800">
            Not configured on this install: GOOGLE_DATA_OAUTH_CLIENT_ID and SECRET are missing.
          </p>
        )}
        <Problem text={connectError} />
      </Section>

      <Section title="Search Console" badge={<Badge {...chosen(gsc)} />}>
        <Picker
          label="Site"
          current={gsc?.external_property_id ?? null}
          load={() => act.loadGscSitesAction(client.id)}
          save={(value) => act.saveGscAction(client.id, client.slug, value)}
          empty="This Google account has no Search Console sites."
        />
        {gsc?.error_message ? <Problem text={gsc.error_message} /> : null}
      </Section>

      <Section title="Google Analytics 4" badge={<Badge {...chosen(ga4)} />}>
        <Picker
          label="Property"
          current={ga4?.external_property_id ?? null}
          load={() => act.loadGa4Action(client.id)}
          save={(value) => act.saveGa4Action(client.id, client.slug, value)}
          empty="This Google account has no GA4 properties."
        />
        {ga4?.error_message ? <Problem text={ga4.error_message} /> : null}
      </Section>

      <Section title="SE Ranking" badge={<Badge {...chosen(ser)} />}>
        {connections.se_ranking_key_configured ? (
          <Picker
            label="Project"
            current={ser?.external_account_id ?? ser?.external_property_id ?? null}
            load={() => act.loadSeRankingAction(client.id)}
            save={(value, label) => act.saveSeRankingAction(client.id, client.slug, value, label)}
          />
        ) : (
          <p className="text-sm text-amber-800">Not configured on this install: SE_RANKING_API_KEY is missing.</p>
        )}
      </Section>

      <Section
        title="Bing Webmaster"
        badge={bing ? <Badge status={bing.status} /> : <Badge status="not_connected" />}
      >
        <p className="mb-3 text-sm text-[var(--text-secondary)]">
          The site as it is listed in Bing Webmaster Tools. Query, page and traffic data comes later;
          this records which site is the client&apos;s and checks Bing has it verified.
        </p>
        {bing ? (
          <p className="mb-3 text-sm">
            <span className="text-[var(--text-secondary)]">Site: </span>
            <span className="font-medium">{bing.site_url}</span>
            {bing.status === "unchecked" ? (
              <span className="text-[var(--text-secondary)]"> (not checked: no Bing API key on this install)</span>
            ) : null}
          </p>
        ) : null}
        {bing?.error ? <Problem text={bing.error} /> : null}
        {connections.bing_key_configured ? (
          <Picker
            label="Choose from the Bing account"
            current={bing?.site_url ?? null}
            load={() => act.loadBingSitesAction(client.id)}
            save={(value) => act.saveBingAction(client.id, client.slug, value)}
          />
        ) : (
          <div>
            <p className="mb-2 text-sm text-amber-800">
              BING_WEBMASTER_API_KEY is not set on this install, so the site can be saved but not checked.
            </p>
            <div className="flex gap-3">
              <input
                value={bingText}
                onChange={(e) => setBingText(e.target.value)}
                placeholder="https://example.com/"
                aria-label="Bing site"
                className={inputClass}
              />
              <button
                type="button"
                disabled={bingPending || !bingText.trim()}
                onClick={() =>
                  startBing(async () => {
                    setBingError(null);
                    const result = await act.saveBingAction(client.id, client.slug, bingText.trim());
                    if (!result.ok) setBingError(result.error);
                    else setBingText("");
                  })
                }
                className="shrink-0 rounded-lg bg-[var(--brand-teal)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
              >
                Save
              </button>
            </div>
            <Problem text={bingError} />
          </div>
        )}
        {bing ? (
          <button
            type="button"
            disabled={bingPending}
            onClick={() => startBing(async () => void (await act.clearBingAction(client.id, client.slug)))}
            className="mt-3 text-xs font-semibold text-red-700 hover:underline disabled:opacity-50"
          >
            Remove Bing site
          </button>
        ) : null}
      </Section>

      <Section
        title="Teamwork"
        badge={<Badge status={connections.teamwork_configured ? "connected" : "not_connected"} label={connections.teamwork_configured ? "install configured" : "not configured"} />}
      >
        {connections.teamwork_configured ? null : (
          <p className="mb-3 text-sm text-amber-800">
            This install has no Teamwork site or token (TEAMWORK_SITE, TEAMWORK_API_TOKEN), so growth
            actions can be copied but not sent.
          </p>
        )}
        <form
          onSubmit={(event) => {
            event.preventDefault();
            startTw(async () => {
              setTwResult(null);
              setTwResult(
                await updateClientAction(client.id, client.slug, {
                  teamwork_tasklist_id: tasklist.trim() || null,
                }),
              );
            });
          }}
        >
          <Field
            label="Tasklist ID"
            hint="The Teamwork tasklist this client's sent growth actions land in. The site and token are shared by every client."
          >
            <input
              value={tasklist}
              onChange={(e) => {
                setTasklist(e.target.value);
                setTwResult(null);
              }}
              className={inputClass}
            />
          </Field>
          <button
            type="submit"
            disabled={twPending}
            className="mt-3 rounded-lg bg-[var(--brand-dark)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
          >
            Save
          </button>
          {twResult?.ok ? <span className="ml-3 text-sm text-[var(--text-secondary)]">Saved.</span> : null}
          {twResult && !twResult.ok ? <Problem text={twResult.error} /> : null}
        </form>
      </Section>
    </div>
  );
}
