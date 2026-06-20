"""Trace events for inspectable workflow runs."""

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from agentforge.config.schemas import AgentConfig
from agentforge.llm import AgentInvocation, AgentResponse


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
            timestamp=_utc_timestamp(),
            error_message=error_message,
        )


@dataclass(frozen=True)
class ToolCallRecord:
    """One deterministic tool call made before an agent runs."""

    agent: str
    tool: str
    status: Literal["success", "failed"]
    input: dict[str, Any]
    output_preview: str
    timestamp: str
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        if self.error is None:
            record.pop("error")
        return record


class ToolCallLog:
    """Collect tool call records in execution order."""

    def __init__(self) -> None:
        self.records: list[ToolCallRecord] = []

    def append_success(
        self,
        *,
        agent_name: str,
        tool_name: str,
        tool_input: dict[str, Any],
        output: Any,
    ) -> None:
        self.records.append(
            ToolCallRecord(
                agent=agent_name,
                tool=tool_name,
                status="success",
                input=dict(tool_input),
                output_preview=self._preview_output(output),
                timestamp=_utc_timestamp(),
            )
        )

    def append_failure(
        self,
        *,
        agent_name: str,
        tool_name: str,
        tool_input: dict[str, Any],
        error_message: str,
    ) -> None:
        self.records.append(
            ToolCallRecord(
                agent=agent_name,
                tool=tool_name,
                status="failed",
                input=dict(tool_input),
                output_preview="",
                timestamp=_utc_timestamp(),
                error=error_message,
            )
        )

    def to_list(self) -> list[dict[str, Any]]:
        return [record.to_dict() for record in self.records]

    @staticmethod
    def _preview_output(output: Any, max_length: int = 500) -> str:
        if isinstance(output, str):
            preview = output
        else:
            preview = json.dumps(output, sort_keys=True)
        if len(preview) > max_length:
            return f"{preview[:max_length]}..."
        return preview


@dataclass(frozen=True)
class LLMCallRecord:
    """One provider text generation call made for an agent."""

    agent: str
    provider: str
    model: str
    input_keys: list[str]
    output_key: str
    prompt_preview: str
    response_preview: str
    metadata: dict[str, Any]
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LLMCallLog:
    """Collect provider text generation records in execution order."""

    def __init__(self) -> None:
        self.records: list[LLMCallRecord] = []

    def append(self, invocation: AgentInvocation, response: AgentResponse) -> None:
        self.records.append(
            LLMCallRecord(
                agent=invocation.agent_name,
                provider=response.provider,
                model=response.model,
                input_keys=list(invocation.inputs),
                output_key=invocation.output_key,
                prompt_preview=_preview_text(invocation.prompt),
                response_preview=_preview_text(response.content),
                metadata=dict(response.metadata),
                timestamp=_utc_timestamp(),
            )
        )

    def to_list(self) -> list[dict[str, Any]]:
        return [record.to_dict() for record in self.records]


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _preview_text(value: str, max_length: int = 500) -> str:
    if len(value) > max_length:
        return f"{value[:max_length]}..."
    return value
