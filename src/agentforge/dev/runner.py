"""Planner-controlled iterative development pipeline orchestration."""

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
    """Raised when the dev pipeline cannot complete."""

    def __init__(self, message: str, run_directory: Path | None = None) -> None:
        super().__init__(message)
        self.run_directory = run_directory


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


class DevPipelineRunner:
    """Coordinate a planner-controlled human-approved development loop."""

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
        max_cycles: int = 3,
    ) -> DevRunSession:
        """Run the first pre-review workflow cycle and stop for human approval."""
        if max_cycles <= 0:
            raise DevPipelineError("max_cycles must be greater than 0.")

        return self._prepare_cycle(
            user_request=user_request,
            project_root=Path(project_root).resolve(),
            workflow_path=Path(workflow_path).resolve(strict=False),
            max_cycles=max_cycles,
            cycle_number=1,
            run_id=None,
            previous_testing_report=None,
            planned_focus=None,
        )

    def prepare_next_cycle(self, result: DevRunResult) -> DevRunSession:
        """Run the next workflow/coding cycle in the same dev run directory."""
        next_cycle_number = result.cycle_number + 1
        if next_cycle_number > result.max_cycles:
            raise DevPipelineError(
                "Cannot continue dev run because max_cycles has been reached.",
                run_directory=result.run_directory,
            )

        decision = result.planner_decisions[-1] if result.planner_decisions else {}
        planned_focus = decision.get("recommended_focus")
        if not isinstance(planned_focus, str):
            planned_focus = None

        return self._prepare_cycle(
            user_request=result.user_request,
            project_root=result.project_root,
            workflow_path=result.workflow_path,
            max_cycles=result.max_cycles,
            cycle_number=next_cycle_number,
            run_id=result.run_id,
            previous_testing_report=result.testing_report,
            planned_focus=planned_focus,
        )

    def finish(self, session: DevRunSession, *, approved: bool) -> DevRunResult:
        """Complete a prepared dev cycle after the approval decision."""
        if not approved:
            testing_report = _not_run_testing_report(
                "Tests were not run because human approval was declined."
            )
            decision = _approval_declined_decision(session.cycle_number, testing_report)
            final_verdict = (
                f"No changes were applied because approval was declined for cycle "
                f"{session.cycle_number}."
            )
            result = self._build_result(
                session=session,
                status="user_declined",
                applied_patches=[],
                test_status="not_run",
                test_command=None,
                testing_report=testing_report,
                planner_decisions=[decision],
                final_verdict=final_verdict,
            )
            self._write_result_summary(result)
            self._append_dev_report(result)
            return result

        if not session.generated_patches:
            testing_report = _not_run_testing_report(
                "Tests were not run because no patch proposals were generated."
            )
            decision = _no_patches_decision(session.cycle_number, testing_report)
            final_verdict = (
                "No patch proposals were generated, so the dev run cannot continue."
            )
            result = self._build_result(
                session=session,
                status="no_patches",
                applied_patches=[],
                test_status="not_run",
                test_command=None,
                testing_report=testing_report,
                planner_decisions=[decision],
                final_verdict=final_verdict,
            )
            self._write_result_summary(result)
            self._append_dev_report(result)
            return result

        try:
            applied_patches = self._apply_proposed_patches(session)
        except PatchReviewError as error:
            testing_report = _not_run_testing_report(
                "Tests were not run because patch application failed."
            )
            decision = _apply_error_decision(
                session.cycle_number,
                testing_report,
                str(error),
            )
            final_verdict = f"Patch application failed: {error}"
            result = self._build_result(
                session=session,
                status="apply_failed",
                applied_patches=[],
                test_status="not_run",
                test_command=None,
                testing_report=testing_report,
                planner_decisions=[decision],
                final_verdict=final_verdict,
            )
            self._write_result_summary(result)
            self._append_dev_report(result)
            raise DevPipelineError(final_verdict, run_directory=session.run_directory) from error

        test_status, test_command, test_error, testing_report = self._run_tests(session)
        decision = _planner_decision_for_test_report(
            cycle_number=session.cycle_number,
            test_status=test_status,
            testing_report=testing_report,
            max_cycles=session.max_cycles,
            selected_agents=session.selected_agents,
            test_error=test_error,
        )
        final_verdict = _final_verdict_for_decision(
            decision=decision,
            test_status=test_status,
            cycle_number=session.cycle_number,
            max_cycles=session.max_cycles,
            test_error=test_error,
        )
        result = self._build_result(
            session=session,
            status=_status_for_planner_decision(decision, test_status),
            applied_patches=applied_patches,
            test_status=test_status,
            test_command=test_command,
            testing_report=testing_report,
            planner_decisions=[decision],
            final_verdict=final_verdict,
        )
        self._write_result_summary(result)
        self._append_dev_report(result)
        return result

    def _prepare_cycle(
        self,
        *,
        user_request: str,
        project_root: Path,
        workflow_path: Path,
        max_cycles: int,
        cycle_number: int,
        run_id: str | None,
        previous_testing_report: dict[str, Any] | None,
        planned_focus: str | None,
    ) -> DevRunSession:
        try:
            run_result = self.workflow_runner.run(
                workflow_path,
                user_request,
                project_root=project_root,
                stop_before_agent_names={REVIEWER_AGENT_NAME},
                run_id=run_id,
                patch_id_prefix=f"cycle{cycle_number}_",
                merge_patch_manifest=True,
            )
        except (ConfigLoadError, WorkflowExecutionError) as error:
            run_directory = getattr(error, "run_directory", None)
            raise DevPipelineError(str(error), run_directory=run_directory) from error

        session = DevRunSession(
            user_request=user_request,
            project_root=project_root,
            workflow_path=workflow_path,
            max_cycles=max_cycles,
            run_result=run_result,
            cycle_number=cycle_number,
            planner_summary=_planner_summary(run_result.state),
            selected_agents=_selected_workflow_agents(run_result.trace_events),
            generated_patches=_generated_patch_summaries(run_result.patch_proposals),
            previous_testing_report=previous_testing_report,
            planned_focus=planned_focus,
        )
        self._write_summary(
            session=session,
            status="awaiting_approval",
            applied_patches=[],
            test_status="not_run",
            test_command=None,
            testing_report=_not_run_testing_report("Tests have not run for this cycle yet."),
            planner_decisions=[],
            final_verdict="",
        )
        return session

    def _apply_proposed_patches(
        self,
        session: DevRunSession,
    ) -> list[dict[str, Any]]:
        current_patch_ids = {
            str(patch["id"])
            for patch in session.generated_patches
            if "id" in patch
        }
        proposals = self.patch_review_service.list_patches(session.run_id)
        applied_patches: list[dict[str, Any]] = []
        for proposal in proposals:
            if proposal.id not in current_patch_ids or proposal.status != "proposed":
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
    ) -> tuple[str, list[str] | None, str | None, dict[str, Any]]:
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
            artifact_paths = _copy_cycle_test_artifacts(
                session.run_directory,
                session.cycle_number,
            )
            testing_report = _testing_report(
                status=test_status,
                test_command=test_command,
                test_error=str(error),
                artifact_paths=artifact_paths,
            )
            return test_status, test_command, str(error), testing_report

        artifact_paths = _copy_cycle_test_artifacts(
            session.run_directory,
            session.cycle_number,
        )
        testing_report = _testing_report(
            status=test_result.status,
            test_command=test_result.selected_command,
            test_error=None,
            artifact_paths=artifact_paths,
        )
        return test_result.status, test_result.selected_command, None, testing_report

    def _build_result(
        self,
        *,
        session: DevRunSession,
        status: str,
        applied_patches: list[dict[str, Any]],
        test_status: str,
        test_command: list[str] | None,
        testing_report: dict[str, Any],
        planner_decisions: list[dict[str, Any]],
        final_verdict: str,
    ) -> DevRunResult:
        return DevRunResult(
            run_id=session.run_id,
            run_directory=session.run_directory,
            user_request=session.user_request,
            project_root=session.project_root,
            workflow_path=session.workflow_path,
            max_cycles=session.max_cycles,
            status=status,
            cycle_number=session.cycle_number,
            planner_summary=session.planner_summary,
            selected_agents=session.selected_agents,
            generated_patches=session.generated_patches,
            applied_patches=applied_patches,
            test_status=test_status,
            test_command=test_command,
            testing_report=testing_report,
            planner_decisions=planner_decisions,
            final_verdict=final_verdict,
        )

    def _write_result_summary(self, result: DevRunResult) -> None:
        _write_dev_summary_file(
            result.run_directory,
            _summary_payload_from_result(result),
        )

    def _write_summary(
        self,
        *,
        session: DevRunSession,
        status: str,
        applied_patches: list[dict[str, Any]],
        test_status: str,
        test_command: list[str] | None,
        testing_report: dict[str, Any],
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
                max_cycles=session.max_cycles,
                cycle_number=session.cycle_number,
                planner_summary=session.planner_summary,
                selected_agents=session.selected_agents,
                generated_patches=session.generated_patches,
                status=status,
                applied_patches=applied_patches,
                test_status=test_status,
                test_command=test_command,
                testing_report=testing_report,
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
        if decision.get("recommended_focus"):
            note_lines.append(f"- Recommended focus: `{decision['recommended_focus']}`")

        section = [
            "",
            f"## AgentForge Dev Pipeline Cycle {result.cycle_number}",
            "",
            f"- Status: `{result.status}`",
            f"- Test status: `{result.test_status}`",
            "",
            "### Planner Decision",
            "",
            *(note_lines or ["No planner decision was recorded."]),
            "",
        ]
        if result.final_verdict:
            section.extend(
                [
                    "### Final Verdict",
                    "",
                    result.final_verdict,
                    "",
                ]
            )
        else:
            section.extend(
                [
                    "The planner selected another cycle; no final verdict was returned.",
                    "",
                ]
            )
        section_text = "\n".join(section)
        report_path.write_text(f"{existing.rstrip()}\n{section_text}", encoding="utf-8")


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


def _summary_payload_from_result(result: DevRunResult) -> dict[str, Any]:
    return _summary_payload(
        run_id=result.run_id,
        user_request=result.user_request,
        project_root=result.project_root,
        workflow_path=result.workflow_path,
        max_cycles=result.max_cycles,
        cycle_number=result.cycle_number,
        planner_summary=result.planner_summary,
        selected_agents=result.selected_agents,
        generated_patches=result.generated_patches,
        status=result.status,
        applied_patches=result.applied_patches,
        test_status=result.test_status,
        test_command=result.test_command,
        testing_report=result.testing_report,
        planner_decisions=result.planner_decisions,
        final_verdict=result.final_verdict,
    )


def _summary_payload(
    *,
    run_id: str,
    user_request: str,
    project_root: Path,
    workflow_path: Path,
    max_cycles: int,
    cycle_number: int,
    planner_summary: str,
    selected_agents: list[str],
    generated_patches: list[dict[str, Any]],
    status: str,
    applied_patches: list[dict[str, Any]],
    test_status: str,
    test_command: list[str] | None,
    testing_report: dict[str, Any],
    planner_decisions: list[dict[str, Any]],
    final_verdict: str,
) -> dict[str, Any]:
    decision = planner_decisions[-1] if planner_decisions else None
    cycle_payload = {
        "approval": _cycle_approval_status(planner_decisions),
        "cycle": cycle_number,
        "planner_summary": planner_summary,
        "selected_agents": selected_agents,
        "generated_patches": generated_patches,
        "applied_patches": applied_patches,
        "test_status": test_status,
        "test_command": test_command,
        "testing_report": testing_report,
        "planner_decision": decision,
        "final_verdict": final_verdict,
        "stop_reason": _stop_reason(decision),
    }
    return {
        "run_id": run_id,
        "user_request": user_request,
        "project_root": str(project_root.resolve(strict=False)),
        "workflow_path": str(workflow_path),
        "max_cycles": max_cycles,
        "status": status,
        "cycles": [cycle_payload],
        "generated_patches": generated_patches,
        "applied_patches": applied_patches,
        "test_status": test_status,
        "test_command": test_command,
        "planner_decisions": planner_decisions,
        "final_verdict": final_verdict,
    }


def _cycle_approval_status(planner_decisions: list[dict[str, Any]]) -> str:
    if not planner_decisions:
        return "pending"
    approval = planner_decisions[-1].get("approval")
    return approval if isinstance(approval, str) else "unknown"


def _stop_reason(decision: dict[str, Any] | None) -> str | None:
    if not decision:
        return None
    next_action = decision.get("next_action")
    if next_action == "continue":
        return None
    reason = decision.get("reason")
    return reason if isinstance(reason, str) else None


def _write_dev_summary_file(run_directory: Path, payload: dict[str, Any]) -> None:
    existing = _read_dev_summary_file(run_directory)
    if existing is not None and existing.get("run_id") == payload.get("run_id"):
        payload = _merge_summary_payload(existing, payload)

    summary_path = run_directory / "dev_run_summary.json"
    summary_path.write_text(
        f"{json.dumps(payload, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )


def _read_dev_summary_file(run_directory: Path) -> dict[str, Any] | None:
    summary_path = run_directory / "dev_run_summary.json"
    if not summary_path.exists():
        return None
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _merge_summary_payload(
    existing: dict[str, Any],
    current: dict[str, Any],
) -> dict[str, Any]:
    existing_cycles = existing.get("cycles")
    current_cycles = current.get("cycles")
    if not isinstance(existing_cycles, list) or not isinstance(current_cycles, list):
        return current

    cycles = _upsert_cycle(existing_cycles, current_cycles[0])
    return {
        **existing,
        **current,
        "cycles": cycles,
        "generated_patches": _aggregate_cycle_list(cycles, "generated_patches"),
        "applied_patches": _aggregate_cycle_list(cycles, "applied_patches"),
        "planner_decisions": [
            cycle["planner_decision"]
            for cycle in cycles
            if isinstance(cycle, dict) and cycle.get("planner_decision") is not None
        ],
    }


def _upsert_cycle(
    cycles: list[Any],
    current_cycle: dict[str, Any],
) -> list[dict[str, Any]]:
    current_number = current_cycle.get("cycle")
    merged: list[dict[str, Any]] = []
    replaced = False
    for cycle in cycles:
        if not isinstance(cycle, dict):
            continue
        if cycle.get("cycle") == current_number:
            merged.append(current_cycle)
            replaced = True
        else:
            merged.append(cycle)
    if not replaced:
        merged.append(current_cycle)
    return sorted(merged, key=lambda cycle: int(cycle.get("cycle", 0)))


def _aggregate_cycle_list(
    cycles: list[dict[str, Any]],
    key: str,
) -> list[dict[str, Any]]:
    aggregated: list[dict[str, Any]] = []
    for cycle in cycles:
        values = cycle.get(key)
        if not isinstance(values, list):
            continue
        aggregated.extend(value for value in values if isinstance(value, dict))
    return aggregated


def _approval_declined_decision(
    cycle_number: int,
    testing_report: dict[str, Any],
) -> dict[str, Any]:
    return {
        "cycle": cycle_number,
        "approval": "declined",
        "test_status": "not_run",
        "testing_report": testing_report,
        "next_action": "stopped_user_declined",
        "reason": "Human approval was not granted.",
        "notes": [
            "Human approval was not granted.",
            "No patches were applied.",
            "Tests were not run.",
        ],
    }


def _no_patches_decision(
    cycle_number: int,
    testing_report: dict[str, Any],
) -> dict[str, Any]:
    return {
        "cycle": cycle_number,
        "approval": "not_required",
        "test_status": "not_run",
        "testing_report": testing_report,
        "next_action": "return_final_verdict",
        "reason": "No patch proposals were generated.",
        "notes": [
            "No patch proposals were generated.",
            "Tests were not run.",
        ],
    }


def _apply_error_decision(
    cycle_number: int,
    testing_report: dict[str, Any],
    error_message: str,
) -> dict[str, Any]:
    return {
        "cycle": cycle_number,
        "approval": "approved",
        "test_status": "not_run",
        "testing_report": testing_report,
        "next_action": "return_final_verdict",
        "reason": "Patch application failed.",
        "notes": [
            f"Patch application failed: {error_message}",
            "Tests were not run.",
        ],
    }


def _planner_decision_for_test_report(
    *,
    cycle_number: int,
    test_status: str,
    testing_report: dict[str, Any],
    max_cycles: int,
    selected_agents: list[str],
    test_error: str | None,
) -> dict[str, Any]:
    if test_status == "passed":
        next_action = "return_final_verdict"
        reason = "Tests passed."
        notes = [reason]
        recommended_focus = None
        next_agents: list[str] = []
    elif cycle_number < max_cycles:
        next_action = "continue"
        reason = "Tests failed and max cycles have not been reached."
        recommended_focus = _recommended_focus(testing_report)
        next_agents = _next_cycle_agents(selected_agents)
        notes = [
            reason,
            f"Focus: {recommended_focus}.",
        ]
    else:
        next_action = "stopped_max_cycles"
        reason = "Tests failed and max cycles were reached."
        recommended_focus = _recommended_focus(testing_report)
        next_agents = []
        notes = [
            reason,
            f"Focus: {recommended_focus}.",
        ]

    if test_status != "passed":
        notes.insert(0, f"Tests ended with status '{test_status}'.")
    if test_error:
        notes.append(test_error)

    return {
        "cycle": cycle_number,
        "approval": "approved",
        "test_status": test_status,
        "testing_report": testing_report,
        "next_action": next_action,
        "reason": reason,
        "recommended_focus": recommended_focus,
        "selected_agents": next_agents,
        "notes": notes,
    }


def _next_cycle_agents(selected_agents: list[str]) -> list[str]:
    preferred = [agent for agent in ("backend", "testing") if agent in selected_agents]
    if preferred:
        return preferred
    return selected_agents[-2:]


def _recommended_focus(testing_report: dict[str, Any]) -> str:
    focus = testing_report.get("recommended_focus")
    return focus if isinstance(focus, str) and focus else "implementation"


def _final_verdict_for_decision(
    *,
    decision: dict[str, Any],
    test_status: str,
    cycle_number: int,
    max_cycles: int,
    test_error: str | None,
) -> str:
    next_action = decision.get("next_action")
    if next_action == "continue":
        return ""
    if next_action == "return_final_verdict" and test_status == "passed":
        return "Changes applied successfully and tests passed."
    if next_action == "stopped_max_cycles":
        base = (
            f"Tests still failed after {cycle_number} cycle(s); "
            f"max cycles ({max_cycles}) were reached."
        )
        if test_error:
            return f"{base} Test runner note: {test_error}"
        return base
    if next_action == "return_final_verdict":
        reason = decision.get("reason")
        return reason if isinstance(reason, str) else "Dev run stopped."
    return "Dev run stopped."


def _status_for_planner_decision(decision: dict[str, Any], test_status: str) -> str:
    next_action = decision.get("next_action")
    if next_action == "continue":
        return "continuing"
    if next_action == "stopped_max_cycles":
        return "max_cycles_reached"
    if test_status == "passed":
        return "tests_passed"
    if test_status == "no_command_detected":
        return "tests_not_detected"
    if test_status == "timeout":
        return "tests_timeout"
    if test_status == "failed":
        return "tests_failed"
    return "tests_incomplete"


def _testing_report(
    *,
    status: str,
    test_command: list[str] | None,
    test_error: str | None,
    artifact_paths: dict[str, str],
) -> dict[str, Any]:
    report_status = _testing_report_status(status)
    report = {
        "status": report_status,
        "summary": _testing_report_summary(status, test_error),
        "test_command": test_command,
        "test_results_artifact": artifact_paths.get("test_results_artifact"),
        "test_output_artifact": artifact_paths.get("test_output_artifact"),
        "recommended_focus": None if report_status == "passed" else "implementation",
    }
    if report_status == "not_run":
        report["recommended_focus"] = None
    return report


def _not_run_testing_report(summary: str) -> dict[str, Any]:
    return {
        "status": "not_run",
        "summary": summary,
        "test_command": None,
        "test_results_artifact": None,
        "test_output_artifact": None,
        "recommended_focus": None,
    }


def _testing_report_status(status: str) -> str:
    if status in {"passed", "failed", "timeout", "error", "not_run"}:
        return status
    return "error"


def _testing_report_summary(status: str, test_error: str | None) -> str:
    if status == "passed":
        return "Tests passed."
    if status == "failed":
        return "Tests failed."
    if status == "timeout":
        return "Tests timed out."
    if status == "no_command_detected":
        return "No safe test command was detected."
    if status == "error":
        return "Tests ended with an error."
    summary = f"Tests ended with status '{status}'."
    if test_error:
        return f"{summary} {test_error}"
    return summary


def _copy_cycle_test_artifacts(run_directory: Path, cycle_number: int) -> dict[str, str]:
    artifact_paths: dict[str, str] = {}
    artifacts = {
        "test_results_artifact": (
            run_directory / "test_results.json",
            run_directory / f"cycle_{cycle_number}_test_results.json",
        ),
        "test_output_artifact": (
            run_directory / "test_output.txt",
            run_directory / f"cycle_{cycle_number}_test_output.txt",
        ),
    }
    for key, (source, destination) in artifacts.items():
        if not source.exists():
            continue
        destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        artifact_paths[key] = str(destination)
    return artifact_paths


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
