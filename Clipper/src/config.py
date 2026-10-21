from pathlib import Path
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
import yaml


class AppConfig(BaseModel):
    storage_dir: Path = Path("storage")
    database_path: Path = Path("storage/clipper.db")
    log_level: str = "INFO"


class PipelineConfig(BaseModel):
    clip_min_duration_seconds: float = 120.0
    clip_max_duration_seconds: float = 300.0
    max_overlap_ratio: float = 0.20
    boundary_padding_seconds: float = 0.3
    target_lufs: float = -14.0
    audio_fade_seconds: float = 0.3


class AIConfig(BaseModel):
    whisper_model: str = "medium"
    whisper_device: str = "auto"
    whisper_compute_type: str = "auto"
    gemini_model: str = "gemini-1.5-flash"
    max_token_threshold: int = 90000
    chunk_overlap_tokens: int = 3000


class PublishingConfig(BaseModel):
    daily_quota_limit: int = 10000
    upload_cost_units: int = 1600
    max_uploads_per_day: int = 6
    default_privacy: str = "private"


class Config(BaseModel):
    app: AppConfig = Field(default_factory=AppConfig)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    ai: AIConfig = Field(default_factory=AIConfig)
    publishing: PublishingConfig = Field(default_factory=PublishingConfig)


class EnvSettings(BaseSettings):
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    clipper_env: str = "production"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


def load_config(config_path: str = "config.yaml") -> tuple[Config, EnvSettings]:
    path = Path(config_path)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            raw_yaml = yaml.safe_load(f) or {}
            config = Config(**raw_yaml)
    else:
        config = Config()

    config.app.storage_dir.mkdir(parents=True, exist_ok=True)
    config.app.database_path.parent.mkdir(parents=True, exist_ok=True)

    env = EnvSettings()
    return config, env
