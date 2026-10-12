"use client";

import { useEffect, useState } from "react";

import { FieldLabel, Input, Select } from "@/components/ui/Input";

type TaskList = {
  id: string;
  name: string;
  project_id: string | null;
  project_name: string | null;
};

type Payload = {
  configured: boolean;
  tasklists: TaskList[];
  error: string | null;
};

/**
 * Where this client's sent growth actions land.
 *
 * A list rather than a box to type an id into: an id read off a URL is how a
 * task ends up in the wrong client's list, and nothing downstream would
 * catch it. Grouped by project, because "Content" means nothing on its own
 * when nine clients each have one.
 *
 * It degrades to the id box whenever the list cannot be fetched — no
 * credentials yet, or Teamwork refusing — so a saved id is never stranded
 * behind a dropdown that will not load.
 */
export function TeamworkTasklistField({ value }: { value: string | null }) {
  const [data, setData] = useState<Payload | null>(null);
  const [failed, setFailed] = useState(false);
  const [chosen, setChosen] = useState(value ?? "");

  // `useState` reads the prop once. Saving revalidates the page and the
  // server sends the new value down, but React keeps this instance, so the
  // select went on showing "Not set" after a save that had worked — and
  // came right only on a full reload.
  useEffect(() => {
    setChosen(value ?? "");
  }, [value]);

  useEffect(() => {
    let live = true;
    fetch("/api/proxy/teamwork-tasklists")
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error("failed"))))
      .then((body: Payload) => live && setData(body))
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, []);

  const byProject = new Map<string, TaskList[]>();
  for (const row of data?.tasklists ?? []) {
    const key = row.project_name ?? "Other";
    byProject.set(key, [...(byProject.get(key) ?? []), row]);
  }

  // The saved id may not be in the list — a completed project, or a token
  // that cannot see it. Keeping it as an option stops a save silently
  // clearing it.
  const known = (data?.tasklists ?? []).some((row) => row.id === chosen);

  if (failed || (data && !data.configured) || (data && data.error)) {
    return (
      <div className="flex flex-col gap-1">
        <FieldLabel label="Teamwork tasklist ID">
          <Input
            name="teamwork_tasklist_id"
            inputMode="numeric"
            defaultValue={value ?? ""}
            placeholder="e.g. 2859633"
          />
        </FieldLabel>
        <p className="text-xs text-[var(--text-tertiary)]">
          {data?.error
            ? data.error
            : data && !data.configured
              ? "Teamwork is not connected, so there is no list to choose from. Set TEAMWORK_SITE and TEAMWORK_API_TOKEN, or paste the id from the tasklist's URL."
              : "Could not reach Teamwork, so paste the id from the tasklist's URL."}
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-1">
      <FieldLabel label="Teamwork tasklist">
        <Select
          name="teamwork_tasklist_id"
          value={chosen}
          disabled={!data}
          onChange={(e) => setChosen(e.target.value)}
        >
          <option value="">
            {data ? "Not set — slot cards offer Copy" : "Loading…"}
          </option>
          {chosen && data && !known ? (
            <option value={chosen}>Saved list ({chosen})</option>
          ) : null}
          {[...byProject.entries()].map(([project, lists]) => (
            <optgroup key={project} label={project}>
              {lists.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.name}
                </option>
              ))}
            </optgroup>
          ))}
        </Select>
      </FieldLabel>
      <p className="text-xs text-[var(--text-tertiary)]">
        Where sent growth actions land. Leave it unset and slot cards offer
        Copy instead of Send.
      </p>
    </div>
  );
}
