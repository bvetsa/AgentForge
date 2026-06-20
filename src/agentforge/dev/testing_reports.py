"""Convert test runner results into dev pipeline testing reports."""

from typing import Any


class TestingReportService:
    """Build stable testing report payloads for planner decisions and artifacts."""

    def build(
        self,
        *,
        status: str,
        test_command: list[str] | None,
        test_error: str | None,
        artifact_paths: dict[str, str],
    ) -> dict[str, Any]:
        report_status = self._status(status)
        report = {
            "status": report_status,
            "summary": self._summary(status, test_error),
            "test_command": test_command,
            "test_results_artifact": artifact_paths.get("test_results_artifact"),
            "test_output_artifact": artifact_paths.get("test_output_artifact"),
            "recommended_focus": None if report_status == "passed" else "implementation",
        }
        if report_status == "not_run":
            report["recommended_focus"] = None
        return report

    @staticmethod
    def not_run(summary: str) -> dict[str, Any]:
        return {
            "status": "not_run",
            "summary": summary,
            "test_command": None,
            "test_results_artifact": None,
            "test_output_artifact": None,
            "recommended_focus": None,
        }

    @staticmethod
    def _status(status: str) -> str:
        if status in {"passed", "failed", "timeout", "error", "not_run"}:
            return status
        return "error"

    @staticmethod
    def _summary(status: str, test_error: str | None) -> str:
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
