import type { Finding } from "@/lib/decision-engine";

/** The stable thing a finding is, for grouping. */
function signalOf(finding: Finding): string {
  const evidence = finding.evidence_json ?? {};
  const signal = evidence.audit_signal ?? evidence.gate;
  return typeof signal === "string" && signal ? signal : finding.lever;
}

/** The engine's own sentence, with the per-item detail after it removed. */
function headline(finding: Finding): string {
  return finding.diagnosis.split(/[:—]/)[0].trim() || finding.diagnosis;
}

/**
 * The wording for a group of findings of the same kind.
 *
 * Grouping is on the signal, which is stable; this only has to name the
 * row, and it uses the engine's own sentence so the label cannot drift
 * from what the rule says.
 *
 * Some sentences carry a number — "Under-linked page ranking 16" is one
 * problem across six pages, each with its own position. Those are merged
 * by dropping the trailing figure, but only when the group actually
 * disagrees: doing it unconditionally turned "Keyword fell out of the top
 * 5" into "Keyword fell out of the top".
 */
function labelFor(items: Finding[]): string {
  const heads = items.map(headline);
  const distinct = new Set(heads);
  if (distinct.size === 1) return heads[0];

  const merged = heads.map((text) => text.replace(/\s+-?\d[\d.,%]*\s*$/, "").trim());
  const tally = new Map<string, number>();
  for (const text of merged) tally.set(text, (tally.get(text) ?? 0) + 1);
  const best = [...tally.entries()].sort((a, b) => b[1] - a[1])[0][0];
  return best || heads[0];
}

type Group = { signal: string; label: string; items: Finding[] };

export function groupReported(findings: Finding[]): Group[] {
  const bySignal = new Map<string, Finding[]>();
  for (const finding of findings) {
    const key = signalOf(finding);
    const bucket = bySignal.get(key);
    if (bucket) bucket.push(finding);
    else bySignal.set(key, [finding]);
  }

  return [...bySignal.entries()]
    .map(([signal, items]) => {
      return { signal, label: labelFor(items), items };
    })
    .sort((a, b) => b.items.length - a.items.length);
}

/** Past this a group is a wall of text rather than a list to read. */
const SHOWN_PER_GROUP = 25;

/**
 * What the engine looked at and did not offer.
 *
 * "The remaining 107 are reported rather than offered: nothing there is a
 * separate hour of work" is a claim the reader cannot check, and checking
 * it is the point — ACCTek's hundred turned out to be sixty pages
 * answering HTTP 429, which is rate limiting and not sixty problems with
 * the client's site.
 *
 * It is a summary, not a second ledger. These are not ranked and carry no
 * count, because nothing here was measured as a separate hour of work;
 * putting a number beside them would invite them to be compared with the
 * actions above, which is the screen this one replaced.
 */
export function ReportedFindings({ findings }: { findings: Finding[] }) {
  if (findings.length === 0) return null;
  const groups = groupReported(findings);

  return (
    <details className="mt-4 border-t border-[var(--border)] pt-3">
      <summary className="flex min-h-[44px] cursor-pointer items-center text-[13.5px] font-semibold text-[var(--brand-teal-deep)]">
        See the {findings.length.toLocaleString()} reported, by kind
      </summary>

      <p className="mt-2 max-w-[86ch] text-[13px] leading-relaxed text-[var(--text-tertiary)]">
        Not ranked and not counted: none of these was measured as a separate
        hour of work. They are here so the claim that none of them is can be
        argued with.
      </p>

      <ul className="mt-3 space-y-1.5">
        {groups.map((group) => (
          <li key={group.signal}>
            <details className="rounded-[10px] bg-[var(--surface-muted)] px-4 py-2.5">
              <summary className="flex min-h-[36px] cursor-pointer items-baseline gap-3 text-[13.5px]">
                <span className="min-w-[2.5rem] font-[family-name:var(--font-display)] font-extrabold tabular-nums text-[var(--text-primary)]">
                  {group.items.length}
                </span>
                <span className="min-w-0 flex-1 text-[var(--text-secondary)]">
                  {group.label}
                </span>
              </summary>
              <ul className="mt-2.5 space-y-1 border-t border-[var(--border)] pt-2.5">
                {group.items.slice(0, SHOWN_PER_GROUP).map((item) => (
                  <li
                    key={item.rule_key}
                    className="break-words font-[family-name:var(--font-mono)] text-[11.5px] leading-relaxed text-[var(--text-tertiary)]"
                  >
                    {item.page_url
                      ? item.page_url.replace(/^https?:\/\/[^/]+/, "") || "/"
                      : (item.query ?? item.diagnosis)}
                  </li>
                ))}
                {group.items.length > SHOWN_PER_GROUP ? (
                  <li className="text-[11.5px] text-[var(--text-tertiary)]">
                    and {group.items.length - SHOWN_PER_GROUP} more
                  </li>
                ) : null}
              </ul>
            </details>
          </li>
        ))}
      </ul>
    </details>
  );
}
