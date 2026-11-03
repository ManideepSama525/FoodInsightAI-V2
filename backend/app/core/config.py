from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "FoodInsightAI V2"
    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"
    cors_origins: list[str] = ["http://localhost:3000"]
    database_url: str = "sqlite:///./foodinsightai.db"
    max_upload_size_mb: int = 10
    upload_directory: Path = Path("storage/uploads")
    usda_api_key: str = ""
    usda_base_url: str = "https://api.nal.usda.gov/fdc/v1"
    recognition_model_path: Path = Path("artifacts/food_classifier.ts")
    recognition_labels_path: Path = Path("artifacts/classes.json")
    recognition_model_version: str = "untrained"
    recognition_confidence_threshold: float = 0.65
    recognition_image_size: int = 224

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("app_env")
    @classmethod
    def validate_app_env(cls, value: str) -> str:
        value = value.casefold().strip()
        if value not in {"development", "test", "staging", "production"}:
            raise ValueError("APP_ENV must be development, test, staging or production")
        return value

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, values: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(origin.strip().rstrip("/") for origin in values if origin.strip()))
        if not cleaned:
            raise ValueError("CORS_ORIGINS must contain at least one explicit origin")
        if "*" in cleaned:
            raise ValueError("Wildcard CORS origins are not allowed when credentials are enabled")
        for origin in cleaned:
            if not origin.startswith(("http://", "https://")):
                raise ValueError(f"Invalid CORS origin: {origin}")
        return cleaned

    @field_validator("max_upload_size_mb")
    @classmethod
    def validate_upload_limit(cls, value: int) -> int:
        if not 1 <= value <= 50:
            raise ValueError("MAX_UPLOAD_SIZE_MB must be between 1 and 50")
        return value

    @field_validator("recognition_confidence_threshold")
    @classmethod
    def validate_confidence_threshold(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("RECOGNITION_CONFIDENCE_THRESHOLD must be between 0 and 1")
        return value

    @field_validator("recognition_image_size")
    @classmethod
    def validate_image_size(cls, value: int) -> int:
        if not 32 <= value <= 1024:
            raise ValueError("RECOGNITION_IMAGE_SIZE must be between 32 and 1024")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
