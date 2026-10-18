from datetime import date
from typing import Literal
from pydantic import BaseModel, Field, model_validator
from app.core.urls import public_host_or_error


class Observation(BaseModel):
    observed_on: date | None = None
    brand_mentioned: bool | None = None
    brand_cited: bool | None = None
    citation_url: str | None = Field(default=None, max_length=2048)
    source: str | None = Field(default=None, max_length=100)
    answer: str | None = Field(default=None, max_length=20000)


class WatchTargetUpdate(BaseModel):
    kind: Literal["keyword", "prompt"]
    text: str = Field(min_length=1, max_length=4000)
    provider: str | None = Field(default=None, max_length=100)
    state: Literal["existing", "planned", "unmapped", "excluded"]
    target_url: str | None = Field(default=None, max_length=2048)
    priority: bool = False
    note: str | None = Field(default=None, max_length=5000)
    observation: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_target(self):
        self.text = self.text.strip()
        if not self.text:
            raise ValueError("An item needs text.")
        if self.kind == "keyword" and len(self.text) > 512:
            raise ValueError("Keywords must be at most 512 characters.")
        if self.state == "existing":
            if not self.target_url or not self.target_url.startswith(("https://", "http://")):
                raise ValueError("An existing target needs an absolute HTTP or HTTPS page URL.")
            error = public_host_or_error(self.target_url)
            if error:
                raise ValueError(error)
        else:
            self.target_url = None
        if self.state in ("planned", "excluded") and not (self.note or "").strip():
            raise ValueError("Describe the planned page or explain the exclusion.")
        self.observation = Observation.model_validate(self.observation).model_dump(mode="json", exclude_none=True)
        return self
