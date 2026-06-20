"""Data models for planner-controlled development runs."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentforge.core.runner import RunResult


@dataclass(frozen=True)
class DevRunSession:
    """Prepared dev cycle waiting at the human approval gate."""

    user_request: str
    project_root: Path
    workflow_path: Path
    max_cycles: int
    run_result: RunResult
    cycle_number: int
    planner_summary: str
    selected_agents: list[str]
    generated_patches: list[dict[str, Any]]
    previous_testing_report: dict[str, Any] | None = None
    planned_focus: str | None = None

    @property
    def run_id(self) -> str:
        """Return the run ID for this dev session."""
        return self.run_result.run_id

    @property
    def run_directory(self) -> Path:
        """Return the artifact directory for this dev session."""
        return self.run_result.run_directory


@dataclass(frozen=True)
class DevRunResult:
    """Completed dev cycle result."""

    run_id: str
    run_directory: Path
    user_request: str
    project_root: Path
    workflow_path: Path
    max_cycles: int
    status: str
    cycle_number: int
    planner_summary: str
    selected_agents: list[str]
    generated_patches: list[dict[str, Any]]
    applied_patches: list[dict[str, Any]]
    test_status: str
    test_command: list[str] | None
    testing_report: dict[str, Any]
    planner_decisions: list[dict[str, Any]]
    final_verdict: str
