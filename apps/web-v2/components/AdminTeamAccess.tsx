"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState, useTransition } from "react";

import { addPersonAction, removePeopleAction, restorePeopleAction, teamAssignAction, teamRemoveAction } from "@/app/(app)/admin/actions";
import { Spinner } from "@/components/ui/Spinner";
import type { TeamAccessData } from "@/lib/admin";

const ROLE: Record<string, string> = { sma_admin: "Admin", sma_team: "Team", seo_lead: "SEO lead", content_manager: "Content manager" };
const box = "rounded-xl border border-[var(--border)] bg-[var(--surface)]";

function toggle(set: Set<string>, id: string): Set<string> {
  const next = new Set(set);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  return next;
}

/**
 * Give people access to clients, many at once or one by one: choose the people, choose the clients, then give or remove access.
 * One person and one client is the one-by-one case. An admin sees every client by role, so there is nothing to give.
 */
export function AdminTeamAccess({ data }: { data: TeamAccessData }) {
  const router = useRouter();
  const [people, setPeople] = useState<Set<string>>(new Set());
  const [clients, setClients] = useState<Set<string>>(new Set());
  const [pq, setPq] = useState("");
  const [cq, setCq] = useState("");
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [pending, start] = useTransition();
  const [adding, setAdding] = useState(false);
  const [newEmail, setNewEmail] = useState("");
  const [newName, setNewName] = useState("");
  const [newRole, setNewRole] = useState<"sma_team" | "sma_admin">("sma_team");

  const users = data.users.filter((u) => u.is_active);
  const removed = data.users.filter((u) => !u.is_active);
  const shownPeople = useMemo(() => users.filter((u) => `${u.name ?? ""} ${u.email}`.toLowerCase().includes(pq.trim().toLowerCase())), [users, pq]);
  const shownClients = useMemo(() => data.clients.filter((c) => `${c.name} ${c.domain}`.toLowerCase().includes(cq.trim().toLowerCase())), [data.clients, cq]);
  const chosen = users.filter((u) => people.has(u.id));
  const needy = chosen.filter((u) => !u.sees_all); // people an assignment can change
  const accessOf = (clientId: string) => needy.filter((u) => u.client_ids.includes(clientId)).length;

  const allPeople = shownPeople.length > 0 && shownPeople.every((u) => people.has(u.id));
  const allClients = shownClients.length > 0 && shownClients.every((c) => clients.has(c.id));
  const ready = people.size > 0 && clients.size > 0;

  const run = (kind: "give" | "remove") => {
    if (kind === "remove" && !window.confirm(`Remove access for ${people.size} ${people.size === 1 ? "person" : "people"} on ${clients.size} ${clients.size === 1 ? "client" : "clients"}? They can sign in again but will not see those clients.`)) return;
    start(async () => {
      setMessage(null);
      const ids = [Array.from(people), Array.from(clients)] as const;
      if (kind === "give") {
        const r = await teamAssignAction(ids[0], ids[1]);
        if (!r.ok) return setMessage({ ok: false, text: r.error });
        const v = r.value;
        setMessage({ ok: true, text: `Gave access ${v.added} ${v.added === 1 ? "time" : "times"}${v.already ? `; ${v.already} already had it` : ""}${v.admins_skipped ? `; ${v.admins_skipped} ${v.admins_skipped === 1 ? "admin sees" : "admins see"} every client already` : ""}.` });
      } else {
        const r = await teamRemoveAction(ids[0], ids[1]);
        if (!r.ok) return setMessage({ ok: false, text: r.error });
        setMessage({ ok: true, text: `Removed access ${r.value.removed} ${r.value.removed === 1 ? "time" : "times"}${r.value.admins_skipped ? `; admin access is by role and was left` : ""}.` });
      }
      router.refresh();
    });
  };

  const addPerson = () =>
    start(async () => {
      setMessage(null);
      const r = await addPersonAction(newEmail, newName, newRole);
      if (!r.ok) return setMessage({ ok: false, text: r.error });
      // Chosen straight away, so the next step is to choose their clients and give access.
      setPeople((p) => new Set(p).add(r.value.id));
      setPq("");
      setNewEmail("");
      setNewName("");
      setNewRole("sma_team");
      setAdding(false);
      setMessage({ ok: true, text: `${r.value.outcome === "restored" ? "Let back in" : "Added"} ${r.value.email}. ${r.value.emailed ? "We emailed them how to sign in." : "We could not email them, so send them the sign-in link yourself."} Choose their clients, then Give access.` });
      router.refresh();
    });

  const removePeople = () => {
    if (!window.confirm(`Remove ${people.size} ${people.size === 1 ? "person" : "people"} from Organic IQ? They can no longer sign in and lose access to every client. You can restore them later.`)) return;
    start(async () => {
      setMessage(null);
      const r = await removePeopleAction(Array.from(people));
      if (!r.ok) return setMessage({ ok: false, text: r.error });
      setPeople(new Set());
      setMessage({ ok: true, text: `Removed ${r.value.removed} ${r.value.removed === 1 ? "person" : "people"}. They can no longer sign in.` });
      router.refresh();
    });
  };
  const restorePerson = (id: string) =>
    start(async () => {
      setMessage(null);
      const r = await restorePeopleAction([id]);
      if (!r.ok) return setMessage({ ok: false, text: r.error });
      setMessage({ ok: true, text: "Restored. They can sign in again; give them their clients." });
      router.refresh();
    });

  return (
    <div className="space-y-4">
      <p className="text-sm text-[var(--text-secondary)]">
        Choose the people, choose the clients, then give or remove access. One person and one client is a single change. An admin sees every client, so there is nothing to give. To take someone out of the tool entirely, choose them and use Remove from Organic IQ. Someone who has not signed in yet can be added with Add a team member, so you can give them clients first.
      </p>
      <div className="grid gap-4 lg:grid-cols-2">
        <section className={`${box} p-4`} aria-label="People">
          <div className="flex items-center justify-between gap-2">
            <h2 className="font-bold">People <span className="font-normal text-[var(--text-tertiary)]">· {people.size} chosen</span></h2>
            <div className="flex items-center gap-3">
              <button type="button" onClick={() => setAdding((a) => !a)} aria-expanded={adding} className="text-xs font-semibold text-[var(--brand-teal)] hover:underline">{adding ? "Cancel" : "Add a team member"}</button>
              <button type="button" onClick={() => setPeople(allPeople ? new Set() : new Set(shownPeople.map((u) => u.id)))} className="text-xs font-semibold underline">{allPeople ? "Clear" : "Choose all shown"}</button>
            </div>
          </div>
          {adding ? (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                addPerson();
              }}
              className="mt-3 space-y-2 rounded-lg border border-[var(--border)] bg-[var(--bg)] p-3"
            >
              <input type="email" required value={newEmail} onChange={(e) => setNewEmail(e.target.value)} placeholder="Work email, e.g. name@smamarketing.com" aria-label="Work email" className="w-full rounded-lg border border-[var(--border)] bg-white px-3 py-2 text-sm" />
              <input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="Name (optional)" aria-label="Name" className="w-full rounded-lg border border-[var(--border)] bg-white px-3 py-2 text-sm" />
              <div className="flex flex-wrap items-center gap-3">
                <select value={newRole} onChange={(e) => setNewRole(e.target.value as "sma_team" | "sma_admin")} aria-label="Role" className="rounded-lg border border-[var(--border)] bg-white px-3 py-2 text-sm">
                  <option value="sma_team">Team member</option>
                  <option value="sma_admin">Admin (sees every client)</option>
                </select>
                <button type="submit" disabled={pending || !newEmail.trim()} className="rounded-lg bg-[#00a99d] px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60">{pending ? <><Spinner />Adding…</> : "Add"}</button>
              </div>
              <p className="text-xs text-[var(--text-secondary)]">They sign in with their own Google account on this address. Nothing is sent to them.</p>
            </form>
          ) : null}
          <input value={pq} onChange={(e) => setPq(e.target.value)} placeholder="Find a person" aria-label="Find a person" className="mt-2 w-full rounded-lg border border-[var(--border)] bg-white px-3 py-2 text-sm" />
          <ul className="mt-2 max-h-96 divide-y divide-[var(--border)] overflow-y-auto text-sm">
            {shownPeople.map((u) => (
              <li key={u.id}>
                <label className="flex cursor-pointer items-center gap-3 py-2">
                  <input type="checkbox" checked={people.has(u.id)} onChange={() => setPeople(toggle(people, u.id))} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">{u.name || u.email}</span>
                    {u.name ? <span className="block truncate text-xs text-[var(--text-secondary)]">{u.email}</span> : null}
                  </span>
                  <span className="rounded-full bg-[var(--bg)] px-2 py-0.5 text-xs font-semibold text-[var(--text-secondary)]">{ROLE[u.role] ?? u.role}</span>
                  <span className="w-24 text-right text-xs text-[var(--text-tertiary)]">{u.sees_all ? "all clients" : `${u.client_ids.length} ${u.client_ids.length === 1 ? "client" : "clients"}`}</span>
                </label>
              </li>
            ))}
            {shownPeople.length === 0 ? <li className="py-3 text-[var(--text-secondary)]">No one matches.</li> : null}
          </ul>
          {removed.length ? (
            <details className="mt-3 text-sm">
              <summary className="cursor-pointer text-xs font-semibold">Removed ({removed.length})</summary>
              <ul className="mt-1 divide-y divide-[var(--border)]">
                {removed.map((u) => (
                  <li key={u.id} className="flex items-center gap-3 py-2">
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[var(--text-secondary)]">{u.name || u.email}</span>
                      {u.name ? <span className="block truncate text-xs text-[var(--text-tertiary)]">{u.email}</span> : null}
                    </span>
                    <button type="button" disabled={pending} onClick={() => restorePerson(u.id)} className="rounded-lg border border-[var(--border)] bg-white px-3 py-1 text-xs font-semibold disabled:opacity-50">Restore</button>
                  </li>
                ))}
              </ul>
            </details>
          ) : null}
        </section>

        <section className={`${box} p-4`} aria-label="Clients">
          <div className="flex items-center justify-between gap-2">
            <h2 className="font-bold">Clients <span className="font-normal text-[var(--text-tertiary)]">· {clients.size} chosen</span></h2>
            <button type="button" onClick={() => setClients(allClients ? new Set() : new Set(shownClients.map((c) => c.id)))} className="text-xs font-semibold underline">{allClients ? "Clear" : "Choose all shown"}</button>
          </div>
          <input value={cq} onChange={(e) => setCq(e.target.value)} placeholder="Find a client" aria-label="Find a client" className="mt-2 w-full rounded-lg border border-[var(--border)] bg-white px-3 py-2 text-sm" />
          <ul className="mt-2 max-h-96 divide-y divide-[var(--border)] overflow-y-auto text-sm">
            {shownClients.map((c) => {
              const have = accessOf(c.id);
              return (
                <li key={c.id}>
                  <label className="flex cursor-pointer items-center gap-3 py-2">
                    <input type="checkbox" checked={clients.has(c.id)} onChange={() => setClients(toggle(clients, c.id))} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-medium">{c.name}</span>
                      <span className="block truncate text-xs text-[var(--text-secondary)]">{c.domain}</span>
                    </span>
                    {needy.length > 0 ? (
                      <span className={`text-xs ${have === needy.length ? "font-semibold text-green-700" : "text-[var(--text-tertiary)]"}`}>{have === needy.length ? "has access" : have ? `${have} of ${needy.length} have it` : "no access yet"}</span>
                    ) : null}
                  </label>
                </li>
              );
            })}
            {shownClients.length === 0 ? <li className="py-3 text-[var(--text-secondary)]">No client matches.</li> : null}
          </ul>
        </section>
      </div>

      <div className={`${box} flex flex-wrap items-center gap-3 p-4`}>
        <p className="text-sm">{ready ? <><strong>{people.size}</strong> {people.size === 1 ? "person" : "people"} on <strong>{clients.size}</strong> {clients.size === 1 ? "client" : "clients"}</> : "Choose at least one person and one client."}</p>
        <div className="ml-auto flex flex-wrap gap-2">
          <button type="button" onClick={removePeople} disabled={pending || people.size === 0} title="Take the chosen people out of Organic IQ" className="rounded-lg border border-red-200 bg-white px-4 py-2 text-sm font-semibold text-red-700 disabled:cursor-not-allowed disabled:opacity-50">Remove from Organic IQ</button>
          <button type="button" onClick={() => run("remove")} disabled={pending || !ready} className="rounded-lg border border-[var(--border)] bg-white px-4 py-2 text-sm font-semibold text-red-700 disabled:cursor-not-allowed disabled:opacity-50">Remove access</button>
          <button type="button" onClick={() => run("give")} disabled={pending || !ready} className="rounded-lg bg-[#00a99d] px-4 py-2 text-sm font-semibold text-white hover:bg-[var(--brand-teal-hover)] disabled:cursor-not-allowed disabled:opacity-60">{pending ? <><Spinner />Saving…</> : "Give access"}</button>
        </div>
      </div>
      {message ? <p role={message.ok ? "status" : "alert"} className={`rounded-lg p-3 text-sm ${message.ok ? "bg-green-50 text-green-800" : "bg-red-50 text-red-800"}`}>{message.text}</p> : null}
    </div>
  );
}
