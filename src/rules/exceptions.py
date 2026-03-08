"""Rules domain exceptions."""

from src.exceptions import EntityNotFoundError, ValidationError


class RuleNotFoundError(EntityNotFoundError):
    """Raised when a rule is not found."""

    def __init__(self, rule_id: str) -> None:
        super().__init__("Rule", rule_id)
        self.rule_id = rule_id


class RuleValidationError(ValidationError):
    """Raised when rule validation fails."""
