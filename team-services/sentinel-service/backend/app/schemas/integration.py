from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SecurityEventIn(BaseModel):

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    event_id: str = Field(min_length=8, max_length=64)

    source: str = Field(
        default="FoodInsightAI",
        min_length=1,
        max_length=64,
    )

    event_type: str = Field(
        min_length=1,
        max_length=64,
    )

    category: str | None = Field(default=None, max_length=100)
    severity: str | None = Field(default=None, max_length=20)

    risk_score: float | None = Field(
        default=None,
        ge=0,
        le=100,
    )

    client_id: str | None = Field(default=None, max_length=128)
    source_ip: str | None = Field(default=None, max_length=45)
    user_id: str | None = Field(default=None, max_length=64)
    account_id_hash: str | None = Field(default=None, max_length=64)

    method: str | None = Field(default=None, max_length=12)
    path: str | None = Field(default=None, max_length=512)

    status_code: int | None = Field(
        default=None,
        ge=100,
        le=599,
    )

    detection_rule_id: str | None = Field(
        default=None,
        max_length=120,
    )

    description: str | None = Field(
        default=None,
        max_length=1000,
    )

    action_taken: str | None = Field(
        default=None,
        max_length=80,
    )

    occurred_at: datetime | None = None

    @model_validator(mode="after")
    def require_client_identity(self):
        if not self.client_id and not self.source_ip:
            raise ValueError(
                "A client_id or source_ip is required."
            )

        return self

from uuid import UUID


class RevokeUserSessionsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    action_id: UUID
    incident_id: str = Field(pattern=r"^INC-\d{6}$", min_length=10, max_length=10)
    user_id: int = Field(gt=0)
    reason: str = Field(min_length=8, max_length=500)