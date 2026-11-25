from functools import lru_cache
from pathlib import Path

from pydantic import field_validator, model_validator
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
    freshness_service_url: str = "http://localhost:8100"
    toxifruit_service_url: str = "http://localhost:8101"
    indian_recognition_model_path: Path = Path("artifacts/indian_food_v1/indian_food_classifier.ts")
    indian_recognition_labels_path: Path = Path("artifacts/indian_food_v1/classes.json")
    cinnamon_ftir_model_dir: Path = Path("artifacts/food_fraud/cinnamon_ftir")
    indian_recognition_model_version: str = "indian-food-v1"
    indian_recognition_confidence_threshold: float = 0.65
    indian_recognition_temperature: float = 0.583016488786505
    jwt_secret_key: str = "development-only-change-this-secret-key"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080
    knowledge_graph_enabled: bool = False
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: str = ""
    neo4j_database: str = "neo4j"
    embedding_model_name: str = "BAAI/bge-small-en-v1.5"
    embedding_dimensions: int = 384
    embedding_batch_size: int = 32
    embedding_cache_dir: Path = Path("storage/model_cache")
    regulatory_admin_user_ids: list[int] = []

    @field_validator("regulatory_admin_user_ids")
    @classmethod
    def validate_regulatory_admin_ids(cls, values: list[int]) -> list[int]:
        if any(isinstance(value, bool) or value <= 0 for value in values):
            raise ValueError("REGULATORY_ADMIN_USER_IDS must contain positive user IDs")
        if len(values) != len(set(values)):
            raise ValueError("REGULATORY_ADMIN_USER_IDS cannot contain duplicates")
        return values

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

    @field_validator("indian_recognition_confidence_threshold")
    @classmethod
    def validate_indian_confidence_threshold(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("INDIAN_RECOGNITION_CONFIDENCE_THRESHOLD must be between 0 and 1")
        return value

    @field_validator("indian_recognition_temperature")
    @classmethod
    def validate_indian_temperature(cls, value: float) -> float:
        if not 0.05 <= value <= 20.0:
            raise ValueError("INDIAN_RECOGNITION_TEMPERATURE must be between 0.05 and 20")
        return value

    @field_validator("recognition_image_size")
    @classmethod
    def validate_image_size(cls, value: int) -> int:
        if not 32 <= value <= 1024:
            raise ValueError("RECOGNITION_IMAGE_SIZE must be between 32 and 1024")
        return value

    @field_validator("embedding_dimensions")
    @classmethod
    def validate_embedding_dimensions(cls, value: int) -> int:
        if value != 384:
            raise ValueError("The configured BGE-small model requires 384 dimensions")
        return value

    @field_validator("embedding_batch_size")
    @classmethod
    def validate_embedding_batch_size(cls, value: int) -> int:
        if not 1 <= value <= 128:
            raise ValueError("EMBEDDING_BATCH_SIZE must be between 1 and 128")
        return value

    @field_validator("access_token_expire_minutes")
    @classmethod
    def validate_token_expiry(cls, value: int) -> int:
        if not 5 <= value <= 43200:
            raise ValueError("ACCESS_TOKEN_EXPIRE_MINUTES must be between 5 and 43200")
        return value

    @model_validator(mode="after")
    def validate_jwt_secret(self):
        if self.app_env == "production":
            if len(self.jwt_secret_key) < 40:
                raise ValueError("A strong JWT_SECRET_KEY is required in production")
            if self.jwt_secret_key == "development-only-change-this-secret-key":
                raise ValueError("The development JWT secret cannot be used in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


