"""Planner-controlled iterative development pipeline orchestration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agentforge.config.loader import ConfigLoadError
from agentforge.core.runner import WorkflowExecutionError, WorkflowRunner
from agentforge.dev.decisions import PlannerDecisionService
from agentforge.dev.models import DevRunResult, DevRunSession
from agentforge.dev.report import DevReportWriter
from agentforge.dev.summary import DevSummaryWriter
from agentforge.dev.testing_reports import TestingReportService
from agentforge.patches import PatchProposal, PatchReviewError, PatchReviewService
from agentforge.testing import TestRunError, TestRunner

REVIEWER_AGENT_NAME = "reviewer"
CUSTOMER_FACING_AGENT_NAMES = {"planner", REVIEWER_AGENT_NAME}


class DevPipelineError(RuntimeError):
    """Raised when the dev pipeline cannot complete."""

    def __init__(self, message: str, run_directory: Path | None = None) -> None:
        super().__init__(message)
        self.run_directory = run_directory


class DevPipelineRunner:
    """Coordinate a planner-controlled human-approved development loop."""

    def __init__(
        self,
        *,
        workflow_runner: WorkflowRunner | None = None,
        patch_review_service: PatchReviewService | None = None,
        test_runner: TestRunner | None = None,
        planner_decision_service: PlannerDecisionService | None = None,
        testing_report_service: TestingReportService | None = None,
        summary_writer: DevSummaryWriter | None = None,
        report_writer: DevReportWriter | None = None,
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
        self.planner_decision_service = (
            planner_decision_service or PlannerDecisionService()
        )
        self.testing_report_service = testing_report_service or TestingReportService()
        self.summary_writer = summary_writer or DevSummaryWriter()
        self.report_writer = report_writer or DevReportWriter()

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
            testing_report = self.testing_report_service.not_run(
                "Tests were not run because human approval was declined."
            )
            decision = self.planner_decision_service.approval_declined(
                session.cycle_number, testing_report
            )
            final_verdict = self.planner_decision_service.approval_declined_final_verdict(
                session.cycle_number
            )
            result = self._build_result(
                session=session,
                status=self.planner_decision_service.approval_declined_status(),
                applied_patches=[],
                test_status="not_run",
                test_command=None,
                testing_report=testing_report,
                planner_decisions=[decision],
                final_verdict=final_verdict,
            )
            self._persist_result(result)
            return result

        if not session.generated_patches:
            testing_report = self.testing_report_service.not_run(
                "Tests were not run because no patch proposals were generated."
            )
            decision = self.planner_decision_service.no_patches(
                session.cycle_number, testing_report
            )
            final_verdict = self.planner_decision_service.no_patches_final_verdict()
            result = self._build_result(
                session=session,
                status=self.planner_decision_service.no_patches_status(),
                applied_patches=[],
                test_status="not_run",
                test_command=None,
                testing_report=testing_report,
                planner_decisions=[decision],
                final_verdict=final_verdict,
            )
            self._persist_result(result)
            return result

        try:
            applied_patches = self._apply_proposed_patches(session)
        except PatchReviewError as error:
            testing_report = self.testing_report_service.not_run(
                "Tests were not run because patch application failed."
            )
            decision = self.planner_decision_service.apply_error(
                session.cycle_number,
                testing_report,
                str(error),
            )
            final_verdict = self.planner_decision_service.apply_error_final_verdict(
                str(error)
            )
            result = self._build_result(
                session=session,
                status=self.planner_decision_service.apply_error_status(),
                applied_patches=[],
                test_status="not_run",
                test_command=None,
                testing_report=testing_report,
                planner_decisions=[decision],
                final_verdict=final_verdict,
            )
            self._persist_result(result)
            raise DevPipelineError(final_verdict, run_directory=session.run_directory) from error

        test_status, test_command, test_error, testing_report = self._run_tests(session)
        decision = self.planner_decision_service.for_test_report(
            cycle_number=session.cycle_number,
            test_status=test_status,
            testing_report=testing_report,
            max_cycles=session.max_cycles,
            selected_agents=session.selected_agents,
            test_error=test_error,
        )
        final_verdict = self.planner_decision_service.final_verdict(
            decision=decision,
            test_status=test_status,
            cycle_number=session.cycle_number,
            max_cycles=session.max_cycles,
            test_error=test_error,
        )
        result = self._build_result(
            session=session,
            status=self.planner_decision_service.status(decision, test_status),
            applied_patches=applied_patches,
            test_status=test_status,
            test_command=test_command,
            testing_report=testing_report,
            planner_decisions=[decision],
            final_verdict=final_verdict,
        )
        self._persist_result(result)
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
        self.summary_writer.write_session(
            session=session,
            status="awaiting_approval",
            applied_patches=[],
            test_status="not_run",
            test_command=None,
            testing_report=self.testing_report_service.not_run(
                "Tests have not run for this cycle yet."
            ),
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
            testing_report = self.testing_report_service.build(
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
        testing_report = self.testing_report_service.build(
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

    def _persist_result(self, result: DevRunResult) -> None:
        self.summary_writer.write_result(result)
        self.report_writer.append(result)


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
