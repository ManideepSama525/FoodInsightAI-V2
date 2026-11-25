"""Restricted synthetic-IP containment request contract."""
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TemporaryIPBlockRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    action_id: UUID
    incident_id: str = Field(
        pattern=r"^INC-\d{6}$",
        min_length=10,
        max_length=10,
    )
    source_ip: str = Field(min_length=7, max_length=45)
    duration_seconds: int = Field(ge=5, le=300)
    reason: str = Field(min_length=10, max_length=500)
