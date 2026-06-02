"""Shared state passed between agents in a workflow."""

from dataclasses import dataclass, field


class MissingStateInputError(KeyError):
    """Raised when an agent requires a state key that has not been produced."""

    def __init__(self, missing_key: str) -> None:
        super().__init__(missing_key)
        self.missing_key = missing_key

    def __str__(self) -> str:
        return f"missing required state input '{self.missing_key}'"


@dataclass
class WorkflowState:
    """Mutable shared state for one workflow run."""

    values: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_user_request(cls, input_text: str) -> "WorkflowState":
        return cls(values={"user_request": input_text})

    def get_required_inputs(self, input_keys: list[str]) -> dict[str, str]:
        inputs: dict[str, str] = {}
        for input_key in input_keys:
            if input_key not in self.values:
                raise MissingStateInputError(input_key)
            inputs[input_key] = self.values[input_key]
        return inputs

    def set_output(self, output_key: str, output: str) -> None:
        self.values[output_key] = output

    def to_dict(self) -> dict[str, str]:
        return dict(self.values)
