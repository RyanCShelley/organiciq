export type DashboardPeriodMetric = {
  current: number | null;
  previous: number | null;
  change_pct: number | null;
};

export function emptyPeriodMetric(): DashboardPeriodMetric {
  return { current: null, previous: null, change_pct: null };
}

function periodMetric(value: unknown): DashboardPeriodMetric {
  if (!value || typeof value !== "object") return emptyPeriodMetric();
  const metric = value as Partial<DashboardPeriodMetric>;
  return {
    current: typeof metric.current === "number" ? metric.current : null,
    previous: typeof metric.previous === "number" ? metric.previous : null,
    change_pct: typeof metric.change_pct === "number" ? metric.change_pct : null,
  };
}

export function normalizeDashboardResponse(payload: unknown): DashboardResponse {
  const data = (payload ?? {}) as Partial<DashboardResponse>;
  const search = data.visibility?.search;
  const ai = data.visibility?.ai as Record<string, unknown> | undefined;
  const conversions = data.conversions;
  const traffic = data.traffic;

  return {
    period: data.period ?? {
      from: "",
      to: "",
      previous_from: "",
      previous_to: "",
    },
    freshness: Array.isArray(data.freshness) ? data.freshness : [],
    conversions: {
      configured: conversions?.configured === true,
      lead_events: Array.isArray(conversions?.lead_events) ? conversions.lead_events : [],
      leads: periodMetric(conversions?.leads),
      lead_rate: periodMetric(conversions?.lead_rate),
      leads_by_channel: Array.isArray(conversions?.leads_by_channel)
        ? conversions.leads_by_channel
        : [],
      monthly_lead_goal:
        typeof conversions?.monthly_lead_goal === "number" ? conversions.monthly_lead_goal : null,
      period_lead_goal:
        typeof conversions?.period_lead_goal === "number" ? conversions.period_lead_goal : null,
      goal_period_days:
        typeof conversions?.goal_period_days === "number" ? conversions.goal_period_days : null,
      goal_progress_pct:
        typeof conversions?.goal_progress_pct === "number" ? conversions.goal_progress_pct : null,
    },
    visibility: {
      search: {
        search_visibility: periodMetric(search?.search_visibility),
        search_visibility_source: search?.search_visibility_source ?? null,
        search_sov: periodMetric(search?.search_sov),
        search_sov_source: search?.search_sov_source ?? null,
        gsc_impressions: periodMetric(search?.gsc_impressions),
        average_position: periodMetric(search?.average_position),
        average_position_source: search?.average_position_source ?? "gsc_pages",
        keyword_distribution: search?.keyword_distribution ?? {
          top_3: 0,
          top_10: 0,
          top_20: 0,
          beyond_20: 0,
          not_ranking: 0,
        },
      },
      ai: {
        mention_presence: periodMetric(ai?.mention_presence),
        link_presence: periodMetric(ai?.link_presence),
        mention_top3_presence: periodMetric(ai?.mention_top3_presence),
        link_top3_presence: periodMetric(ai?.link_top3_presence),
        prompt_count: typeof ai?.prompt_count === "number" ? ai.prompt_count : null,
        tracked_prompt_source:
          typeof ai?.tracked_prompt_source === "string" ? ai.tracked_prompt_source : null,
      },
    },
    traffic: {
      gsc_clicks: periodMetric(traffic?.gsc_clicks),
      gsc_ctr: periodMetric(traffic?.gsc_ctr),
      ga4_sessions: periodMetric(traffic?.ga4_sessions),
      ga4_views: periodMetric(traffic?.ga4_views),
      by_channel: Array.isArray(traffic?.by_channel) ? traffic.by_channel : [],
      top_pages: Array.isArray(traffic?.top_pages) ? traffic.top_pages : [],
    },
  };
}

export type DashboardFreshness = {
  source: string;
  fact_through: string | null;
  validation: string | null;
  available: boolean;
};

export type DashboardResponse = {
  period: {
    from: string;
    to: string;
    previous_from: string;
    previous_to: string;
  };
  freshness: DashboardFreshness[];
  conversions: {
    configured: boolean;
    lead_events: string[];
    leads: DashboardPeriodMetric;
    lead_rate: DashboardPeriodMetric;
    leads_by_channel: { channel: string; label: string; leads: number }[];
    monthly_lead_goal: number | null;
    period_lead_goal: number | null;
    goal_period_days: number | null;
    goal_progress_pct: number | null;
  };
  visibility: {
    search: {
      search_visibility: DashboardPeriodMetric;
      search_visibility_source: string | null;
      search_sov: DashboardPeriodMetric;
      search_sov_source: string | null;
      gsc_impressions: DashboardPeriodMetric;
      average_position: DashboardPeriodMetric;
      average_position_source: string;
      keyword_distribution: {
        top_3: number;
        top_10: number;
        top_20: number;
        beyond_20: number;
        not_ranking: number;
      };
    };
    ai: {
      mention_presence: DashboardPeriodMetric;
      link_presence: DashboardPeriodMetric;
      mention_top3_presence: DashboardPeriodMetric;
      link_top3_presence: DashboardPeriodMetric;
      prompt_count: number | null;
      tracked_prompt_source: string | null;
    };
  };
  traffic: {
    gsc_clicks: DashboardPeriodMetric;
    gsc_ctr: DashboardPeriodMetric;
    ga4_sessions: DashboardPeriodMetric;
    ga4_views: DashboardPeriodMetric;
    by_channel: { channel: string; label: string; sessions: number; views: number }[];
    top_pages: {
      page: string;
      gsc_impressions: number;
      gsc_clicks: number;
      ga4_sessions: number;
      ga4_views: number;
    }[];
  };
};
