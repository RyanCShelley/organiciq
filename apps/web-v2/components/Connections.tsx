"use client";

import { useEffect, useState, useTransition } from "react";

import { updateClientAction } from "@/app/(app)/[clientSlug]/settings/client-actions";
import * as act from "@/app/(app)/[clientSlug]/settings/connections/actions";
import { PullPanel } from "@/components/PullPanel";
import { inputClass } from "@/components/ui/form";
import { SearchList } from "@/components/ui/SearchList";
import type { Client } from "@/lib/api";
import type { ActionResult } from "@/lib/client-settings";
import type { AdsAccount, AdsConnection, AdsDiagnosis, AdsPullResult, Connections, IntegrationRow, Option, OptionsResult } from "@/lib/connections";
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
  logo: string | null;
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
        {logo ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={`/logos/${logo}.png`} alt="" width={40} height={40} className="h-10 w-10 shrink-0 rounded-lg border border-[var(--border)] bg-white object-contain p-1" />
        ) : (
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg border border-[var(--border)] bg-white text-xs font-bold text-[var(--text-secondary)]" aria-hidden>Ads</span>
        )}
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
  ads,
  isAdmin,
  oauth,
}: {
  client: Client;
  integrations: IntegrationRow[];
  connections: Connections;
  ads?: AdsConnection | null;
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
  const [adsPulling, startAdsPull] = useTransition();
  const [adsError, setAdsError] = useState<string | null>(null);
  const [adsKind, setAdsKind] = useState<"ads" | "lsa">("ads");
  const [adsRemoving, startAdsRemove] = useTransition();
  const [adsPulled, setAdsPulled] = useState<AdsPullResult | null>(null);
  const [adsChecking, startAdsCheck] = useTransition();
  const [adsReport, setAdsReport] = useState<AdsDiagnosis | null>(null);
  const [adsReportError, setAdsReportError] = useState<string | null>(null);
  const checkAds = () =>
    startAdsCheck(async () => {
      setAdsReportError(null);
      const r = await act.diagnoseAdsAction(client.id);
      if (r.ok) setAdsReport(r.data);
      else setAdsReportError(r.error);
    });

  const googleLinked = gsc?.connection_status === "connected" || ga4?.connection_status === "connected";
  const connectGoogle = () =>
    startConnect(async () => {
      setConnectError(null);
      const result = await act.startGoogleConnectAction(client.id);
      if (result.ok) window.location.href = result.url;
      else setConnectError(result.error);
    });

  const accounts: AdsAccount[] = ads?.accounts ?? [];
  const adsValue = accounts.length ? accounts.map((a) => a.name || a.customer_id).join(", ") : null;
  const adsTone: { tone: Tone; status: string } = !ads
    ? { tone: "off", status: "Not set up" }
    : !ads.permission
      ? { tone: "warn", status: "Needs permission" }
      : accounts.some((a) => a.last_error)
        ? { tone: "bad", status: "Problem" }
        : accounts.length && accounts.every((a) => a.last_pull_at)
          ? { tone: "ok", status: "Connected" }
          : { tone: "off", status: accounts.length ? "Not pulled yet" : "Not chosen" };
  const pullAds = () =>
    startAdsPull(async () => {
      setAdsError(null);
      setAdsPulled(null);
      const r = await act.pullAdsAction(client.id, client.slug);
      if (r.ok) setAdsPulled(r.data);
      else setAdsError(r.error);
    });
  const changeAccount = (a: AdsAccount, name: string, kind: "ads" | "lsa") =>
    startAdsRemove(async () => {
      const r = await act.updateAdsAccountAction(client.id, client.slug, a.customer_id, name, kind);
      if (!r.ok) setAdsError(r.error);
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
        {ads?.enabled ? (
          <Row logo="google-ads" name="Google Ads" value={adsValue} {...adsTone} action={accounts.length ? "Change" : "Choose"} open={open === "ads"} onToggle={() => toggle("ads")}>
            {!ads.permission ? (
              <div className="space-y-2 text-sm">
                <p>The shared Google sign-in does not include Google Ads yet. An admin needs to reconnect Google and approve the Google Ads permission.</p>
                {isAdmin ? (
                  <button type="button" disabled={connecting} onClick={connectGoogle} className="rounded-lg bg-[var(--brand-dark)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">
                    {connecting ? <><Spinner />Opening Google…</> : "Reconnect Google"}
                  </button>
                ) : <p className="text-[var(--text-secondary)]">Ask an admin to do this.</p>}
                <Problem text={connectError} />
              </div>
            ) : !ads.manager_set ? (
              <p className="text-sm text-amber-800">Not configured on this install: GOOGLE_ADS_LOGIN_CUSTOMER_ID (the manager account, digits only) is missing.</p>
            ) : (
              <div className="space-y-4">
                {accounts.length > 0 ? (
                  <ul className="divide-y divide-[var(--border)] rounded-lg border border-[var(--border)] bg-white text-sm">
                    {accounts.map((a) => (
                      <li key={a.customer_id} className="p-3">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-semibold">{a.name || a.customer_id}</span>
                          {isAdmin ? (
                            <select aria-label={`Kind of account ${a.name || a.customer_id}`} value={a.kind} disabled={adsRemoving} onChange={(e) => changeAccount(a, a.name, e.target.value as "ads" | "lsa")} className="rounded border border-[var(--border)] bg-white px-1.5 py-0.5 text-xs font-semibold">
                              <option value="ads">Ads</option>
                              <option value="lsa">Local Services Ads</option>
                            </select>
                          ) : <span className="rounded bg-[var(--bg)] px-1.5 py-0.5 text-xs font-semibold text-[var(--text-secondary)]">{a.kind === "lsa" ? "Local Services Ads" : "Ads"}</span>}
                          <span className="text-xs text-[var(--text-tertiary)]">{a.customer_id.replace(/^(\d{3})(\d{3})(\d{4})$/, "$1-$2-$3")}{a.last_pull_at ? ` · pulled ${new Date(a.last_pull_at).toLocaleDateString("en-US", { month: "short", day: "numeric" })}` : ""}</span>
                          {isAdmin ? (
                            <button type="button" disabled={adsRemoving} onClick={() => { const n = window.prompt("What should this account be called?", a.name || ""); if (n !== null && n.trim()) changeAccount(a, n.trim(), a.kind); }} className="ml-auto text-xs underline disabled:opacity-50">Rename</button>
                          ) : null}
                          {isAdmin ? (
                            <button type="button" disabled={adsRemoving} onClick={() => startAdsRemove(async () => { const r = await act.removeAdsAccountAction(client.id, client.slug, a.customer_id); if (!r.ok) setAdsError(r.error); })} className="text-xs underline disabled:opacity-50">Remove</button>
                          ) : null}
                        </div>
                        {a.last_error ? <Problem text={a.last_error} /> : null}
                      </li>
                    ))}
                  </ul>
                ) : null}
                {isAdmin ? (
                  <div className="space-y-3">
                    <div className="text-sm font-semibold">Add an account</div>
                    <label className="block text-xs font-semibold">
                      What kind of account
                      <select value={adsKind} onChange={(e) => setAdsKind(e.target.value as "ads" | "lsa")} className="mt-1 block rounded-lg border border-[var(--border)] bg-white px-2 py-2 text-sm font-normal">
                        <option value="ads">Ads (search and other campaigns)</option>
                        <option value="lsa">Local Services Ads</option>
                      </select>
                    </label>
                    <Picker
                      key={accounts.map((a) => a.customer_id).join(",")}
                      label="Google Ads account"
                      load={() => act.loadAdsAccountsAction(accounts.map((a) => a.customer_id))}
                      save={(v, l) => act.addAdsAccountAction(client.id, client.slug, v, l.replace(/\s*\(\d{3}-\d{3}-\d{4}\)$/, ""), adsKind)}
                      empty="The manager account has no more client accounts this Google user can see."
                      onSaved={close}
                    />
                    {accounts.length > 0 ? (
                      <div>
                        <button type="button" disabled={adsPulling} onClick={pullAds} className="rounded-lg border border-[var(--border)] px-3 py-1.5 text-sm font-semibold hover:bg-white disabled:opacity-50">
                          {adsPulling ? <><Spinner />Pulling…</> : "Pull now"}
                        </button>
                        <p className="mt-1 text-xs text-[var(--text-tertiary)]">The numbers also pull once a day, and show under Pull data. The first pull goes back 90 days.</p>
                      </div>
                    ) : null}
                    <Problem text={adsError} />
                    {adsPulled ? (
                      <div className="rounded-lg bg-white p-3 text-xs text-[var(--text-secondary)]">
                        <div className="font-semibold text-[var(--text-primary,inherit)]">What this pull brought</div>
                        <ul className="mt-1 space-y-0.5">
                          {adsPulled.accounts.map((p) => <li key={p.account}>{accounts.find((a) => a.customer_id === p.account)?.name || p.account}: {p.rows.toLocaleString()} daily rows over {p.days} days ({p.from} to {p.to}), {p.markets.toLocaleString()} market rows, {p.terms.toLocaleString()} search rows{p.leads ? `, ${p.leads.toLocaleString()} Local Services leads` : ""}</li>)}
                        </ul>
                        {adsPulled.errors.map((e) => <p key={e} className="mt-1 text-red-700">{e}</p>)}
                      </div>
                    ) : null}
                  </div>
                ) : <p className="text-sm text-[var(--text-secondary)]">Ask an admin to add the Google Ads accounts.</p>}
                {isAdmin && accounts.length > 0 ? (
                  <div className="space-y-2 border-t border-[var(--border)] pt-3">
                    <div className="flex flex-wrap items-center gap-3">
                      <button type="button" disabled={adsChecking} onClick={checkAds} className="rounded-lg border border-[var(--border)] px-3 py-1.5 text-sm font-semibold hover:bg-white disabled:opacity-50">
                        {adsChecking ? <><Spinner />Asking Google Ads…</> : "Check what works"}
                      </button>
                      <span className="text-xs text-[var(--text-tertiary)]">Asks Google Ads what each account returns for the last 30 days. Read-only; nothing is saved.</span>
                    </div>
                    <Problem text={adsReportError} />
                    {adsReport ? (
                      <div className="space-y-3 text-sm">
                        <p className="text-xs text-[var(--text-tertiary)]">Checked {new Date(adsReport.checked_at).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}, the last {adsReport.days} days.</p>
                        {adsReport.accounts.map((a) => (
                          <div key={a.customer_id} className="rounded-lg border border-[var(--border)] bg-white">
                            <div className="border-b border-[var(--border)] px-3 py-2 font-semibold">{a.name || a.customer_id} <span className="font-normal text-[var(--text-tertiary)]">· {a.kind === "lsa" ? "Local Services Ads" : "Ads"} · {a.customer_id.replace(/^(\d{3})(\d{3})(\d{4})$/, "$1-$2-$3")}</span></div>
                            <ul className="divide-y divide-[var(--border)]">
                              {a.checks.map((c) => (
                                <li key={c.name} className="flex gap-3 px-3 py-2">
                                  <span className={`w-16 shrink-0 text-xs font-semibold ${c.status === "ok" ? "text-green-700" : c.status === "empty" ? "text-amber-700" : "text-red-700"}`}>{c.status === "ok" ? "Works" : c.status === "empty" ? "Empty" : "Refused"}</span>
                                  <div className="min-w-0 flex-1">
                                    <div className="font-semibold">{c.name}</div>
                                    <div className={c.status === "error" ? "text-red-800" : "text-[var(--text-secondary)]"}>{c.detail}</div>
                                    {c.sample ? (
                                      <details className="mt-0.5 text-xs text-[var(--text-tertiary)]">
                                        <summary className="cursor-pointer font-semibold">First row Google sent</summary>
                                        <pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-all rounded bg-[var(--bg)] p-2">{c.sample}</pre>
                                      </details>
                                    ) : null}
                                  </div>
                                </li>
                              ))}
                            </ul>
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </div>
            )}
          </Row>
        ) : null}
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
