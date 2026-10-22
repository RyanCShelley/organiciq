"use client";
import { useState } from "react";

export function CompetitorDomainsField({ initial }: { initial: string[] }) {
  const [domains, setDomains] = useState(initial);
  const [candidate, setCandidate] = useState("");
  const [error, setError] = useState<string | null>(null);
  function add() {
    try {
      const url = new URL(/^https?:\/\//i.test(candidate) ? candidate.trim() : `https://${candidate.trim()}`);
      const domain = url.hostname.toLowerCase().replace(/^www\./, "");
      if (!domain.includes(".") || url.username || url.password) throw new Error();
      if (domains.includes(domain)) { setError("This competitor is already listed."); return; }
      if (domains.length >= 3) { setError("This client supports up to three competitors."); return; }
      setDomains([...domains, domain]); setCandidate(""); setError(null);
    } catch { setError("Enter a valid competitor domain, such as example.com."); }
  }
  return <div className="space-y-4">
    <input type="hidden" name="competitor_domains" value={domains.join("\n")} />
    <p className="text-sm text-[var(--text-secondary)]">Select the sites competing for this client’s customers. Up to three domains; saved changes apply to future competitor analysis.</p>
    <div className="flex flex-wrap gap-3">
      <label className="flex-1 text-sm">Competitor domain<input className="input mt-1 w-full" value={candidate} onChange={e => setCandidate(e.target.value)} placeholder="competitor.com" onKeyDown={e => { if (e.key === "Enter") { e.preventDefault(); add(); } }} /></label>
      <button type="button" className="btn btn-secondary self-end" onClick={add} disabled={domains.length >= 3}>Add domain</button>
    </div>
    {error ? <p role="alert" className="text-sm text-red-700">{error}</p> : null}
    <ul className="divide-y divide-[var(--border)]">{domains.map(domain => <li key={domain} className="flex items-center justify-between gap-4 py-3"><span>{domain}</span><button type="button" className="btn btn-ghost btn-sm" aria-label={`Remove ${domain}`} onClick={() => setDomains(domains.filter(d => d !== domain))}>Remove</button></li>)}</ul>
    {!domains.length ? <p className="text-sm text-[var(--text-secondary)]">No competitors selected.</p> : null}
    <p className="text-xs text-[var(--text-secondary)]">Use Save changes to apply additions or removals.</p>
  </div>;
}
