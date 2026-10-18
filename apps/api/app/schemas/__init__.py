from typing import Literal
from datetime import date as Date, datetime as DateTime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.urls import public_host_or_error

from app.models.client import ClientStatus
from app.models.config import OrganicChannel, TopicStatus
from app.models.integration import ConnectionStatus, IntegrationProvider
from app.models.job import SyncJobStatus, ValidationStatus
from app.models.user import UserRole
from app.services.competitors import clean_competitor_domains


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class AuthUpsertRequest(BaseModel):
    email: EmailStr
    name: str | None = None
    google_sub: str


class UserOut(ORMModel):
    id: UUID
    email: str
    name: str | None
    role: UserRole
    is_active: bool


class TierOut(ORMModel):
    id: UUID
    tier_name: str
    tracked_keyword_limit: int
    tracked_prompt_limit: int
    content_allowance: int
    update_allowance: int
    growth_action_allowance: int
    conversion_limit: int
    reporting_level: str
    watchlist_cadence: str


class TierCreate(BaseModel):
    tier_name: str
    tracked_keyword_limit: int = 10
    tracked_prompt_limit: int = 10
    content_allowance: int = 3
    update_allowance: int = 3
    growth_action_allowance: int = 1
    conversion_limit: int = 3
    reporting_level: str = "launch"
    watchlist_cadence: str = "monthly"


class ServiceReportingConfig(BaseModel):
    organiciq: bool
    ad_accelerator: bool


class ClientCreate(BaseModel):
    service_reporting: ServiceReportingConfig | None = None
    client_name: str
    domain: str
    tier_id: UUID
    slug: str | None = None
    start_date: Date | None = None
    primary_market: str | None = None
    timezone: str = "America/New_York"
    monthly_lead_goal: int | None = None
    lead_goal_overrides: dict | None = None
    brand_aliases: list[str] = []
    competitor_domains: list[str] = []
    account_sheet_url: str | None = None
    #: Where this client's sent growth actions land in Teamwork. The site and
    #: token are install-wide; this is the only per-client part, and without
    #: it the slot cards offer Copy instead of Send.
    teamwork_tasklist_id: str | None = None
    custom_tracked_keyword_limit: int | None = None
    custom_tracked_prompt_limit: int | None = None
    custom_content_allowance: int | None = None
    custom_update_allowance: int | None = None
    custom_growth_action_allowance: int | None = None
    custom_watchlist_cadence: str | None = None
    #: Resolved server-side from tier + overrides, so a caller never has to
    #: apply the rule itself — and never has to read the admin tier list to
    #: do it, which a client-role user is forbidden from fetching at all.
    growth_action_allowance: int | None = None
    #: The tier's name, for the same reason: naming the plan on screen is
    #: not a reason to hand someone the whole tier table.
    plan_label: str | None = None
    ai_search_prompt_limit: int | None = None
    crawl_page_limit: int | None = None
    sitemap_url: str | None = None
    path_prefix: str | None = None
    baseline_as_of: Date | None = None
    baseline_period_start: Date | None = None
    baseline_period_end: Date | None = None
    baseline_monthly_sessions: int | None = None
    baseline_monthly_leads: int | None = None
    baseline_lead_rate_pct: float | None = None
    baseline_source: str | None = None
    baseline_notes: str | None = None
    baseline_projection_json: dict | None = None
    status: ClientStatus = ClientStatus.ONBOARDING

    @field_validator("domain", "sitemap_url", check_fields=False)
    @classmethod
    def _must_be_a_public_site(cls, value: str | None, info) -> str | None:
        problem = public_host_or_error(value)
        if problem:
            raise ValueError(f"{info.field_name} {problem}")
        return value

    @field_validator("competitor_domains", check_fields=False)
    @classmethod
    def _at_most_three_competitors(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else clean_competitor_domains(value)


class ClientUpdate(BaseModel):
    service_reporting: ServiceReportingConfig | None = None
    client_name: str | None = None
    slug: str | None = None
    domain: str | None = None
    tier_id: UUID | None = None
    start_date: Date | None = None
    primary_market: str | None = None
    timezone: str | None = None
    monthly_lead_goal: int | None = None
    lead_goal_overrides: dict | None = None
    brand_aliases: list[str] | None = None
    competitor_domains: list[str] | None = None
    account_sheet_url: str | None = None
    #: Where this client's sent growth actions land in Teamwork. The site
    #: and token are install-wide; this is the only per-client part, and
    #: without it the slot cards offer Copy instead of Send.
    teamwork_tasklist_id: str | None = None
    custom_tracked_keyword_limit: int | None = None
    custom_tracked_prompt_limit: int | None = None
    custom_content_allowance: int | None = None
    custom_update_allowance: int | None = None
    custom_growth_action_allowance: int | None = None
    custom_watchlist_cadence: str | None = None
    #: Resolved server-side from tier + overrides, so a caller never has to
    #: apply the rule itself — and never has to read the admin tier list to
    #: do it, which a client-role user is forbidden from fetching at all.
    growth_action_allowance: int | None = None
    #: The tier's name, for the same reason: naming the plan on screen is
    #: not a reason to hand someone the whole tier table.
    plan_label: str | None = None
    ai_search_prompt_limit: int | None = None
    crawl_page_limit: int | None = None
    sitemap_url: str | None = None
    path_prefix: str | None = None
    baseline_as_of: Date | None = None
    baseline_period_start: Date | None = None
    baseline_period_end: Date | None = None
    baseline_monthly_sessions: int | None = None
    baseline_monthly_leads: int | None = None
    baseline_lead_rate_pct: float | None = None
    baseline_source: str | None = None
    baseline_notes: str | None = None
    baseline_projection_json: dict | None = None
    status: ClientStatus | None = None

    @field_validator("domain", "sitemap_url", check_fields=False)
    @classmethod
    def _must_be_a_public_site(cls, value: str | None, info) -> str | None:
        problem = public_host_or_error(value)
        if problem:
            raise ValueError(f"{info.field_name} {problem}")
        return value

    @field_validator("competitor_domains", check_fields=False)
    @classmethod
    def _at_most_three_competitors(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else clean_competitor_domains(value)


class ClientOut(ORMModel):
    service_reporting: ServiceReportingConfig | None = None
    id: UUID
    client_name: str
    slug: str
    domain: str
    tier_id: UUID
    start_date: Date | None
    primary_market: str | None
    timezone: str
    monthly_lead_goal: int | None
    brand_aliases: list[str] = []
    competitor_domains: list[str] = []
    account_sheet_url: str | None
    teamwork_tasklist_id: str | None = None
    custom_tracked_keyword_limit: int | None = None
    custom_tracked_prompt_limit: int | None = None
    custom_content_allowance: int | None = None
    custom_update_allowance: int | None = None
    custom_growth_action_allowance: int | None = None
    custom_watchlist_cadence: str | None = None
    #: Resolved server-side from tier + overrides, so a caller never has to
    #: apply the rule itself — and never has to read the admin tier list to
    #: do it, which a client-role user is forbidden from fetching at all.
    growth_action_allowance: int | None = None
    #: The tier's name, for the same reason: naming the plan on screen is
    #: not a reason to hand someone the whole tier table.
    plan_label: str | None = None
    ai_search_prompt_limit: int | None = None
    crawl_page_limit: int | None = None
    sitemap_url: str | None = None
    path_prefix: str | None = None
    baseline_as_of: Date | None = None
    baseline_period_start: Date | None = None
    baseline_period_end: Date | None = None
    baseline_monthly_sessions: int | None = None
    baseline_monthly_leads: int | None = None
    baseline_lead_rate_pct: float | None = None
    baseline_source: str | None = None
    baseline_notes: str | None = None
    baseline_projection_json: dict | None = None
    status: ClientStatus
    created_at: DateTime
    updated_at: DateTime


class AnnotationCreate(BaseModel):
    date: Date
    annotation_type: str
    description: str
    growth_action: str | None = None
    decision_id: UUID | None = None
    topic_id: UUID | None = None
    page_url: str | None = None
    baseline_metrics_json: dict = Field(default_factory=dict)
    success_metric: str | None = None
    teamwork_task_id: str | None = None
    completed_at: Date | None = None
    measurement_start_date: Date | None = None
    measurement_end_date: Date | None = None
    post_action_metrics_json: dict = Field(default_factory=dict)
    result: str = "not_yet_measured"
    notes: str | None = None


class AnnotationUpdate(BaseModel):
    date: Date | None = None
    annotation_type: str | None = None
    description: str | None = None
    growth_action: str | None = None
    decision_id: UUID | None = None
    topic_id: UUID | None = None
    page_url: str | None = None
    baseline_metrics_json: dict | None = None
    success_metric: str | None = None
    teamwork_task_id: str | None = None
    completed_at: Date | None = None
    measurement_start_date: Date | None = None
    measurement_end_date: Date | None = None
    post_action_metrics_json: dict | None = None
    result: str | None = None
    notes: str | None = None


class AnnotationOut(ORMModel):
    id: UUID
    client_id: UUID
    decision_id: UUID | None
    date: Date
    annotation_type: str
    growth_action: str | None
    description: str
    topic_id: UUID | None
    page_url: str | None
    baseline_metrics_json: dict
    success_metric: str | None
    teamwork_task_id: str | None
    completed_at: Date | None
    measurement_start_date: Date | None
    measurement_end_date: Date | None
    post_action_metrics_json: dict
    result: str
    notes: str | None
    impact_summary_json: dict
    created_at: DateTime
    updated_at: DateTime


class AnnotationImportRequest(BaseModel):
    csv_text: str


class AnnotationImportResponse(BaseModel):
    created: int
    errors: list[dict]


class BaselineSeriesCsvRequest(BaseModel):
    """A monthly series pasted as CSV. Nothing is stored."""

    csv_text: str = Field(min_length=1, max_length=200_000)
    regime_start: str | None = None
    #: The last day the data covers; a month it falls in is left out as unfinished.
    as_of: Date | None = None
    half_life_months: float = Field(default=3.0, ge=0.5, le=24)
    acknowledged: list[str] = []


class BaselineLockRequest(BaseModel):
    """Freeze a baseline. The numbers are recomputed from the source, never taken from here."""

    source: str = "ga4"
    csv_text: str | None = Field(default=None, max_length=200_000)
    as_of: Date | None = None
    months: int = Field(default=24, ge=6, le=48)
    regime_start: str | None = None
    lead_events: list[str] = []
    half_life_months: float = Field(default=3.0, ge=0.5, le=24)
    acknowledged: list[str] = []
    reason_code: str | None = None
    reason_note: str | None = Field(default=None, max_length=2000)
    #: The plan-end goal. Absent means the 12-month figure from this baseline's own projection.
    monthly_lead_goal: int | None = Field(default=None, ge=0)
    target_lead_rate_pct: float | None = Field(default=None, gt=0, le=100)
    #: Agree to make the chosen events the client's lead conversions, which the home
    #: screen, alerts and results count, when they differ from what is set now.
    sync_lead_conversions: bool = False


class BaselineResetRequest(BaseModel):
    """Wipe baselines and goals. `confirm` must be exactly RESET."""

    confirm: str
    #: Leave empty to reset every client.
    client_ids: list[UUID] = []


class BaselineGoalRequest(BaseModel):
    monthly_lead_goal: int = Field(ge=0)


class BaselineLeadConversionsRequest(BaseModel):
    lead_events: list[str] = Field(min_length=1)


class IntegrationCreate(BaseModel):
    provider: IntegrationProvider
    external_account_id: str | None = None
    external_property_id: str | None = None
    connection_status: ConnectionStatus = ConnectionStatus.NOT_CONNECTED


class IntegrationUpdate(BaseModel):
    external_account_id: str | None = None
    external_property_id: str | None = None
    connection_status: ConnectionStatus | None = None
    error_message: str | None = None


class IntegrationOut(ORMModel):
    id: UUID
    client_id: UUID
    provider: IntegrationProvider
    external_account_id: str | None
    external_property_id: str | None
    gsc_secondary_site_urls: list[str] = []
    connection_status: ConnectionStatus
    last_sync_started: DateTime | None
    last_sync_completed: DateTime | None
    last_successful_sync: DateTime | None
    last_fact_date: Date | None
    error_message: str | None
    created_at: DateTime
    updated_at: DateTime


class SyncJobCreate(BaseModel):
    source: str = Field(min_length=1, max_length=64)
    start_date: Date
    end_date: Date
    params: dict | None = None


class SyncJobOut(ORMModel):
    id: UUID
    client_id: UUID
    source: str
    start_date: Date
    end_date: Date
    status: SyncJobStatus
    started_at: DateTime | None
    completed_at: DateTime | None
    records_fetched: int | None
    records_written: int | None
    fact_watermark: Date | None
    validation_status: ValidationStatus | None
    error_message: str | None
    created_at: DateTime
    updated_at: DateTime


class DataWatermarkOut(ORMModel):
    id: UUID
    client_id: UUID
    source: str
    fact_through_date: Date | None
    last_successful_sync_at: DateTime | None
    validation_status: ValidationStatus | None


class ConversionDefinitionCreate(BaseModel):
    event_name: str
    conversion_name: str
    conversion_type: str = "lead"
    is_primary: bool = False
    active: bool = True


class ConversionDefinitionOut(ORMModel):
    id: UUID
    client_id: UUID
    event_name: str
    conversion_name: str
    conversion_type: str
    is_primary: bool
    active: bool


class ChannelRuleOut(ORMModel):
    id: UUID
    match_source: str | None
    match_medium: str | None
    match_host_contains: str | None
    channel: OrganicChannel
    priority: int
    active: bool
    description: str | None


class TopicCreate(BaseModel):
    topic_name: str
    description: str | None = None
    priority: int = 0
    status: TopicStatus = TopicStatus.ACTIVE


class TopicOut(ORMModel):
    id: UUID
    client_id: UUID
    topic_name: str
    description: str | None
    priority: int
    status: TopicStatus


class UserClientAssign(BaseModel):
    user_id: UUID
    client_id: UUID
    role: UserRole = UserRole.SMA_TEAM


class UserClientRemove(BaseModel):
    user_id: UUID
    client_id: UUID


class ClientTeamMemberOut(BaseModel):
    user_id: UUID
    email: str
    name: str | None
    role: UserRole
    is_active: bool
    # True when access comes from the SMA_ADMIN role rather than an assignment.
    via_admin: bool = False


class ExcludedPageIn(BaseModel):
    """A page or section the engine must not prescribe for.

    `/careers*` takes the careers index and everything under it, which is
    what somebody means by "we are not working on careers".
    """

    url_pattern: str
    reason: str


class PageStageIn(BaseModel):
    """A funnel stage somebody is confirming for a landing page."""

    normalized_url: str
    stage: Literal["tofu", "mofu", "bofu"]


class MonthlyRunRequest(BaseModel):
    """Which finished month to run. Absent means last month."""

    month: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$")


class EngineActionAssign(BaseModel):
    """Hand a slot to somebody. A null assignee returns it to planned.

    Identified by email, because most of the team does the work and never
    opens this tool — and because email is already how a sent task finds its
    owner in Teamwork.
    """

    assignee_email: str | None = None
    assignee_name: str | None = None
    due: Date | None = None


class EngineActionInPlan(BaseModel):
    """Put an action in the month's plan, or take it out.

    Null hands the decision back to the engine rather than freezing what it
    last said.
    """

    in_plan: bool | None = None
    reason: str | None = None


class EngineActionShipped(BaseModel):
    """The day the work went live. Null clears it."""

    shipped_on: Date | None = None


class EngineActionSkip(BaseModel):
    """Take a slot off the table, or put it back.

    A reason is required on the way out. "Skipped" with nothing beside it is
    what makes next month unable to tell a wrong action from a busy month.
    """

    reason: str | None = None
    undo: bool = False


class HealthOut(BaseModel):
    status: str
    service: str


class ConversionPageIn(BaseModel):
    """A page this client counts as an offer.

    Declared pages win over the URL guesses. `classify_page_url` reads
    fragments — /contact, /demo, /quote — which is right often enough to
    have hidden how often it is wrong: ACCTek's offer is /contact-us, and
    the engine spent months telling people to link to /contact, which 404s.
    """

    model_config = ConfigDict(populate_by_name=True)

    normalized_url: str = Field(min_length=1, max_length=2048)
    label: str = Field(min_length=1, max_length=255)
    #: tofu / mofu / bofu, so a page is sent to the offer that matches where
    #: its reader is rather than to whichever one is primary.
    stage: str | None = Field(default=None, max_length=8)
    is_primary: bool = False


class ConversionPageOut(ORMModel):
    id: UUID
    normalized_url: str
    label: str
    stage: str | None = None
    is_primary: bool = False


class KeywordTargetEntry(BaseModel):
    keyword: str = Field(min_length=1, max_length=512)
    #: Null records "no page owns this yet" — a decision, not an omission.
    target_url: str | None = None
    #: primary | secondary | None. Null means nobody has said, which the
    #: rules that care must treat as its own answer.
    term_role: Literal["primary", "secondary"] | None = None
    group_name: str | None = None
    priority: bool = False
    note: str | None = None


class KeywordTargetUpdate(BaseModel):
    entries: list[KeywordTargetEntry]


class KeywordTargetOut(ORMModel):
    keyword: str
    target_url: str | None
    term_role: str | None
    group_name: str | None
    priority: bool
    source: str
    confidence: float | None
    note: str | None
