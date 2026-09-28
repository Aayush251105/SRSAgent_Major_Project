from typing import Any, Dict, List

from pydantic import ValidationError

from models.requirement import Requirement, SRSOutput


class RequirementValidator:
    """
    Validates SRS Agent output against the canonical requirement schema.
    """

    def validate_requirement(self, data: Dict[str, Any]) -> Requirement:
        """Validate and return a single normalized requirement."""

        try:
            return Requirement.model_validate(data)
        except ValidationError as exc:
            raise ValueError(
                f"Invalid requirement output: {exc}"
            ) from exc

    def validate_output(self, data: Dict[str, Any]) -> SRSOutput:
        """Validate the complete SRS Agent response."""

        try:
            return SRSOutput.model_validate(data)
        except ValidationError as exc:
            raise ValueError(
                f"Invalid SRS Agent output: {exc}"
            ) from exc

    def validate_requirements(
        self,
        requirements: List[Dict[str, Any]]
    ) -> List[Requirement]:
        """Validate a list of extracted requirements."""

        return [
            self.validate_requirement(requirement)
            for requirement in requirements
        ]