import json
from pathlib import Path

import pytest

from agentforge.core.runner import WorkflowExecutionError, WorkflowRunner

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_basic_workflow_run_creates_state_and_artifacts(tmp_path: Path) -> None:
    runner = WorkflowRunner(runs_directory=tmp_path / ".agentforge/runs")

    result = runner.run(
        PROJECT_ROOT / "examples/workflows/basic_feature.yaml",
        "Add a todo endpoint to a FastAPI app",
    )

    assert set(result.state) == {
        "user_request",
        "plan",
        "frontend_plan",
        "backend_plan",
        "test_plan",
        "review",
    }
    assert [event["agent"] for event in result.trace_events] == [
        "planner",
        "frontend",
        "backend",
        "testing",
        "reviewer",
    ]
    assert all(event["status"] == "success" for event in result.trace_events)

    expected_files = {"input.txt", "state.json", "trace.json", "final_report.md"}
    assert {path.name for path in result.run_directory.iterdir()} == expected_files

    saved_state = json.loads((result.run_directory / "state.json").read_text(encoding="utf-8"))
    saved_trace = json.loads((result.run_directory / "trace.json").read_text(encoding="utf-8"))
    final_report = (result.run_directory / "final_report.md").read_text(encoding="utf-8")

    assert saved_state == result.state
    assert saved_trace == result.trace_events
    assert "basic_feature" in final_report
    assert "Add a todo endpoint to a FastAPI app" in final_report
    for agent_name in ["planner", "frontend", "backend", "testing", "reviewer"]:
        assert f"### {agent_name}" in final_report


def test_missing_input_records_failed_trace_and_raises_clear_error(tmp_path: Path) -> None:
    agent_path = tmp_path / "missing-input-agent.yaml"
    agent_path.write_text(
        """
name: blocked
description: Requires an output that does not exist.
system_prompt: Produce a plan.
allowed_tools: []
input_keys:
  - missing_key
output_key: blocked_plan
""".strip(),
        encoding="utf-8",
    )
    workflow_path = tmp_path / "missing-input-workflow.yaml"
    workflow_path.write_text(
        """
name: missing_input
description: Demonstrates a missing state input.
agents:
  - missing-input-agent.yaml
""".strip(),
        encoding="utf-8",
    )
    runner = WorkflowRunner(runs_directory=tmp_path / ".agentforge/runs")

    with pytest.raises(WorkflowExecutionError, match="missing required state input") as error:
        runner.run(workflow_path, "Demonstrate failure handling")

    assert error.value.run_directory is not None
    trace_path = error.value.run_directory / "trace.json"
    saved_trace = json.loads(trace_path.read_text(encoding="utf-8"))
    assert saved_trace == [
        {
            "agent": "blocked",
            "error_message": "missing required state input 'missing_key'",
            "input_keys": ["missing_key"],
            "output_key": "blocked_plan",
            "status": "failed",
            "timestamp": saved_trace[0]["timestamp"],
        }
    ]
