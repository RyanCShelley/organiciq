"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { SearchableSelect } from "@/components/SearchableSelect";

type Project = {
  site_id: string;
  title: string;
  url?: string | null;
};

export function SeRankingConnectPanel({
  clientId,
  connected,
  propertyId,
  projectName,
}: {
  clientId: string;
  connected: boolean;
  propertyId: string | null;
  projectName: string | null;
}) {
  const router = useRouter();
  const [projects, setProjects] = useState<Project[]>([]);
  const [selected, setSelected] = useState(propertyId ?? "");
  const [message, setMessage] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const projectOptions = useMemo(
    () =>
      projects.map((p) => ({
        value: p.site_id,
        label: `${p.title}${p.url ? ` (${p.url})` : ""} — ${p.site_id}`,
      })),
    [projects],
  );

  async function loadProjects() {
    setPending(true);
    setMessage(null);
    const res = await fetch(`/api/proxy/seranking/projects?clientId=${encodeURIComponent(clientId)}`);
    const data = await res.json();
    setPending(false);
    if (!res.ok) {
      setMessage(typeof data.detail === "string" ? data.detail : "Failed to list SE Ranking projects");
      return;
    }
    setProjects(data);
  }

  async function saveProperty() {
    if (!selected) return;
    setPending(true);
    setMessage(null);
    const project = projects.find((p) => p.site_id === selected);
    const res = await fetch(`/api/proxy/seranking/property`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        clientId,
        site_id: selected,
        project_name: project?.title,
      }),
    });
    const text = await res.text();
    setPending(false);
    if (!res.ok) {
      setMessage(text || "Failed to save project");
      return;
    }
    setMessage("SE Ranking project saved — use Sync 90 days below to pull data.");
    router.refresh();
  }

  return (
    <div className="mt-6 rounded-xl border border-[var(--border)] bg-[var(--card)] p-4">
      <h2 className="text-lg font-medium">SE Ranking</h2>
      <p className="mt-1 text-sm text-[var(--muted)]">
        Uses the account API key. Map this client&apos;s project (Search + AI + Audit sync together).
      </p>

      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          disabled={pending}
          onClick={loadProjects}
          className="btn btn-primary btn-sm disabled:opacity-50"
        >
          {propertyId ? "Change project" : "Load projects"}
        </button>
      </div>

      {projects.length > 0 ? (
        <div className="mt-4 flex flex-wrap items-end gap-3">
          <SearchableSelect
            label="SE Ranking project"
            options={projectOptions}
            value={selected}
            onChange={setSelected}
            searchPlaceholder="Search projects…"
          />
          <button
            type="button"
            disabled={pending || !selected}
            onClick={saveProperty}
            className="btn btn-primary btn-sm disabled:opacity-50"
          >
            Save project
          </button>
        </div>
      ) : null}

      {propertyId ? (
        <p className="mt-3 text-sm text-[var(--muted)]">
          Connected project: {projectName ? `${projectName} / ` : ""}
          {propertyId}
        </p>
      ) : null}
      {message ? <p className="mt-3 text-sm text-[var(--muted)]">{message}</p> : null}
    </div>
  );
}
