"""Trace events for inspectable workflow runs."""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from agentforge.config.schemas import AgentConfig


@dataclass(frozen=True)
class TraceEvent:
    """One agent execution event."""

    agent: str
    input_keys: list[str]
    output_key: str
    status: Literal["success", "failed"]
    timestamp: str
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        event = asdict(self)
        if self.error_message is None:
            event.pop("error_message")
        return event


class TraceLog:
    """Collect trace events in execution order."""

    def __init__(self) -> None:
        self.events: list[TraceEvent] = []

    def append_success(self, agent_config: AgentConfig) -> None:
        self.events.append(self._create_event(agent_config, status="success"))

    def append_failure(self, agent_config: AgentConfig, error_message: str) -> None:
        self.events.append(
            self._create_event(agent_config, status="failed", error_message=error_message)
        )

    def to_list(self) -> list[dict[str, Any]]:
        return [event.to_dict() for event in self.events]

    @staticmethod
    def _create_event(
        agent_config: AgentConfig,
        *,
        status: Literal["success", "failed"],
        error_message: str | None = None,
    ) -> TraceEvent:
        return TraceEvent(
            agent=agent_config.name,
            input_keys=list(agent_config.input_keys),
            output_key=agent_config.output_key,
            status=status,
            timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            error_message=error_message,
        )
