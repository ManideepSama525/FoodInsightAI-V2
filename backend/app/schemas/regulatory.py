from datetime import datetime
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


OFFICIAL_DOMAIN_SUFFIXES = (
    "gov.in",
    "nic.in",
    "gov",
    "gov.uk",
    "europa.eu",
    "who.int",
)


class RegulatoryEvidenceCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    source_id: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=3, max_length=500)
    content: str = Field(min_length=20, max_length=100000)
    authority: str = Field(min_length=2, max_length=200)
    jurisdiction: str = Field(min_length=2, max_length=100)
    source_url: str = Field(min_length=10, max_length=2000)
    document_type: Literal[
        "regulation",
        "recall",
        "contamination_alert",
        "guidance",
        "food_safety_notice",
    ]
    document_status: Literal[
        "active",
        "amended",
        "withdrawn",
        "superseded",
        "under_review",
    ]
    published_at: datetime
    effective_at: datetime | None = None
    last_checked_at: datetime

    @field_validator("source_url")
    @classmethod
    def validate_official_https_url(cls, value: str) -> str:
        parsed = urlparse(value)
        host = (parsed.hostname or "").lower().rstrip(".")

        if parsed.scheme.lower() != "https" or not host:
            raise ValueError("source_url must be a valid HTTPS URL")

        if parsed.username or parsed.password:
            raise ValueError("source_url cannot contain credentials")

        official = any(
            host == suffix or host.endswith("." + suffix)
            for suffix in OFFICIAL_DOMAIN_SUFFIXES
        )
        if not official:
            raise ValueError(
                "source_url must use an approved official government "
                "or international authority domain"
            )

        return value

    @model_validator(mode="after")
    def validate_dates(self):
        if self.effective_at and self.effective_at < self.published_at:
            raise ValueError("effective_at cannot precede published_at")
        if self.last_checked_at < self.published_at:
            raise ValueError("last_checked_at cannot precede published_at")
        return self


class RegulatoryEvidenceBatch(BaseModel):
    records: list[RegulatoryEvidenceCreate] = Field(min_length=1, max_length=500)
