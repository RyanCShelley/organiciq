/**
 * The saved monthly record, as the engine writes it.
 *
 * Mirrors `schema/monthly-record.schema.json`. The page renders this and
 * recomputes nothing: a run is a thing that happened on a date with the data
 * it had, and two months of it are two decisions rather than two
 * recalculations.
 */

export type TestStatus = "pass" | "fail" | "blocked";

export type BranchTest = {
  id: string;
  name: string;
  metric_label: string;
  value: number | null;
  pass_line: number;
  direction: "min" | "max";
  unit: "pct" | "chg" | "count";
  status: TestStatus;
  display?: string;
  missing?: string;
};

export type BranchResult = {
  branch: "visibility" | "traffic" | "leads";
  status: TestStatus;
  headline_test: string;
  display?: string | null;
  missing?: string[];
  tests: BranchTest[];
};

export type RecordAction = {
  action_uid: string;
  slot: number;
  id: string;
  title: string;
  branch: string;
  spillover: boolean;
  target_url: string;
  term: string | null;
  score: number;
  effort_min: number;
  why: string;
  evidence?: string[];
  done_when: string;
  /** The job as a checklist, each line built from a fact about this page. */
  steps?: string[];
  metric: string;
  check_on: string;
  flags?: string[];
};

/** Everything the engine weighed, slotted or not. */
export type Candidate = RecordAction & {
  /** Null when the engine left it out; the reason says why. */
  slot: number | null;
  not_slotted_because: string | null;
};

export type MonthlyRecord = {
  client: string;
  client_name?: string;
  domain?: string;
  month: string;
  run_saved_at: string;
  data_through: string | null;
  plan: string;
  action_slots: number;
  constraint: string;
  reason_text: string;
  override?: string | null;
  /** What the tests produced, when a person overrode it. */
  engine_constraint?: string;
  override_reason?: string;
  held_since: string;
  confidence: "high" | "medium" | "low";
  confidence_reasons?: { code: string; text: string }[];
  branches: BranchResult[];
  actions: RecordAction[];
  empty_slots: { slot: number; reason: string }[];
  incidents: {
    incident_uid: string;
    title: string;
    scope: string;
    detail?: string;
    evidence?: string[];
    effort_min?: number;
  }[];
  not_this_month: {
    id?: string;
    title?: string;
    branch?: string;
    branch_status?: TestStatus;
    target_url?: string;
    reason?: string;
  }[];
  candidates?: Candidate[];
  /** Retainer work: refreshing existing content, against update_allowance.
   *  Kept apart from `actions` because growth actions are outside the
   *  monthly fee and these are inside it. */
  updates?: RecordAction[];
  update_slots?: number;
  empty_update_slots?: { slot: number; reason: string }[];
  update_candidates?: Candidate[];
  /** New pages, against content_allowance. No URL yet: a term is the identity. */
  new_content?: RecordAction[];
  content_slots?: number;
  empty_content_slots?: { slot: number; reason: string }[];
  content_candidates?: Candidate[];
  /** What the gap scan checked, so an empty pool can say what it looked at. */
  content_scan?: {
    tracked?: number;
    mapped?: number;
    covered?: number;
    ranking?: number;
    brand?: number;
    no_metrics?: number;
    small?: number;
    gaps?: number;
    pages_searched?: number;
    blocked?: string;
  };
  data_gaps: { input: string; status: string }[];
  previous_results: {
    /** Which pool the action came from. Absent on records saved before the
     *  retainer pools existed, which were all growth actions. */
    kind?: "action" | "update" | "content";
    action_uid?: string;
    title?: string;
    target_url?: string;
    metric?: string;
    before?: number | null;
    after?: number | null;
    result?: "improved" | "no_change" | "worse" | "waiting";
    check_on?: string;
    /** Somebody recorded shipping it. Without this the verdict is about the
     *  metric, not about the work. */
    shipped?: boolean;
    skipped?: boolean;
  }[];
  excluded_pages?: { url_pattern: string; reason: string }[];
  excluded_targets?: { keyword: string; target_url: string; reason: string }[];
};

export type RunSummary = {
  month: string;
  run_saved_at: string | null;
  data_through: string | null;
  constraint: string;
  confidence: string;
};

export const BRANCH_LABEL: Record<string, string> = {
  visibility: "Visibility",
  traffic: "Traffic",
  leads: "Leads",
};

export const CONSTRAINT_LABEL: Record<string, string> = {
  visibility: "Visibility",
  traffic: "Traffic",
  leads: "Leads",
  visibility_expansion: "Visibility expansion",
  withheld: "Withheld",
};

/** "October 2026" from "2026-10". */
export function monthName(month: string): string {
  const [year, m] = month.split("-").map(Number);
  if (!year || !m) return month;
  return new Date(Date.UTC(year, m - 1, 1)).toLocaleDateString("en-US", {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
}

export function formatDay(iso: string | null | undefined): string {
  if (!iso) return "—";
  const parsed = new Date(`${iso.slice(0, 10)}T00:00:00Z`);
  return Number.isNaN(parsed.getTime())
    ? iso
    : parsed.toLocaleDateString("en-US", { day: "numeric", month: "short", timeZone: "UTC" });
}

/**
 * A test's value in the unit the reader recognises.
 *
 * The old screen normalised everything to a ratio and could only say "43% of
 * a 30% bar", which is not a metric anyone knows. `display` wins when the
 * engine wrote one — "4 of 50 leads" beats "8%".
 */
export function testValue(test: BranchTest): string {
  if (test.display) return test.display;
  if (test.value === null) return "—";
  if (test.unit === "count") return Math.round(test.value).toLocaleString();
  return `${Math.round(test.value)}%`;
}

export function passLine(test: BranchTest): string {
  const bar = test.unit === "count" ? `${test.pass_line}` : `${test.pass_line}%`;
  return test.direction === "min" ? `pass at ${bar} or more` : `pass at ${bar} or less`;
}

/** How many months a constraint has been held, inclusive of this one. */
export function monthsHeld(heldSince: string, month: string): number {
  const [hy, hm] = heldSince.split("-").map(Number);
  const [my, mm] = month.split("-").map(Number);
  if (!hy || !hm || !my || !mm) return 1;
  return Math.max(1, (my - hy) * 12 + (mm - hm) + 1);
}

/** Who can be given work on this client. */
/** Somebody who can be given work — from Teamwork where it is connected. */
export type Assignee = {
  email: string;
  name: string | null;
  source?: "teamwork" | "organiciq";
};

/**
 * What the team did about one slot.
 *
 * Served apart from the record, because assigning a task must not rewrite
 * what the engine decided.
 */
export type SlotState = {
  uid: string;
  status: "planned" | "assigned" | "done" | "skipped";
  assignee_email: string | null;
  assignee_name: string | null;
  due: string | null;
  skip_reason: string | null;
  /** A person put it in the plan or took it out. Null defers to the engine. */
  in_plan: boolean | null;
  in_plan_reason: string | null;
  sent_at: string | null;
  /** The day the work went live. The results loop reads this. */
  shipped_on: string | null;
  teamwork_task_id: string | null;
  teamwork_task_url: string | null;
  assigned_action_id: string | null;
  /** The slot holds a different action now from the one that was assigned. */
  stale: boolean;
};

export type Workflow = {
  month: string;
  teamwork_ready: boolean;
  actions: SlotState[];
};
