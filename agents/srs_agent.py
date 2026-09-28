from typing import List

from models.requirement import Requirement


class SRSAgent:
    """
    Converts detected requirement candidates into the canonical Requirement
    representation used by the Retrieval Agent.
    """

    def __init__(self, llm_provider):
        self.llm_provider = llm_provider

    def extract(
        self,
        candidates: List[dict]
    ) -> List[Requirement]:
        """
        Send requirement candidates to the configured LLM provider and
        validate the structured response.
        """

        requirements = []

        for index, candidate in enumerate(candidates, start=1):
            prompt = self._build_prompt(
                candidate["text"],
                candidate["source"],
                index
            )

            response = self.llm_provider.generate_structured(
                prompt=prompt,
                schema=Requirement
            )

            requirements.append(
                Requirement.model_validate(response)
            )

        return requirements

    def _build_prompt(
        self,
        text: str,
        source: dict,
        index: int
    ) -> str:
        """Build the extraction prompt while preserving the original text."""

        return f"""
You are an SRS analysis agent.

Extract the software requirement from the provided text and return it
according to the supplied structured schema.

Rules:
- Preserve the requirement meaning.
- Do not invent implementation details.
- raw_text must exactly match the provided requirement text.
- Extract actors, actions, entities, inputs, outputs, conditions,
  constraints, and error conditions when explicitly implied.
- Decompose complex requirements into meaningful sub_requirements.
- Generate useful domain_terms and synonyms for code retrieval.
- retrieval_text should combine the important concepts needed to find
  related source-code components.
- If information is unavailable, use an empty list or appropriate empty value.
- requirement_id should be REQ-{index:03d}.
- id_source should be "generated".

Requirement:
{text}

Source:
{source}
"""