"""Deterministic planner decision policy for the development loop."""

from typing import Any


class PlannerDecisionService:
    """Create planner decisions, statuses, and final verdicts from cycle results."""

    @staticmethod
    def approval_declined_status() -> str:
        return "user_declined"

    @staticmethod
    def approval_declined_final_verdict(cycle_number: int) -> str:
        return (
            f"No changes were applied because approval was declined for cycle "
            f"{cycle_number}."
        )

    def approval_declined(
        self,
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

    def no_patches(
        self,
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

    @staticmethod
    def no_patches_status() -> str:
        return "no_patches"

    @staticmethod
    def no_patches_final_verdict() -> str:
        return "No patch proposals were generated, so the dev run cannot continue."

    def apply_error(
        self,
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

    @staticmethod
    def apply_error_status() -> str:
        return "apply_failed"

    @staticmethod
    def apply_error_final_verdict(error_message: str) -> str:
        return f"Patch application failed: {error_message}"

    def for_test_report(
        self,
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
            recommended_focus = self._recommended_focus(testing_report)
            next_agents = self._next_cycle_agents(selected_agents)
            notes = [reason, f"Focus: {recommended_focus}."]
        else:
            next_action = "stopped_max_cycles"
            reason = "Tests failed and max cycles were reached."
            recommended_focus = self._recommended_focus(testing_report)
            next_agents = []
            notes = [reason, f"Focus: {recommended_focus}."]

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

    def final_verdict(
        self,
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

    @staticmethod
    def status(decision: dict[str, Any], test_status: str) -> str:
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

    @staticmethod
    def _next_cycle_agents(selected_agents: list[str]) -> list[str]:
        preferred = [agent for agent in ("backend", "testing") if agent in selected_agents]
        if preferred:
            return preferred
        return selected_agents[-2:]

    @staticmethod
    def _recommended_focus(testing_report: dict[str, Any]) -> str:
        focus = testing_report.get("recommended_focus")
        return focus if isinstance(focus, str) and focus else "implementation"
