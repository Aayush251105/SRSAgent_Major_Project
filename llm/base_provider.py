from abc import ABC, abstractmethod
from typing import Any, Type


class LLMProvider(ABC):
    """
    Common interface for all LLM providers used by the SRS Agent.

    The SRS Agent depends on this interface rather than a specific
    provider, allowing Ollama and Grok to be swapped independently.
    """

    @abstractmethod
    def generate_structured(
        self,
        prompt: str,
        schema: Type[Any]
    ) -> dict:
        """
        Generate a response that conforms to the provided structured schema.
        """
        pass