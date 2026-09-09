"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { SearchableSelect } from "@/components/SearchableSelect";
import { syncJobWindow } from "@/lib/dates";

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
    setMessage("SE Ranking project saved");
    router.refresh();
  }

  async function syncDays(
    source: "se_ranking_search" | "se_ranking_ai" | "se_ranking_audit",
    days: number,
  ) {
    setPending(true);
    setMessage(null);
    const res = await fetch("/api/proxy/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        clientId,
        source,
        ...syncJobWindow(days),
      }),
    });
    if (!res.ok) {
      setPending(false);
      setMessage(await res.text());
      return;
    }
    setPending(false);
    setMessage(`Enqueued ${source} (${days} days)`);
    router.refresh();
  }

  return (
    <div className="mt-6 rounded-xl border border-[var(--border)] bg-[var(--card)] p-4">
      <h2 className="text-lg font-medium">SE Ranking</h2>
      <p className="mt-1 text-sm text-[var(--muted)]">
        Uses account API key (<code className="text-xs">SE_RANKING_API_KEY</code>). Map a project,
        then sync Search or AI visibility into the Watch List.
      </p>

      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          disabled={pending}
          onClick={loadProjects}
          className="btn btn-primary btn-sm disabled:opacity-50"
        >
          Load projects
        </button>
        <button
          type="button"
          disabled={pending || !propertyId}
          onClick={() => syncDays("se_ranking_search", 14)}
          className="rounded-lg border border-[var(--border)] px-4 py-2 text-sm disabled:opacity-50"
        >
          Sync Search 14 days
        </button>
        <button
          type="button"
          disabled={pending || !propertyId}
          onClick={() => syncDays("se_ranking_search", 90)}
          className="rounded-lg border border-[var(--border)] px-4 py-2 text-sm disabled:opacity-50"
        >
          Sync Search 90 days
        </button>
        <button
          type="button"
          disabled={pending || !propertyId}
          onClick={() => syncDays("se_ranking_ai", 14)}
          className="rounded-lg border border-[var(--border)] px-4 py-2 text-sm disabled:opacity-50"
        >
          Sync AI 14 days
        </button>
        <button
          type="button"
          disabled={pending || !propertyId}
          onClick={() => syncDays("se_ranking_ai", 90)}
          className="rounded-lg border border-[var(--border)] px-4 py-2 text-sm disabled:opacity-50"
        >
          Sync AI 90 days
        </button>
        <button
          type="button"
          disabled={pending || !propertyId}
          onClick={() => syncDays("se_ranking_audit", 1)}
          className="rounded-lg border border-[var(--border)] px-4 py-2 text-sm disabled:opacity-50"
        >
          Sync Website Audit
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
          Selected project: {projectName ? `${projectName} / ` : ""}
          {propertyId}
          {connected ? "" : " (not marked connected)"}
        </p>
      ) : null}
      {message ? <p className="mt-3 text-sm text-[var(--muted)]">{message}</p> : null}
    </div>
  );
}
