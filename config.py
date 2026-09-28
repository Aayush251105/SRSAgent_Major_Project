import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


# Load project-local configuration when running from any working directory.
load_dotenv(Path(__file__).resolve().parent / ".env")


@dataclass
class LLMConfig:
    """Configuration for selecting and initializing the LLM provider."""

    provider: str = os.getenv("LLM_PROVIDER", "ollama").strip().lower()
    model: str = os.getenv("LLM_MODEL", "llama3.1")

    ollama_host: str = os.getenv(
        "OLLAMA_HOST",
        "http://localhost:11434"
    )

    grok_api_key: str | None = os.getenv("XAI_API_KEY")
