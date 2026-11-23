import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


# Load project-local configuration when running from any working directory.
load_dotenv(Path(__file__).resolve().parent / ".env")


def _env_bool(name: str, default: bool | None) -> bool | None:
    """'true'/'false' (also 1/0, yes/no); unset or empty -> default."""
    value = os.getenv(name, "").strip().lower()
    if not value:
        return default
    return value in ("1", "true", "yes", "on")


@dataclass
class LLMConfig:
    """Configuration for selecting and initializing the LLM provider."""

    provider: str = os.getenv("LLM_PROVIDER", "ollama").strip().lower()
    # Defaults chosen by the model benchmark (TraceabilityApp/benchmark).
    model: str = os.getenv("LLM_MODEL", "qwen3:8b")
    judge_model: str = os.getenv("JUDGE_MODEL", "").strip()
    # Thinking models (qwen3): False disables the hidden reasoning pass, None
    # leaves the model's default. Extraction runs with thinking off (11h44m ->
    # 19 min on the benchmark); the judge keeps the model default.
    think: bool | None = _env_bool("LLM_THINK", False)
    judge_think: bool | None = _env_bool("JUDGE_THINK", None)

    ollama_host: str = os.getenv(
        "OLLAMA_HOST",
        "http://localhost:11434"
    )

    grok_api_key: str | None = os.getenv("XAI_API_KEY")
