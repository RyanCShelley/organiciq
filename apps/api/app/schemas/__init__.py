from datetime import date, datetime
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
    conversion_limit: int
    reporting_level: str


class TierCreate(BaseModel):
    tier_name: str
    tracked_keyword_limit: int = 100
    tracked_prompt_limit: int = 50
    content_allowance: int = 4
    update_allowance: int = 4
    conversion_limit: int = 5
    reporting_level: str = "standard"


class ClientCreate(BaseModel):
    client_name: str
    domain: str
    tier_id: UUID
    start_date: date | None = None
    primary_market: str | None = None
    timezone: str = "America/New_York"
    monthly_lead_goal: int | None = None
    status: ClientStatus = ClientStatus.ONBOARDING


class ClientUpdate(BaseModel):
    client_name: str | None = None
    domain: str | None = None
    tier_id: UUID | None = None
    start_date: date | None = None
    primary_market: str | None = None
    timezone: str | None = None
    monthly_lead_goal: int | None = None
    status: ClientStatus | None = None


class ClientOut(ORMModel):
    id: UUID
    client_name: str
    domain: str
    tier_id: UUID
    start_date: date | None
    primary_market: str | None
    timezone: str
    monthly_lead_goal: int | None
    status: ClientStatus
    created_at: datetime
    updated_at: datetime


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
    connection_status: ConnectionStatus
    last_sync_started: datetime | None
    last_sync_completed: datetime | None
    last_successful_sync: datetime | None
    last_fact_date: date | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class SyncJobCreate(BaseModel):
    source: str = Field(min_length=1, max_length=64)
    start_date: date
    end_date: date


class SyncJobOut(ORMModel):
    id: UUID
    client_id: UUID
    source: str
    start_date: date
    end_date: date
    status: SyncJobStatus
    started_at: datetime | None
    completed_at: datetime | None
    records_fetched: int | None
    records_written: int | None
    fact_watermark: date | None
    validation_status: ValidationStatus | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class DataWatermarkOut(ORMModel):
    id: UUID
    client_id: UUID
    source: str
    fact_through_date: date | None
    last_successful_sync_at: datetime | None
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
