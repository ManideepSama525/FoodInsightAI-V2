from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RevokeUserSessionsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    action_id: UUID
    incident_id: str = Field(pattern=r"^INC-\d{6}$", min_length=10, max_length=10)
    user_id: int = Field(gt=0)
    reason: str = Field(min_length=8, max_length=500)