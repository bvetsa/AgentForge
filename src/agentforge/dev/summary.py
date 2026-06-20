"""Write and merge dev pipeline summary artifacts."""

import json
from pathlib import Path
from typing import Any

from agentforge.dev.models import DevRunResult, DevRunSession


class DevSummaryWriter:
    """Build, persist, and merge stable dev_run_summary.json payloads."""

    def write_result(self, result: DevRunResult) -> None:
        self.write(result.run_directory, self.payload_from_result(result))

    def write_session(
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
        self.write(
            session.run_directory,
            self.build_payload(
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

    def payload_from_result(self, result: DevRunResult) -> dict[str, Any]:
        return self.build_payload(
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

    @staticmethod
    def build_payload(
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
            "approval": DevSummaryWriter._cycle_approval_status(planner_decisions),
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
            "stop_reason": DevSummaryWriter._stop_reason(decision),
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

    def write(self, run_directory: Path, payload: dict[str, Any]) -> None:
        existing = self.read(run_directory)
        if existing is not None and existing.get("run_id") == payload.get("run_id"):
            payload = self.merge_payload(existing, payload)

        summary_path = run_directory / "dev_run_summary.json"
        summary_path.write_text(
            f"{json.dumps(payload, indent=2, sort_keys=True)}\n",
            encoding="utf-8",
        )

    @staticmethod
    def read(run_directory: Path) -> dict[str, Any] | None:
        summary_path = run_directory / "dev_run_summary.json"
        if not summary_path.exists():
            return None
        try:
            payload = json.loads(summary_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    @staticmethod
    def merge_payload(
        existing: dict[str, Any],
        current: dict[str, Any],
    ) -> dict[str, Any]:
        existing_cycles = existing.get("cycles")
        current_cycles = current.get("cycles")
        if not isinstance(existing_cycles, list) or not isinstance(current_cycles, list):
            return current

        cycles = DevSummaryWriter.upsert_cycle(existing_cycles, current_cycles[0])
        return {
            **existing,
            **current,
            "cycles": cycles,
            "generated_patches": DevSummaryWriter._aggregate_cycle_list(
                cycles, "generated_patches"
            ),
            "applied_patches": DevSummaryWriter._aggregate_cycle_list(
                cycles, "applied_patches"
            ),
            "planner_decisions": [
                cycle["planner_decision"]
                for cycle in cycles
                if isinstance(cycle, dict) and cycle.get("planner_decision") is not None
            ],
        }

    @staticmethod
    def upsert_cycle(
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

    @staticmethod
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

    @staticmethod
    def _cycle_approval_status(planner_decisions: list[dict[str, Any]]) -> str:
        if not planner_decisions:
            return "pending"
        approval = planner_decisions[-1].get("approval")
        return approval if isinstance(approval, str) else "unknown"

    @staticmethod
    def _stop_reason(decision: dict[str, Any] | None) -> str | None:
        if not decision:
            return None
        if decision.get("next_action") == "continue":
            return None
        reason = decision.get("reason")
        return reason if isinstance(reason, str) else None
