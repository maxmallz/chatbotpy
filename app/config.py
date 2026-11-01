from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    core_svc_url: str = "http://127.0.0.1:8080"
    core_svc_timeout_s: float = 5.0

    # "offline" runs the rule-based agent; anything else is a Claude model id.
    agent_model: str = "claude-opus-5-5"
    agent_effort: str = "low"
    agent_timeout_s: float = 60.0
    agent_max_tool_calls: int = 8
    anthropic_api_key: str = ""

    host: str = "127.0.0.1"
    port: int = 8088

    @property
    def offline(self) -> bool:
        return self.agent_model == "offline" or not self.anthropic_api_key


@lru_cache
def get_settings() -> Settings:
    return Settings()
