from datetime import date as Date, datetime as DateTime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.client import ClientStatus
from app.models.config import OrganicChannel, TopicStatus
from app.models.integration import ConnectionStatus, IntegrationProvider
from app.models.job import SyncJobStatus, ValidationStatus
from app.models.user import UserRole


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


class ClientCreate(BaseModel):
    client_name: str
    domain: str
    tier_id: UUID
    slug: str | None = None
    start_date: Date | None = None
    primary_market: str | None = None
    timezone: str = "America/New_York"
    monthly_lead_goal: int | None = None
    account_sheet_url: str | None = None
    custom_tracked_keyword_limit: int | None = None
    custom_tracked_prompt_limit: int | None = None
    custom_content_allowance: int | None = None
    custom_update_allowance: int | None = None
    custom_growth_action_allowance: int | None = None
    custom_watchlist_cadence: str | None = None
    baseline_as_of: Date | None = None
    baseline_monthly_sessions: int | None = None
    baseline_monthly_leads: int | None = None
    baseline_lead_rate_pct: float | None = None
    baseline_source: str | None = None
    baseline_notes: str | None = None
    status: ClientStatus = ClientStatus.ONBOARDING


class ClientUpdate(BaseModel):
    client_name: str | None = None
    slug: str | None = None
    domain: str | None = None
    tier_id: UUID | None = None
    start_date: Date | None = None
    primary_market: str | None = None
    timezone: str | None = None
    monthly_lead_goal: int | None = None
    account_sheet_url: str | None = None
    custom_tracked_keyword_limit: int | None = None
    custom_tracked_prompt_limit: int | None = None
    custom_content_allowance: int | None = None
    custom_update_allowance: int | None = None
    custom_growth_action_allowance: int | None = None
    custom_watchlist_cadence: str | None = None
    baseline_as_of: Date | None = None
    baseline_monthly_sessions: int | None = None
    baseline_monthly_leads: int | None = None
    baseline_lead_rate_pct: float | None = None
    baseline_source: str | None = None
    baseline_notes: str | None = None
    status: ClientStatus | None = None


class ClientOut(ORMModel):
    id: UUID
    client_name: str
    slug: str
    domain: str
    tier_id: UUID
    start_date: Date | None
    primary_market: str | None
    timezone: str
    monthly_lead_goal: int | None
    account_sheet_url: str | None
    custom_tracked_keyword_limit: int | None = None
    custom_tracked_prompt_limit: int | None = None
    custom_content_allowance: int | None = None
    custom_update_allowance: int | None = None
    custom_growth_action_allowance: int | None = None
    custom_watchlist_cadence: str | None = None
    baseline_as_of: Date | None = None
    baseline_monthly_sessions: int | None = None
    baseline_monthly_leads: int | None = None
    baseline_lead_rate_pct: float | None = None
    baseline_source: str | None = None
    baseline_notes: str | None = None
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


class BaselineUpdate(BaseModel):
    baseline_as_of: Date | None = None
    baseline_monthly_sessions: int | None = None
    baseline_monthly_leads: int | None = None
    baseline_lead_rate_pct: float | None = None
    baseline_source: str | None = None
    baseline_notes: str | None = None
    monthly_lead_goal: int | None = None


class BaselineSnapshotApplyRequest(BaseModel):
    monthly_lead_goal: int | None = None
    notes: str | None = None


class BaselineCheckpointOut(BaseModel):
    label: str
    month: int
    monthly_sessions: float
    lead_rate_pct: float
    monthly_leads: float


class BaselineSnapshotPreviewOut(BaseModel):
    ready: bool
    window: dict
    lead_events: list[str]
    tier_name: str | None
    plan: str
    plan_label: str
    period_sessions: float
    period_leads: int
    baseline_as_of: str
    baseline_monthly_sessions: int
    baseline_monthly_leads: int
    baseline_lead_rate_pct: float | None
    baseline_source: str
    suggested_monthly_lead_goal: int
    goal_horizon_months: int
    checkpoints: list[BaselineCheckpointOut]
    disclaimer: str
    current_monthly_lead_goal: int | None = None
    applied_monthly_lead_goal: int | None = None


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


class HealthOut(BaseModel):
    status: str
    service: str


class DecisionOut(ORMModel):
    id: UUID
    client_id: UUID
    rule_key: str
    created_at: DateTime
    decision_type: str
    growth_action: str | None
    diagnostic_layer: str
    priority: str
    status: str
    topic_id: UUID | None
    page_url: str | None
    query: str | None
    keyword: str | None
    prompt: str | None
    diagnosis: str
    recommended_action: str
    evidence_json: dict
    baseline_metrics_json: dict
    success_metric: str
    date_range_start: Date
    date_range_end: Date
    dismissal_reason: str | None
    priority_score: float | None = None
    impact: float | None = None
    confidence: float | None = None
    urgency: float | None = None
    effort: float | None = None


class LeverSummaryOut(BaseModel):
    lever: str
    label: str
    findings_count: int
    recommended_actions_count: int = 0
    status: str


class FindingOut(BaseModel):
    rule_key: str
    lever: str
    label: str
    stage: str
    diagnosis: str
    recommended_action: str
    success_metric: str
    priority_score: float
    impact: float
    confidence: float
    urgency: float
    effort: float
    severity: float | None = None
    page_url: str | None = None
    query: str | None = None
    evidence_json: dict
    is_recommended_action: bool = False
    promotion_blocked_reason: str | None = None
    priority_band: str = "none"
    priority_band_reason: str | None = None
    finding_group_key: str | None = None


class SearchOpportunityOut(BaseModel):
    rule_key: str
    page_url: str | None = None
    query: str | None = None
    topic: str | None = None
    impressions: int | None = None
    clicks: int | None = None
    ctr_percent: float | None = None
    average_position: float | None = None
    page_type: str | None = None
    opportunity_type: str
    diagnosis: str


class RecommendationOut(FindingOut):
    pass


class DiagnoseResponse(BaseModel):
    ready: bool
    message: str | None = None
    readiness: dict[str, bool]
    formula: str
    requested_from: Date | None = None
    requested_to: Date | None = None
    analysis_from: Date | None = None
    analysis_to: Date | None = None
    partial_message: str | None = None
    findings_count: int = 0
    recommended_actions_count: int = 0
    levers: list[LeverSummaryOut]
    findings: list[FindingOut] = []
    recommended_actions: list[FindingOut] = []
    search_opportunities: list[SearchOpportunityOut] = []
    recommendations: list[FindingOut] = []


class DecisionEvaluateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_date: Date = Field(alias="from")
    to_date: Date = Field(alias="to")


class DecisionEnsureRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_date: Date = Field(alias="from")
    to_date: Date = Field(alias="to")
    rule_key: str


class DecisionEvaluateResponse(BaseModel):
    created: list[DecisionOut]
    skipped: int
    diagnose: DiagnoseResponse


class DecisionStatusUpdate(BaseModel):
    status: str
    dismissal_reason: str | None = None


class DecisionThresholdsOut(BaseModel):
    thresholds: dict[str, float | int]
    defaults: dict[str, float | int]


class DecisionThresholdsUpdate(BaseModel):
    thresholds: dict[str, float | int]
