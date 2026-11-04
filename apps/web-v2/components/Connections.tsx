"use client";

import { useEffect, useState, useTransition } from "react";

import { updateClientAction } from "@/app/(app)/[clientSlug]/settings/client-actions";
import * as act from "@/app/(app)/[clientSlug]/settings/connections/actions";
import { PullPanel } from "@/components/PullPanel";
import { inputClass } from "@/components/ui/form";
import { SearchList } from "@/components/ui/SearchList";
import type { Client } from "@/lib/api";
import type { ActionResult } from "@/lib/client-settings";
import type { Connections, IntegrationRow, Option, OptionsResult } from "@/lib/connections";
import { Spinner } from "@/components/ui/Spinner";

type Tone = "ok" | "warn" | "bad" | "off";
const DOT: Record<Tone, string> = { ok: "bg-green-500", warn: "bg-amber-500", bad: "bg-red-500", off: "bg-gray-300" };
const TEXT: Record<Tone, string> = { ok: "text-green-800", warn: "text-amber-800", bad: "text-red-800", off: "text-[var(--text-tertiary)]" };

function Problem({ text }: { text: string | null }) {
  return text ? (
    <p role="alert" className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-800">
      {text}
    </p>
  ) : null;
}

/** One row per source, all alike: a mark, what it is connected to, whether it is working, and a way to change it. */
function Row({
  logo,
  name,
  value,
  tone,
  status,
  error,
  action,
  open,
  onToggle,
  children,
}: {
  logo: string;
  name: string;
  value: string | null;
  tone: Tone;
  status: string;
  error?: string | null;
  action: string;
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  return (
    <li className="p-4">
      <div className="flex flex-wrap items-center gap-3">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={`/logos/${logo}.png`} alt="" width={40} height={40} className="h-10 w-10 shrink-0 rounded-lg border border-[var(--border)] bg-white object-contain p-1" />
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold">{name}</div>
          <div className="truncate text-sm text-[var(--text-secondary)]">{value ?? "Not chosen yet"}</div>
        </div>
        <span className={`flex items-center gap-1.5 text-xs font-semibold ${TEXT[tone]}`}>
          <span className={`h-2 w-2 rounded-full ${DOT[tone]}`} />
          {status}
        </span>
        <button type="button" onClick={onToggle} className="rounded-lg border border-[var(--border)] px-3 py-1.5 text-sm font-semibold hover:bg-[var(--bg)]">
          {open ? "Close" : action}
        </button>
      </div>
      {error ? <Problem text={error} /> : null}
      {open ? <div className="mt-3 rounded-lg bg-[var(--bg)] p-4">{children}</div> : null}
    </li>
  );
}

/** Load the provider's list as soon as it opens, choose one, save it. */
function Picker({
  load,
  save,
  label,
  empty,
  onSaved,
}: {
  load: () => Promise<OptionsResult>;
  save: (value: string, label: string) => Promise<ActionResult>;
  label: string;
  empty?: string;
  onSaved: () => void;
}) {
  const [options, setOptions] = useState<Option[] | null>(null);
  const [choice, setChoice] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  useEffect(() => {
    let live = true;
    load().then((r) => {
      if (!live) return;
      if (r.ok) setOptions(r.options);
      else setError(r.error);
    });
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const chosenLabel = options?.find((o) => o.value === choice)?.label ?? "";
  return (
    <div>
      {options === null && !error ? <p className="text-sm text-[var(--text-secondary)]">Loading…</p> : null}
      {options && options.length === 0 ? <p className="text-sm text-[var(--text-secondary)]">{empty ?? "Nothing available to choose."}</p> : null}
      {options && options.length > 0 ? (
        <div className="space-y-3">
          <SearchList options={options} value={choice} onChange={setChoice} label={label} />
          <button
            type="button"
            disabled={pending || !choice}
            onClick={() =>
              startTransition(async () => {
                setError(null);
                const result = await save(choice, chosenLabel || choice);
                if (result.ok) onSaved();
                else setError(result.error);
              })
            }
            className="rounded-lg bg-[var(--brand-teal)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
          >
            {pending ? <><Spinner />Saving…</> : `Save${choice ? ` “${chosenLabel.slice(0, 40)}”` : ""}`}
          </button>
        </div>
      ) : null}
      <Problem text={error} />
    </div>
  );
}

/** A value typed by hand, for when there is nothing to choose from on this install. */
function TypedValue({ placeholder, initial, save, onSaved }: { placeholder: string; initial: string; save: (v: string) => Promise<ActionResult>; onSaved: () => void }) {
  const [text, setText] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();
  return (
    <div>
      <div className="flex gap-3">
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder={placeholder} aria-label={placeholder} className={inputClass} />
        <button
          type="button"
          disabled={pending || !text.trim()}
          onClick={() =>
            start(async () => {
              setError(null);
              const r = await save(text.trim());
              if (r.ok) onSaved();
              else setError(r.error);
            })
          }
          className="shrink-0 rounded-lg bg-[var(--brand-teal)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
        >
          {pending ? <><Spinner />Saving…</> : "Save"}
        </button>
      </div>
      <Problem text={error} />
    </div>
  );
}

function rowState(row: IntegrationRow | undefined): { tone: Tone; status: string } {
  if (!row || !row.external_property_id) return { tone: "off", status: "Not set up" };
  if (row.connection_status === "error") return { tone: "bad", status: "Problem" };
  if (row.connection_status === "connected") return { tone: "ok", status: "Connected" };
  return { tone: "warn", status: "Not checked" };
}

export function ConnectionsPanel({
  client,
  integrations,
  connections,
  isAdmin,
  oauth,
}: {
  client: Client;
  integrations: IntegrationRow[];
  connections: Connections;
  isAdmin: boolean;
  oauth?: { status: string; message?: string };
}) {
  const row = (provider: IntegrationRow["provider"]) => integrations.find((i) => i.provider === provider);
  const gsc = row("gsc");
  const ga4 = row("ga4");
  const ser = row("se_ranking");
  const bing = connections.bing;
  const [open, setOpen] = useState<string | null>(null);
  const toggle = (key: string) => setOpen((o) => (o === key ? null : key));
  const close = () => setOpen(null);
  const [connectError, setConnectError] = useState<string | null>(null);
  const [connecting, startConnect] = useTransition();
  const [bingPending, startBing] = useTransition();

  const googleLinked = gsc?.connection_status === "connected" || ga4?.connection_status === "connected";
  const connectGoogle = () =>
    startConnect(async () => {
      setConnectError(null);
      const result = await act.startGoogleConnectAction(client.id);
      if (result.ok) window.location.href = result.url;
      else setConnectError(result.error);
    });

  const bingTone: { tone: Tone; status: string } = !bing
    ? { tone: "off", status: "Not set up" }
    : bing.status === "error"
      ? { tone: "bad", status: "Problem" }
      : bing.status === "connected"
        ? { tone: "ok", status: "Connected" }
        : { tone: "warn", status: "Not checked" };

  return (
    <div className="space-y-6">
      {oauth?.status === "connected" ? (
        <p className="rounded-lg bg-green-50 p-3 text-sm text-green-800">Google connected. Choose the Search Console site and GA4 property below.</p>
      ) : null}
      {oauth?.status === "error" ? (
        <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">
          Google did not connect ({oauth.message ?? "unknown reason"}). Try again.
        </p>
      ) : null}

      {!googleLinked ? (
        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5">
          <h2 className="text-sm font-semibold">Connect Google first</h2>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            One Google sign-in covers Search Console and GA4 for every client. Admin only.
          </p>
          {connections.google_connect_configured ? (
            <button type="button" disabled={connecting} onClick={connectGoogle} className="mt-3 rounded-lg bg-[var(--brand-dark)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">
              {connecting ? <><Spinner />Opening Google…</> : "Connect Google"}
            </button>
          ) : (
            <p className="mt-3 text-sm text-amber-800">Not configured on this install: GOOGLE_DATA_OAUTH_CLIENT_ID and SECRET are missing.</p>
          )}
          <Problem text={connectError} />
        </div>
      ) : null}

      <ul className="divide-y divide-[var(--border)] rounded-xl border border-[var(--border)] bg-[var(--surface)]">
        <Row logo="search-console" name="Search Console" value={gsc?.external_property_id ?? null} {...rowState(gsc)} error={gsc?.error_message} action={gsc?.external_property_id ? "Change" : "Choose"} open={open === "gsc"} onToggle={() => toggle("gsc")}>
          <Picker label="Search Console site" load={() => act.loadGscSitesAction(client.id)} save={(v) => act.saveGscAction(client.id, client.slug, v, gsc?.external_property_id ?? null)} empty="This Google account has no Search Console sites." onSaved={close} />
        </Row>

        <Row logo="ga4" name="Google Analytics 4" value={ga4?.external_property_id ?? null} {...rowState(ga4)} error={ga4?.error_message} action={ga4?.external_property_id ? "Change" : "Choose"} open={open === "ga4"} onToggle={() => toggle("ga4")}>
          <Picker label="GA4 property" load={() => act.loadGa4Action(client.id)} save={(v) => act.saveGa4Action(client.id, client.slug, v, ga4?.external_property_id ?? null)} empty="This Google account has no GA4 properties." onSaved={close} />
        </Row>

        <Row logo="se-ranking" name="SE Ranking" value={ser?.external_account_id ?? ser?.external_property_id ?? null} {...rowState(ser)} action={ser?.external_property_id ? "Change" : "Choose"} open={open === "ser"} onToggle={() => toggle("ser")}>
          {connections.se_ranking_key_configured ? (
            <Picker label="SE Ranking project" load={() => act.loadSeRankingAction(client.id)} save={(v, l) => act.saveSeRankingAction(client.id, client.slug, v, l, ser?.external_property_id ?? null)} onSaved={close} />
          ) : (
            <p className="text-sm text-amber-800">Not configured on this install: SE_RANKING_API_KEY is missing.</p>
          )}
        </Row>

        <Row logo="bing" name="Bing Webmaster" value={bing?.site_url ?? null} {...bingTone} error={bing?.error} action={bing ? "Change" : "Choose"} open={open === "bing"} onToggle={() => toggle("bing")}>
          {connections.bing_key_configured ? (
            <Picker label="Site in the Bing account" load={() => act.loadBingSitesAction(client.id)} save={(v) => act.saveBingAction(client.id, client.slug, v, bing?.site_url ?? null)} onSaved={close} />
          ) : (
            <div>
              <p className="mb-2 text-sm text-amber-800">BING_WEBMASTER_API_KEY is not set on this install, so the site can be saved but not checked.</p>
              <TypedValue placeholder="https://example.com/" initial={bing?.site_url ?? ""} save={(v) => act.saveBingAction(client.id, client.slug, v, bing?.site_url ?? null)} onSaved={close} />
            </div>
          )}
          {bing ? (
            <button
              type="button"
              disabled={bingPending}
              onClick={() =>
                startBing(async () => {
                  await act.clearBingAction(client.id, client.slug);
                  close();
                })
              }
              className="mt-3 text-xs font-semibold text-red-700 hover:underline disabled:opacity-50"
            >
              Remove Bing site
            </button>
          ) : null}
        </Row>

        <Row
          logo="teamwork"
          name="Teamwork: growth actions"
          value={connections.teamwork_tasklist_id ? `Tasklist ${connections.teamwork_tasklist_id}` : null}
          tone={!connections.teamwork_configured ? "bad" : connections.teamwork_tasklist_id ? "ok" : "off"}
          status={!connections.teamwork_configured ? "Not configured" : connections.teamwork_tasklist_id ? "Connected" : "Not set up"}
          error={connections.teamwork_configured ? null : "This install has no Teamwork site or token (TEAMWORK_SITE, TEAMWORK_API_TOKEN), so growth actions can be copied but not sent."}
          action={connections.teamwork_tasklist_id ? "Change" : "Choose"}
          open={open === "tw"}
          onToggle={() => toggle("tw")}
        >
          {connections.teamwork_configured ? (
            <div className="space-y-4">
              <Picker
                label="Teamwork tasklist"
                load={() => act.loadTeamworkTasklistsAction(client.id)}
                save={(v) => updateClientAction(client.id, client.slug, { teamwork_tasklist_id: v })}
                empty="This Teamwork token can't see any tasklists."
                onSaved={close}
              />
              <div>
                <p className="mb-1 text-xs text-[var(--text-secondary)]">Or enter a tasklist ID</p>
                <TypedValue placeholder="Tasklist ID" initial={connections.teamwork_tasklist_id ?? ""} save={(v) => updateClientAction(client.id, client.slug, { teamwork_tasklist_id: v })} onSaved={close} />
              </div>
            </div>
          ) : (
            <TypedValue placeholder="Tasklist ID" initial={connections.teamwork_tasklist_id ?? ""} save={(v) => updateClientAction(client.id, client.slug, { teamwork_tasklist_id: v })} onSaved={close} />
          )}
        </Row>
        <Row
          logo="teamwork"
          name="Teamwork: content"
          value={connections.teamwork_content_project_id ? `Project ${connections.teamwork_content_project_id}` : null}
          tone={!connections.teamwork_configured ? "bad" : connections.teamwork_content_project_id ? "ok" : "off"}
          status={!connections.teamwork_configured ? "Not configured" : connections.teamwork_content_project_id ? "Connected" : "Not set up"}
          error={connections.teamwork_configured ? null : "This install has no Teamwork site or token (TEAMWORK_SITE, TEAMWORK_API_TOKEN), so content items can be added to the calendar but not sent. Each item gets its own list in the project you choose here."}
          action={connections.teamwork_content_project_id ? "Change" : "Choose"}
          open={open === "twc"}
          onToggle={() => toggle("twc")}
        >
          {connections.teamwork_configured ? (
            <div className="space-y-4">
              <Picker
                label="Content project"
                load={() => act.loadTeamworkProjectsAction(client.id)}
                save={(v) => updateClientAction(client.id, client.slug, { teamwork_content_project_id: v })}
                empty="This Teamwork token can't see any projects."
                onSaved={close}
              />
              <div>
                <p className="mb-1 text-xs text-[var(--text-secondary)]">Or enter a project ID</p>
                <TypedValue placeholder="Project ID" initial={connections.teamwork_content_project_id ?? ""} save={(v) => updateClientAction(client.id, client.slug, { teamwork_content_project_id: v })} onSaved={close} />
              </div>
            </div>
          ) : (
            <TypedValue placeholder="Project ID" initial={connections.teamwork_content_project_id ?? ""} save={(v) => updateClientAction(client.id, client.slug, { teamwork_content_project_id: v })} onSaved={close} />
          )}
        </Row>
      </ul>

      {/* Keyed by what is connected, so choosing or changing a source reloads what there is to pull. */}
      {isAdmin ? <PullPanel key={[gsc?.external_property_id, ga4?.external_property_id, ser?.external_property_id, bing?.site_url].join("|")} clientId={client.id} /> : null}

      {googleLinked && connections.google_connect_configured ? (
        <p className="text-xs text-[var(--text-tertiary)]">
          Google is connected for every client.{" "}
          <button type="button" disabled={connecting} onClick={connectGoogle} className="font-semibold underline disabled:opacity-50">
            {connecting ? <><Spinner />Opening Google…</> : "Reconnect Google"}
          </button>{" "}
          only if its sign-in has expired; it replaces the shared sign-in.
          {connectError ? <span className="ml-1 text-red-700">{connectError}</span> : null}
        </p>
      ) : null}
    </div>
  );
}
