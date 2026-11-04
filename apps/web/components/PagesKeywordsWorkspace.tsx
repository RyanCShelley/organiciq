"use client";
import { useState } from "react";
import { KeywordPageMapTable, type KeywordMapRow } from "@/components/DecisionEngine/KeywordPageMapTable";
import { PageStagesPanel, type PageStagePayload } from "@/components/PageStagesPanel";
import type { ConversionPage } from "@/components/ConversionPagesPanel";
import { Alert } from "@/components/ui/Alert";
export function PagesKeywordsWorkspace({ clientId, slug, keywords, pages, stages, conversions, errors }: { clientId: string; slug: string; keywords: KeywordMapRow[]; pages: string[]; stages: PageStagePayload | null; conversions: ConversionPage[]; errors: string[] }) {
  const [view, setView] = useState<"pages" | "keywords">("pages");
  const [query, setQuery] = useState("");
  return <div className="space-y-5"><div><h2 className="section-title">Pages & Keywords</h2><p className="section-description">Page ownership, funnel stages and declared conversion destinations in one workspace. Review unresolved matches and preserve your overrides.</p></div>
    {errors.map(error => <Alert variant="warning" key={error}>{error}</Alert>)}
    <div role="group" aria-label="Mapping view" className="flex flex-wrap gap-2"><button className={`btn ${view === "pages" ? "btn-primary" : "btn-secondary"}`} onClick={() => setView("pages")}>By page</button><button className={`btn ${view === "keywords" ? "btn-primary" : "btn-secondary"}`} onClick={() => setView("keywords")}>By keyword</button></div>
    {view === "pages" ? stages ? <div className="workspace-panel"><PageStagesPanel clientId={clientId} initial={stages} keywords={keywords} conversions={conversions} onEditKeywords={url => { setQuery(url); setView("keywords"); }} /></div> : <Alert variant="warning">Page stages could not be loaded. Keyword ownership is available in By keyword.</Alert> : <KeywordPageMapTable key={query} rows={keywords} pages={pages} clientId={clientId} clientSlug={slug} initialSearch={query} />}
  </div>;
}
