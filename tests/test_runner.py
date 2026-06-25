import inspect
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from agentforge.config.schemas import AgentConfig
from agentforge.core.responses import AgentResponseProcessor, ProcessedAgentResponse
from agentforge.core.runner import WorkflowExecutionError, WorkflowRunner
from agentforge.llm import (
    AgentInvocation,
    AgentResponse,
    LLMProvider,
    MockLLMProvider,
    OpenAICompatibleProvider,
)
from agentforge.patches import PatchProposal

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_basic_workflow_run_uses_current_directory_for_project_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(PROJECT_ROOT / "examples/sample_project")
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
    assert result.tool_calls
    assert any(
        record["tool"] == "list_files" and "src/app.py" in record["output_preview"]
        for record in result.tool_calls
    )

    expected_files = {
        "input.txt",
        "patch_manifest.json",
        "patches",
        "state.json",
        "trace.json",
        "tool_calls.json",
        "llm_calls.json",
        "final_report.md",
    }
    assert {path.name for path in result.run_directory.iterdir()} == expected_files

    saved_state = json.loads((result.run_directory / "state.json").read_text(encoding="utf-8"))
    saved_trace = json.loads((result.run_directory / "trace.json").read_text(encoding="utf-8"))
    saved_tool_calls = json.loads(
        (result.run_directory / "tool_calls.json").read_text(encoding="utf-8")
    )
    saved_llm_calls = json.loads(
        (result.run_directory / "llm_calls.json").read_text(encoding="utf-8")
    )
    patch_manifest = json.loads(
        (result.run_directory / "patch_manifest.json").read_text(encoding="utf-8")
    )
    final_report = (result.run_directory / "final_report.md").read_text(encoding="utf-8")

    assert saved_state == result.state
    assert saved_trace == result.trace_events
    assert saved_tool_calls == result.tool_calls
    assert saved_llm_calls == result.llm_calls
    assert [call["agent"] for call in saved_llm_calls] == [
        "planner",
        "frontend",
        "backend",
        "testing",
        "reviewer",
    ]
    assert all(call["provider"] == "mock" for call in saved_llm_calls)
    assert all(call["model"] == "mock-deterministic-v1" for call in saved_llm_calls)
    assert saved_llm_calls[0]["response_preview"] == result.state["plan"]
    assert "## System Prompt" in saved_llm_calls[0]["prompt_preview"]
    assert saved_llm_calls[0]["metadata"] == {"deterministic": True, "offline": True}
    assert "inputs" not in saved_llm_calls[0]
    assert "prompt" not in saved_llm_calls[0]
    assert "response_content" not in saved_llm_calls[0]
    assert "response_metadata" not in saved_llm_calls[0]
    assert patch_manifest == result.patch_proposals
    assert [proposal["agent_name"] for proposal in patch_manifest] == [
        "frontend",
        "backend",
        "testing",
    ]
    assert [proposal["target_file"] for proposal in patch_manifest] == [
        "src/models.py",
        "src/app.py",
        "tests/test_app.py",
    ]
    for proposal in patch_manifest:
        patch_path = result.run_directory / proposal["patch_file"]
        assert proposal["status"] == "proposed"
        assert not proposal["target_file"].startswith("proposed/")
        assert proposal["patch_file"].startswith("patches/")
        assert patch_path.parent == result.run_directory / "patches"
        assert patch_path.exists()
        patch_text = patch_path.read_text(encoding="utf-8")
        assert patch_text.startswith("diff --git")
        assert f"--- a/{proposal['target_file']}" in patch_text
        assert f"+++ b/{proposal['target_file']}" in patch_text
        assert proposal["patch_file"] in final_report
    assert "basic_feature" in final_report
    assert "Add a todo endpoint to a FastAPI app" in final_report
    assert "Patch Proposals" in final_report
    for agent_name in ["planner", "frontend", "backend", "testing", "reviewer"]:
        assert f"### {agent_name}" in final_report


def test_workflow_run_with_project_root_uses_provided_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    runner = WorkflowRunner(runs_directory=tmp_path / ".agentforge/runs")

    result = runner.run(
        PROJECT_ROOT / "examples/workflows/basic_feature.yaml",
        "Add a todo endpoint to a FastAPI app",
        project_root=PROJECT_ROOT / "examples/sample_project",
    )

    assert result.tool_calls
    assert any(record["tool"] == "inspect_tree" for record in result.tool_calls)
    assert any(record["tool"] == "list_files" for record in result.tool_calls)
    assert any(
        record["tool"] == "list_files" and "src/app.py" in record["output_preview"]
        for record in result.tool_calls
    )
    assert all(record["status"] == "success" for record in result.tool_calls)
    assert "tool_context" in result.state["plan"]

    tool_calls_path = result.run_directory / "tool_calls.json"
    saved_tool_calls = json.loads(tool_calls_path.read_text(encoding="utf-8"))
    assert saved_tool_calls == result.tool_calls


def test_workflow_run_with_no_project_context_writes_empty_tool_calls(tmp_path: Path) -> None:
    runner = WorkflowRunner(runs_directory=tmp_path / ".agentforge/runs")

    result = runner.run(
        PROJECT_ROOT / "examples/workflows/basic_feature.yaml",
        "Add a todo endpoint to a FastAPI app",
        use_project_context=False,
    )

    assert result.tool_calls == []
    assert "tool_context" not in result.state["plan"]
    tool_calls_path = result.run_directory / "tool_calls.json"
    assert json.loads(tool_calls_path.read_text(encoding="utf-8")) == []
    llm_calls_path = result.run_directory / "llm_calls.json"
    llm_calls = json.loads(llm_calls_path.read_text(encoding="utf-8"))
    assert len(llm_calls) == 5
    assert "inputs" not in llm_calls[0]
    assert "tool_context" not in llm_calls[0]["input_keys"]
    patch_manifest_path = result.run_directory / "patch_manifest.json"
    assert patch_manifest_path.exists()


def test_mock_provider_returns_agent_response() -> None:
    invocation = AgentInvocation(
        agent_name="planner",
        description="Plans work.",
        system_prompt="Produce a plan.",
        input_keys=["user_request"],
        output_key="plan",
        inputs={"user_request": "Plan a todo endpoint"},
        prompt="prompt text",
    )

    response = MockLLMProvider().generate(invocation)

    assert isinstance(response, AgentResponse)
    assert response.provider == "mock"
    assert response.model == "mock-deterministic-v1"
    assert response.metadata == {"deterministic": True, "offline": True}
    assert response.patch_proposals == []
    assert response.tool_requests == []
    assert response.decisions is None
    assert response.content == (
        "Mock output from planner\n\nInputs:\n- user_request: Plan a todo endpoint"
    )


def test_agent_response_can_carry_future_action_fields() -> None:
    response = AgentResponse(
        content="Ready",
        provider="mock",
        model="mock-deterministic-v1",
        patch_proposals=[{"id": "future-patch"}],
        tool_requests=[{"name": "future-tool"}],
        decisions={"next_action": "future"},
    )

    assert response.patch_proposals == [{"id": "future-patch"}]
    assert response.tool_requests == [{"name": "future-tool"}]
    assert response.decisions == {"next_action": "future"}


def test_workflow_runner_builds_agent_invocations_for_provider(tmp_path: Path) -> None:
    provider = RecordingProvider()
    runner = WorkflowRunner(
        llm_provider=provider,
        runs_directory=tmp_path / ".agentforge/runs",
    )

    result = runner.run(
        PROJECT_ROOT / "examples/workflows/basic_feature.yaml",
        "Add a todo endpoint to a FastAPI app",
        use_project_context=False,
    )

    assert [invocation.agent_name for invocation in provider.invocations] == [
        "planner",
        "frontend",
        "backend",
        "testing",
        "reviewer",
    ]
    first_invocation = provider.invocations[0]
    assert first_invocation.output_key == "plan"
    assert first_invocation.inputs == {
        "user_request": "Add a todo endpoint to a FastAPI app"
    }
    assert first_invocation.prompt.startswith("# Agent\nplanner\n")
    assert "## System Prompt" in first_invocation.prompt
    assert result.state["plan"] == "Provider output from planner"
    assert all(call["provider"] == "recording" for call in result.llm_calls)
    assert all(call["model"] == "recording-model" for call in result.llm_calls)


def test_workflow_runner_delegates_response_processing(tmp_path: Path) -> None:
    response_processor = RecordingResponseProcessor()
    runner = WorkflowRunner(
        llm_provider=RecordingProvider(),
        response_processor=response_processor,
        runs_directory=tmp_path / ".agentforge/runs",
    )

    result = runner.run(
        PROJECT_ROOT / "examples/workflows/basic_feature.yaml",
        "Add a todo endpoint to a FastAPI app",
        use_project_context=False,
    )

    assert response_processor.agents == [
        "planner",
        "frontend",
        "backend",
        "testing",
        "reviewer",
    ]
    assert [proposal["id"] for proposal in result.patch_proposals] == [
        "processor-backend"
    ]


def test_workflow_runner_does_not_synthesize_patches_directly() -> None:
    source = inspect.getsource(WorkflowRunner)

    assert "produces_patches" not in source
    assert "patch_generator.create" not in source
    assert "DeterministicPatchGenerator" not in source


def test_response_processor_falls_back_to_deterministic_patches_for_mock_response() -> None:
    patch_generator = CustomPatchGenerator()
    processor = AgentResponseProcessor(patch_generator=patch_generator)
    response = AgentResponse(
        content="Backend output",
        provider="mock",
        model="mock-deterministic-v1",
    )
    agent_config = AgentConfig(
        name="backend",
        description="Builds backend changes.",
        system_prompt="Implement backend changes.",
        allowed_tools=[],
        input_keys=["plan"],
        output_key="backend_plan",
        produces_patches=True,
    )

    processed = processor.process(
        agent_config,
        response,
        patch_sequence=2,
        patch_id_prefix="cycle1_",
    )

    assert processed.content == "Backend output"
    assert patch_generator.sequences == [2]
    assert len(processed.patch_proposals) == 1
    assert processed.patch_proposals[0].id == "cycle1_custom-2"
    assert processed.patch_proposals[0].patch_file == "patches/cycle1_custom-2.diff"


def test_response_processor_uses_parsed_llm_patches_for_real_provider() -> None:
    patch_generator = CustomPatchGenerator()
    processor = AgentResponseProcessor(patch_generator=patch_generator)
    response = AgentResponse(
        content=_llm_patch_content("src/app.py", "Add health endpoint"),
        provider="openai-compatible",
        model="qwen2.5-coder:1.5b",
    )

    processed = processor.process(
        _patch_agent_config(),
        response,
        patch_sequence=2,
    )

    assert patch_generator.sequences == []
    assert len(processed.patch_proposals) == 1
    proposal = processed.patch_proposals[0]
    assert proposal.id == "002-backend"
    assert proposal.patch_file == "patches/002-backend.diff"
    assert proposal.title == "Add health endpoint"
    assert proposal.target_file == "src/app.py"
    assert "diff --git a/src/app.py b/src/app.py" in proposal.diff


def test_response_processor_returns_no_patches_for_real_provider_without_patch_block() -> None:
    patch_generator = CustomPatchGenerator()
    processor = AgentResponseProcessor(patch_generator=patch_generator)
    response = AgentResponse(
        content="Backend implementation plan without a structured patch artifact.",
        provider="openai-compatible",
        model="qwen2.5-coder:1.5b",
    )

    processed = processor.process(
        _patch_agent_config(),
        response,
        patch_sequence=2,
    )

    assert processed.patch_proposals == []
    assert patch_generator.sequences == []


def test_response_processor_prefixes_parsed_llm_patch_ids() -> None:
    processor = AgentResponseProcessor()
    response = AgentResponse(
        content=_llm_patch_content("src/app.py", "Add health endpoint"),
        provider="openai-compatible",
        model="qwen2.5-coder:1.5b",
    )

    processed = processor.process(
        _patch_agent_config(),
        response,
        patch_sequence=2,
        patch_id_prefix="cycle1_",
    )

    assert [proposal.id for proposal in processed.patch_proposals] == [
        "cycle1_002-backend"
    ]
    assert [proposal.patch_file for proposal in processed.patch_proposals] == [
        "patches/cycle1_002-backend.diff"
    ]


def test_workflow_runner_accepts_an_explicit_patch_generator(tmp_path: Path) -> None:
    patch_generator = CustomPatchGenerator()
    runner = WorkflowRunner(
        patch_generator=patch_generator,
        runs_directory=tmp_path / ".agentforge/runs",
    )

    result = runner.run(
        PROJECT_ROOT / "examples/workflows/basic_feature.yaml",
        "Add a todo endpoint to a FastAPI app",
        use_project_context=False,
    )

    assert patch_generator.sequences == [1, 2, 3]
    assert [proposal["target_file"] for proposal in result.patch_proposals] == [
        "custom/1.txt",
        "custom/2.txt",
        "custom/3.txt",
    ]


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
    patch_manifest_path = error.value.run_directory / "patch_manifest.json"
    assert json.loads(patch_manifest_path.read_text(encoding="utf-8")) == []
    llm_calls_path = error.value.run_directory / "llm_calls.json"
    assert json.loads(llm_calls_path.read_text(encoding="utf-8")) == []


def test_provider_errors_write_sanitized_workflow_artifacts(tmp_path: Path) -> None:
    provider = OpenAICompatibleProvider(
        api_key="sk-runner-secret",
        model="request-model",
        transport=SecretFailingTransport(),
    )
    runner = WorkflowRunner(
        llm_provider=provider,
        runs_directory=tmp_path / ".agentforge/runs",
    )

    with pytest.raises(WorkflowExecutionError) as error:
        runner.run(
            PROJECT_ROOT / "examples/workflows/basic_feature.yaml",
            "Add a todo endpoint",
            use_project_context=False,
        )

    assert "sk-runner-secret" not in str(error.value)
    assert error.value.run_directory is not None
    trace_text = (error.value.run_directory / "trace.json").read_text(encoding="utf-8")
    llm_calls_text = (error.value.run_directory / "llm_calls.json").read_text(
        encoding="utf-8"
    )
    final_report = (error.value.run_directory / "final_report.md").read_text(
        encoding="utf-8"
    )
    assert "sk-runner-secret" not in trace_text
    assert "sk-runner-secret" not in llm_calls_text
    assert "sk-runner-secret" not in final_report
    assert "[REDACTED]" in trace_text


def test_patch_manifest_contains_empty_list_when_no_patches_are_generated(tmp_path: Path) -> None:
    agent_path = tmp_path / "planner.yaml"
    agent_path.write_text(
        """
name: planner
description: Produces a plan only.
system_prompt: Produce a plan.
allowed_tools: []
input_keys:
  - user_request
output_key: plan
""".strip(),
        encoding="utf-8",
    )
    workflow_path = tmp_path / "planning-workflow.yaml"
    workflow_path.write_text(
        """
name: planning_only
description: Demonstrates a workflow with no patch-producing agents.
agents:
  - planner.yaml
""".strip(),
        encoding="utf-8",
    )
    runner = WorkflowRunner(runs_directory=tmp_path / ".agentforge/runs")

    result = runner.run(
        workflow_path,
        "Plan a todo endpoint",
        use_project_context=False,
    )

    patch_manifest_path = result.run_directory / "patch_manifest.json"
    patch_manifest = json.loads(patch_manifest_path.read_text(encoding="utf-8"))
    final_report = (result.run_directory / "final_report.md").read_text(encoding="utf-8")

    assert patch_manifest == []
    assert result.patch_proposals == []
    assert (result.run_directory / "patches").exists()
    assert list((result.run_directory / "patches").iterdir()) == []
    assert "No patch proposals were generated." in final_report


def test_workflow_run_does_not_modify_sample_project_files(tmp_path: Path) -> None:
    sample_project = PROJECT_ROOT / "examples/sample_project"
    before = _snapshot_project_files(sample_project)
    runner = WorkflowRunner(runs_directory=tmp_path / ".agentforge/runs")

    runner.run(
        PROJECT_ROOT / "examples/workflows/basic_feature.yaml",
        "Add a todo endpoint to a FastAPI app",
        project_root=sample_project,
    )

    assert _snapshot_project_files(sample_project) == before


def _snapshot_project_files(project_root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(project_root).as_posix(): path.read_bytes()
        for path in project_root.rglob("*")
        if path.is_file()
    }


class CustomPatchGenerator:
    def __init__(self) -> None:
        self.sequences: list[int] = []

    def create(self, _agent_config, sequence: int) -> PatchProposal:
        self.sequences.append(sequence)
        target_file = f"custom/{sequence}.txt"
        diff = "\n".join(
            [
                f"diff --git a/{target_file} b/{target_file}",
                f"--- a/{target_file}",
                f"+++ b/{target_file}",
                "@@ -0,0 +1 @@",
                f"+generated {sequence}",
            ]
        )
        return PatchProposal(
            id=f"custom-{sequence}",
            agent_name="custom",
            title="Custom patch",
            description="Generated by a test patch generator.",
            target_file=target_file,
            patch_file=f"patches/custom-{sequence}.diff",
            status="proposed",
            diff=diff,
        )


def _patch_agent_config() -> AgentConfig:
    return AgentConfig(
        name="backend",
        description="Builds backend changes.",
        system_prompt="Implement backend changes.",
        allowed_tools=[],
        input_keys=["plan"],
        output_key="backend_plan",
        produces_patches=True,
    )


def _llm_patch_content(target_file: str, title: str) -> str:
    return f"""
Backend implementation plan.

```agentforge-patch
target_file: {target_file}
title: {title}
description: Adds a GET /health endpoint.
---BEGIN DIFF---
diff --git a/{target_file} b/{target_file}
--- a/{target_file}
+++ b/{target_file}
@@ -1,3 +1,7 @@
+def health():
+    return {{"status": "ok"}}
---END DIFF---
```
""".strip()


class RecordingProvider(LLMProvider):
    def __init__(self) -> None:
        self.invocations: list[AgentInvocation] = []

    def generate(self, invocation: AgentInvocation) -> AgentResponse:
        self.invocations.append(invocation)
        return AgentResponse(
            content=f"Provider output from {invocation.agent_name}",
            provider="recording",
            model="recording-model",
            metadata={"test": True},
        )


class RecordingResponseProcessor(AgentResponseProcessor):
    def __init__(self) -> None:
        self.agents: list[str] = []

    def process(
        self,
        agent_config: AgentConfig,
        response: AgentResponse,
        *,
        patch_sequence: int,
        patch_id_prefix: str = "",
    ) -> ProcessedAgentResponse:
        self.agents.append(agent_config.name)
        patch_proposals: list[PatchProposal] = []
        if agent_config.name == "backend":
            patch_proposals.append(
                PatchProposal(
                    id="processor-backend",
                    agent_name="backend",
                    title="Processor patch",
                    description="Created by the response processor.",
                    target_file="custom/backend.txt",
                    patch_file="patches/processor-backend.diff",
                    status="proposed",
                    diff="\n".join(
                        [
                            "diff --git a/custom/backend.txt b/custom/backend.txt",
                            "--- a/custom/backend.txt",
                            "+++ b/custom/backend.txt",
                            "@@ -0,0 +1 @@",
                            "+processor",
                        ]
                    ),
                )
            )
        return ProcessedAgentResponse(
            content=response.content,
            patch_proposals=patch_proposals,
            tool_requests=[],
            decisions=None,
        )


class SecretFailingTransport:
    def __call__(
        self,
        _url: str,
        _headers: Mapping[str, str],
        _payload: Mapping[str, Any],
        _timeout_seconds: float,
    ) -> Mapping[str, Any]:
        raise RuntimeError("provider echoed Authorization: Bearer sk-runner-secret")
