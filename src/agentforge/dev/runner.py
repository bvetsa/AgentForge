"""Phase 6 end-to-end development pipeline orchestration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentforge.config.loader import ConfigLoadError
from agentforge.core.runner import RunResult, WorkflowExecutionError, WorkflowRunner
from agentforge.patches import PatchProposal, PatchReviewError, PatchReviewService
from agentforge.testing import TestRunError, TestRunner

REVIEWER_AGENT_NAME = "reviewer"
CUSTOMER_FACING_AGENT_NAMES = {"planner", REVIEWER_AGENT_NAME}


class DevPipelineError(RuntimeError):
    """Raised when the Phase 6 dev pipeline cannot complete."""

    def __init__(self, message: str, run_directory: Path | None = None) -> None:
        super().__init__(message)
        self.run_directory = run_directory


@dataclass(frozen=True)
class DevRunSession:
    """Prepared dev run waiting at the human approval gate."""

    user_request: str
    project_root: Path
    workflow_path: Path
    max_cycles: int
    run_result: RunResult
    cycle_number: int
    planner_summary: str
    selected_agents: list[str]
    generated_patches: list[dict[str, Any]]

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
    """Completed Phase 6 dev pipeline result."""

    run_id: str
    run_directory: Path
    user_request: str
    project_root: Path
    workflow_path: Path
    status: str
    cycle_number: int
    planner_summary: str
    selected_agents: list[str]
    generated_patches: list[dict[str, Any]]
    applied_patches: list[dict[str, Any]]
    test_status: str
    test_command: list[str] | None
    planner_decisions: list[dict[str, Any]]
    final_verdict: str


class DevPipelineRunner:
    """Coordinate one human-approved end-to-end development run."""

    def __init__(
        self,
        *,
        workflow_runner: WorkflowRunner | None = None,
        patch_review_service: PatchReviewService | None = None,
        test_runner: TestRunner | None = None,
        runs_directory: str | Path = ".agentforge/runs",
    ) -> None:
        self.runs_directory = Path(runs_directory)
        self.workflow_runner = workflow_runner or WorkflowRunner(
            runs_directory=self.runs_directory
        )
        self.patch_review_service = patch_review_service or PatchReviewService(
            runs_directory=self.runs_directory
        )
        self.test_runner = test_runner or TestRunner()

    def prepare(
        self,
        *,
        user_request: str,
        project_root: str | Path,
        workflow_path: str | Path,
        max_cycles: int = 1,
    ) -> DevRunSession:
        """Run the pre-review workflow stages and stop for human approval."""
        if max_cycles <= 0:
            raise DevPipelineError("max_cycles must be greater than 0.")

        resolved_project_root = Path(project_root).resolve()
        resolved_workflow_path = Path(workflow_path).resolve(strict=False)

        try:
            run_result = self.workflow_runner.run(
                resolved_workflow_path,
                user_request,
                project_root=resolved_project_root,
                stop_before_agent_names={REVIEWER_AGENT_NAME},
            )
        except (ConfigLoadError, WorkflowExecutionError) as error:
            run_directory = getattr(error, "run_directory", None)
            raise DevPipelineError(str(error), run_directory=run_directory) from error

        session = DevRunSession(
            user_request=user_request,
            project_root=resolved_project_root,
            workflow_path=resolved_workflow_path,
            max_cycles=max_cycles,
            run_result=run_result,
            cycle_number=1,
            planner_summary=_planner_summary(run_result.state),
            selected_agents=_selected_workflow_agents(run_result.trace_events),
            generated_patches=_generated_patch_summaries(run_result.patch_proposals),
        )
        self._write_summary(
            session=session,
            status="awaiting_approval",
            applied_patches=[],
            test_status="not_run",
            test_command=None,
            planner_decisions=[],
            final_verdict="",
        )
        return session

    def finish(self, session: DevRunSession, *, approved: bool) -> DevRunResult:
        """Complete a prepared dev run after the approval decision."""
        if not approved:
            decision = _approval_declined_decision(session.cycle_number)
            final_verdict = "No changes were applied. Artifacts were saved for review."
            result = self._build_result(
                session=session,
                status="not_applied",
                applied_patches=[],
                test_status="not_run",
                test_command=None,
                planner_decisions=[decision],
                final_verdict=final_verdict,
            )
            self._write_result_summary(result)
            self._append_dev_report(result)
            return result

        try:
            applied_patches = self._apply_proposed_patches(session)
        except PatchReviewError as error:
            decision = {
                "cycle": session.cycle_number,
                "approval": "approved",
                "test_status": "not_run",
                "next_action": "stop_on_apply_error",
                "notes": [f"Patch application failed: {error}"],
            }
            final_verdict = f"Patch application failed: {error}"
            result = self._build_result(
                session=session,
                status="apply_failed",
                applied_patches=[],
                test_status="not_run",
                test_command=None,
                planner_decisions=[decision],
                final_verdict=final_verdict,
            )
            self._write_result_summary(result)
            self._append_dev_report(result)
            raise DevPipelineError(final_verdict, run_directory=session.run_directory) from error

        test_status, test_command, test_error = self._run_tests(session)
        decision = _test_result_decision(
            cycle_number=session.cycle_number,
            test_status=test_status,
            max_cycles=session.max_cycles,
            test_error=test_error,
        )
        final_verdict = _final_verdict_for_tests(
            test_status=test_status,
            max_cycles_reached=session.cycle_number >= session.max_cycles,
            test_error=test_error,
        )
        result = self._build_result(
            session=session,
            status=_status_for_test_status(test_status),
            applied_patches=applied_patches,
            test_status=test_status,
            test_command=test_command,
            planner_decisions=[decision],
            final_verdict=final_verdict,
        )
        self._write_result_summary(result)
        self._append_dev_report(result)
        return result

    def _apply_proposed_patches(
        self,
        session: DevRunSession,
    ) -> list[dict[str, Any]]:
        proposals = self.patch_review_service.list_patches(session.run_id)
        applied_patches: list[dict[str, Any]] = []
        for proposal in proposals:
            if proposal.status != "proposed":
                continue
            target_path = self.patch_review_service.apply_patch(
                session.run_id,
                proposal.id,
                session.project_root,
            )
            summary = _proposal_summary(proposal)
            summary["status"] = "applied"
            summary["applied_path"] = str(target_path.resolve(strict=False))
            applied_patches.append(summary)
        return applied_patches

    def _run_tests(
        self,
        session: DevRunSession,
    ) -> tuple[str, list[str] | None, str | None]:
        try:
            test_result = self.test_runner.run(
                project_root=session.project_root,
                artifact_directory=session.run_directory,
            )
        except TestRunError as error:
            payload = _read_test_results(session.run_directory)
            selected_command = payload.get("selected_command")
            test_command = selected_command if _is_command_list(selected_command) else None
            test_status = payload.get("status")
            if not isinstance(test_status, str):
                test_status = "error"
            return test_status, test_command, str(error)

        return test_result.status, test_result.selected_command, None

    def _build_result(
        self,
        *,
        session: DevRunSession,
        status: str,
        applied_patches: list[dict[str, Any]],
        test_status: str,
        test_command: list[str] | None,
        planner_decisions: list[dict[str, Any]],
        final_verdict: str,
    ) -> DevRunResult:
        return DevRunResult(
            run_id=session.run_id,
            run_directory=session.run_directory,
            user_request=session.user_request,
            project_root=session.project_root,
            workflow_path=session.workflow_path,
            status=status,
            cycle_number=session.cycle_number,
            planner_summary=session.planner_summary,
            selected_agents=session.selected_agents,
            generated_patches=session.generated_patches,
            applied_patches=applied_patches,
            test_status=test_status,
            test_command=test_command,
            planner_decisions=planner_decisions,
            final_verdict=final_verdict,
        )

    def _write_result_summary(self, result: DevRunResult) -> None:
        _write_dev_summary_file(
            result.run_directory,
            _summary_payload(
                run_id=result.run_id,
                user_request=result.user_request,
                project_root=result.project_root,
                workflow_path=result.workflow_path,
                cycle_number=result.cycle_number,
                planner_summary=result.planner_summary,
                selected_agents=result.selected_agents,
                generated_patches=result.generated_patches,
                status=result.status,
                applied_patches=result.applied_patches,
                test_status=result.test_status,
                test_command=result.test_command,
                planner_decisions=result.planner_decisions,
                final_verdict=result.final_verdict,
            ),
        )

    def _write_summary(
        self,
        *,
        session: DevRunSession,
        status: str,
        applied_patches: list[dict[str, Any]],
        test_status: str,
        test_command: list[str] | None,
        planner_decisions: list[dict[str, Any]],
        final_verdict: str,
    ) -> None:
        _write_dev_summary_file(
            session.run_directory,
            _summary_payload(
                run_id=session.run_id,
                user_request=session.user_request,
                project_root=session.project_root,
                workflow_path=session.workflow_path,
                cycle_number=session.cycle_number,
                planner_summary=session.planner_summary,
                selected_agents=session.selected_agents,
                generated_patches=session.generated_patches,
                status=status,
                applied_patches=applied_patches,
                test_status=test_status,
                test_command=test_command,
                planner_decisions=planner_decisions,
                final_verdict=final_verdict,
            ),
        )

    @staticmethod
    def _append_dev_report(result: DevRunResult) -> None:
        report_path = result.run_directory / "final_report.md"
        existing = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
        decision = result.planner_decisions[-1] if result.planner_decisions else {}
        notes = decision.get("notes", [])
        note_lines = [f"- {note}" for note in notes if isinstance(note, str)]
        if decision.get("next_action"):
            note_lines.append(f"- Next action: `{decision['next_action']}`")

        section = [
            "",
            "## AgentForge Dev Pipeline",
            "",
            f"- Status: `{result.status}`",
            f"- Test status: `{result.test_status}`",
            "",
            "### Planner Decision",
            "",
            *(note_lines or ["No planner decision was recorded."]),
            "",
            "### Final Verdict",
            "",
            result.final_verdict,
            "",
        ]
        section_text = "\n".join(section)
        report_path.write_text(
            f"{existing.rstrip()}\n{section_text}",
            encoding="utf-8",
        )


def _planner_summary(state: dict[str, str]) -> str:
    plan = state.get("plan", "")
    for line in plan.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return "No planner output recorded."


def _selected_workflow_agents(trace_events: list[dict[str, object]]) -> list[str]:
    return [
        str(event["agent"])
        for event in trace_events
        if event.get("agent") not in CUSTOMER_FACING_AGENT_NAMES
    ]


def _generated_patch_summaries(
    patch_proposals: list[dict[str, object]],
) -> list[dict[str, Any]]:
    return [
        {
            "id": str(proposal["id"]),
            "agent_name": str(proposal["agent_name"]),
            "target_file": str(proposal["target_file"]),
            "status": str(proposal["status"]),
            "title": str(proposal["title"]),
        }
        for proposal in patch_proposals
    ]


def _proposal_summary(proposal: PatchProposal) -> dict[str, Any]:
    return {
        "id": proposal.id,
        "agent_name": proposal.agent_name,
        "target_file": proposal.target_file,
        "status": proposal.status,
        "title": proposal.title,
    }


def _summary_payload(
    *,
    run_id: str,
    user_request: str,
    project_root: Path,
    workflow_path: Path,
    cycle_number: int,
    planner_summary: str,
    selected_agents: list[str],
    generated_patches: list[dict[str, Any]],
    status: str,
    applied_patches: list[dict[str, Any]],
    test_status: str,
    test_command: list[str] | None,
    planner_decisions: list[dict[str, Any]],
    final_verdict: str,
) -> dict[str, Any]:
    cycle_payload = {
        "approval": _cycle_approval_status(planner_decisions),
        "cycle": cycle_number,
        "planner_summary": planner_summary,
        "selected_agents": selected_agents,
        "generated_patches": generated_patches,
        "applied_patches": applied_patches,
        "test_status": test_status,
        "test_command": test_command,
        "planner_decision": planner_decisions[-1] if planner_decisions else None,
        "final_verdict": final_verdict,
    }
    return {
        "run_id": run_id,
        "user_request": user_request,
        "project_root": str(project_root.resolve(strict=False)),
        "workflow_path": str(workflow_path),
        "status": status,
        "cycles": [cycle_payload],
        "generated_patches": generated_patches,
        "applied_patches": applied_patches,
        "test_status": test_status,
        "planner_decisions": planner_decisions,
        "final_verdict": final_verdict,
    }


def _cycle_approval_status(planner_decisions: list[dict[str, Any]]) -> str:
    if not planner_decisions:
        return "pending"
    approval = planner_decisions[-1].get("approval")
    return approval if isinstance(approval, str) else "unknown"


def _write_dev_summary_file(run_directory: Path, payload: dict[str, Any]) -> None:
    summary_path = run_directory / "dev_run_summary.json"
    summary_path.write_text(
        f"{json.dumps(payload, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )


def _approval_declined_decision(cycle_number: int) -> dict[str, Any]:
    return {
        "cycle": cycle_number,
        "approval": "declined",
        "test_status": "not_run",
        "next_action": "stop_without_reviewer",
        "notes": [
            "Human approval was not granted.",
            "No patches were applied.",
            "Tests were not run.",
        ],
    }


def _test_result_decision(
    *,
    cycle_number: int,
    test_status: str,
    max_cycles: int,
    test_error: str | None,
) -> dict[str, Any]:
    if test_status == "passed":
        notes = ["Tests passed."]
    else:
        notes = [
            f"Tests ended with status '{test_status}'.",
            "Another cycle/debugger loop is needed, but automatic repair is deferred to Phase 7.",
        ]
        if test_error:
            notes.append(test_error)
    if cycle_number >= max_cycles:
        notes.append("Max cycles reached; returning a final user-facing verdict.")

    return {
        "cycle": cycle_number,
        "approval": "approved",
        "test_status": test_status,
        "next_action": "send_to_reviewer",
        "notes": notes,
    }


def _final_verdict_for_tests(
    *,
    test_status: str,
    max_cycles_reached: bool,
    test_error: str | None,
) -> str:
    if test_status == "passed":
        return "Changes applied successfully and tests passed."

    if test_status == "no_command_detected":
        base = "Changes were applied, but no safe test command was detected."
    elif test_status == "failed":
        base = "Changes were applied, but tests failed."
    elif test_status == "timeout":
        base = "Changes were applied, but tests timed out."
    else:
        base = f"Changes were applied, but test status is '{test_status}'."

    details = " Automatic repair is deferred to Phase 7."
    if max_cycles_reached:
        details += " Max cycles reached for this dev run."
    if test_error:
        details += f" Test runner note: {test_error}"
    return f"{base}{details}"


def _status_for_test_status(test_status: str) -> str:
    if test_status == "passed":
        return "tests_passed"
    if test_status == "no_command_detected":
        return "tests_not_detected"
    if test_status == "timeout":
        return "tests_timeout"
    if test_status == "failed":
        return "tests_failed"
    return "tests_incomplete"


def _read_test_results(run_directory: Path) -> dict[str, Any]:
    results_path = run_directory / "test_results.json"
    if not results_path.exists():
        return {}
    try:
        payload = json.loads(results_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _is_command_list(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)
