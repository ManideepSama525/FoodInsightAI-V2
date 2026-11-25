from datetime import datetime
from pydantic import BaseModel


class IncidentCreate(BaseModel):
    attack_type: str
    severity: str
    source_ip: str
    target: str
    description: str
    ai_explanation: str
    confidence: float
    response_action: str


class IncidentResponse(BaseModel):
    id: int
    incident_id: str
    attack_type: str
    severity: str
    source_ip: str
    target: str
    description: str
    ai_explanation: str
    confidence: float
    response_action: str
    status: str
    created_at: datetime

    model_config = {
        "from_attributes": True
    }