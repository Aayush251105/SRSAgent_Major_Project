import os
from dataclasses import dataclass


@dataclass
class LLMConfig:
    """Configuration for selecting and initializing the LLM provider."""

    provider: str = os.getenv("LLM_PROVIDER", "ollama")
    model: str = os.getenv("LLM_MODEL", "llama3.1")

    ollama_host: str = os.getenv(
        "OLLAMA_HOST",
        "http://localhost:11434"
    )

    grok_api_key: str | None = os.getenv("XAI_API_KEY")