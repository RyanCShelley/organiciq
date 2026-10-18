export const ACTION_FAMILIES: Record<string, string> = {
  priority_page: "Improve or recover a priority page",
  ai_answers: "Improve AI answers and citations",
  internal_links: "Strengthen internal links",
  conversion_path: "Improve conversion path",
  structured_data: "Add or repair relevant structured data",
  investigation: "Investigate a material change",
};

export type Brief = {
  action_uid: string; id: string; family: string; title: string;
  branch: string; target_url: string; term: string | null;
  why: string; done_when: string; steps: string[]; evidence: string[];
  finding_ids: string[]; effort_min: number; metric: string;
  metric_key: string; check_after_days: number; check_on?: string | null;
  score?: number; flags?: string[];
};

export type PlanReview = {
  revision: number; strategy: string; focus: string; reason: string; items: Brief[];
  approved_at: string | null; approved_by: string | null;
  versions: { revision: number; approved_at: string; approved_by: string }[];
  proposals: Brief[]; capacity: number; suggested_focus: string;
  setup_findings: { title: string; why: string; target_url: string }[];
};

export function samePage(left: string, right: string): boolean {
  const key = (value: string) => { try { const url = new URL(value); return `${url.hostname.replace(/^www\./, "")}${url.pathname.replace(/\/$/, "")}`.toLowerCase(); } catch { return value; } };
  return Boolean(left && right && key(left) === key(right));
}

export function includesProposal(selected: Brief, proposal: Brief): boolean {
  return samePage(selected.target_url, proposal.target_url)
    && proposal.steps.every(step => selected.steps.includes(step));
}

export const actionCount = (items: { steps?: string[] }[]) => items.reduce((n, item) => n + Math.max(1, item.steps?.filter(s => s.trim()).length ?? 0), 0);

/** One selectable intervention, with its own assignment and Teamwork identity. */
export function individualAction(group: Brief, step: string, index: number): Brief {
  return { ...group, action_uid: `${group.action_uid.slice(0, 105)}-task-${index}`,
    title: step.length > 150 ? `${step.slice(0, 147)}…` : step,
    steps: [step], done_when: step,
    effort_min: Math.max(5, Math.ceil(group.effort_min / Math.max(1, group.steps.length))),
  };
}

export function selectedAction(items: Brief[], group: Brief, step: string): Brief | undefined {
  return items.find(item => samePage(item.target_url, group.target_url) && item.steps.includes(step));
}

export function toggleAction(items: Brief[], group: Brief, step: string, index: number, lockedUids: string[] = []): Brief[] {
  const existing = selectedAction(items, group, step);
  if (existing && lockedUids.includes(existing.action_uid)) return items;
  // Editing creates individual delivery identities for every editable legacy
  // bundle. Already assigned/delivered work keeps its scope and identity.
  const individual = items.flatMap(item => item.steps.length > 1 && !lockedUids.includes(item.action_uid)
    ? item.steps.map((s, i) => individualAction(item, s, i)) : [item]);
  const selected = selectedAction(individual, group, step);
  if (selected) return individual.filter(item => item !== selected);
  return [...individual, individualAction(group, step, index)];
}

export function mergeBrief(current: Brief, incoming: Brief): Brief {
  if (includesProposal(current, incoming)) return current;
  const union = (a: string[], b: string[]) => [...new Set([...a, ...b].filter(x => x.trim()))];
  return { ...current,
    steps: union(current.steps, incoming.steps), evidence: union(current.evidence, incoming.evidence),
    finding_ids: union(current.finding_ids, incoming.finding_ids),
    why: current.why === incoming.why ? current.why : `${current.why}\n\n${incoming.why}`,
    done_when: current.done_when === incoming.done_when ? current.done_when : `${current.done_when}\n\n${incoming.done_when}`,
    effort_min: Math.min(180, current.effort_min + incoming.effort_min),
  };
}

export function suggestedPlan(proposals: Brief[], focus: string, capacity: number): Brief[] {
  const focused = proposals.filter(x => x.branch === focus);
  const pool = focused.length ? focused : proposals;
  const selected: Brief[] = [];
  for (const item of pool) {
    for (const [index, step] of item.steps.entries()) {
      if (actionCount(selected) >= capacity) break;
      if (!selectedAction(selected, item, step)) selected.push(individualAction(item, step, index));
    }
  }
  return selected;
}
