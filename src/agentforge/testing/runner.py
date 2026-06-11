"""Safe test command execution and artifact writing."""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from agentforge.testing.detector import TestCommandDetector
from agentforge.testing.models import TestCommandCandidate
from agentforge.testing.safety import (
    CommandParseError,
    CommandSafetyValidator,
    CommandValidationResult,
    split_command,
)
from agentforge.testing.scanner import ProjectScanError, ProjectScanner

DEFAULT_TEST_TIMEOUT_SECONDS = 30


class TestRunError(RuntimeError):
    """Raised when a test command cannot be selected or executed."""

    __test__ = False

    def __init__(self, message: str, run_directory: Path | None = None) -> None:
        super().__init__(message)
        self.run_directory = run_directory


@dataclass(frozen=True)
class CandidateAssessment:
    """A detected command candidate plus its safety result."""

    candidate: TestCommandCandidate
    safety: CommandValidationResult


@dataclass(frozen=True)
class TestRunResult:
    """Result returned after a test command run."""

    __test__ = False

    run_id: str
    run_directory: Path
    selected_command: list[str]
    command_source: str
    detection_reason: str
    all_candidates: list[dict[str, Any]]
    working_directory: Path
    status: str
    exit_code: int | None
    duration_seconds: float
    timeout_seconds: int
    timed_out: bool
    timestamp: str


class TestRunner:
    """Detect, validate, execute, and record a project test command."""

    __test__ = False

    def __init__(
        self,
        runs_directory: str | Path = ".agentforge/test-runs",
        scanner: ProjectScanner | None = None,
        detector: TestCommandDetector | None = None,
        validator: CommandSafetyValidator | None = None,
    ) -> None:
        self.runs_directory = Path(runs_directory)
        self.scanner = scanner or ProjectScanner()
        self.detector = detector or TestCommandDetector()
        self.validator = validator or CommandSafetyValidator()

    def detect_candidates(self, project_root: str | Path) -> list[CandidateAssessment]:
        """Return detected command candidates with safety assessments."""
        root = Path(project_root).resolve()
        try:
            evidence = self.scanner.scan(root)
        except ProjectScanError as error:
            raise TestRunError(str(error)) from error
        candidates = self.detector.detect(evidence)
        return [
            CandidateAssessment(
                candidate=candidate,
                safety=self.validator.validate(
                    command=candidate.command,
                    working_directory=candidate.working_directory,
                    project_root=root,
                    metadata=candidate.metadata,
                ),
            )
            for candidate in candidates
        ]

    def run(
        self,
        project_root: str | Path,
        command: str | None = None,
        timeout_seconds: int = DEFAULT_TEST_TIMEOUT_SECONDS,
    ) -> TestRunResult:
        """Run an explicit or auto-detected safe test command."""
        if timeout_seconds <= 0:
            raise TestRunError("Timeout must be greater than 0 seconds.")

        root = Path(project_root).resolve()
        timestamp = datetime.now(UTC).isoformat()
        run_id = self._create_run_id()
        run_directory = self.runs_directory / run_id
        run_directory.mkdir(parents=True, exist_ok=False)

        assessments: list[CandidateAssessment] = []
        selected: TestCommandCandidate | None = None
        command_source = "detected"
        detection_reason = ""

        if command is not None:
            try:
                argv = split_command(command)
            except CommandParseError as error:
                payload = self._build_payload(
                    selected_command=None,
                    command_source="user",
                    detection_reason=f"Explicit --command could not be parsed: {error}",
                    assessments=[],
                    working_directory=root,
                    status="blocked",
                    exit_code=None,
                    duration_seconds=0.0,
                    timeout_seconds=timeout_seconds,
                    timed_out=False,
                    timestamp=timestamp,
                    project_root=root,
                )
                self._write_artifacts(run_directory, payload, stdout="", stderr="")
                raise TestRunError(
                    f"Unsafe test command: {payload['detection_reason']}",
                    run_directory=run_directory,
                ) from error

            selected = TestCommandCandidate(
                command=argv,
                working_directory=root,
                confidence=1.0,
                reason="Explicit --command from user",
                source_type="user",
            )
            command_source = "user"
            detection_reason = selected.reason
            safety = self.validator.validate(
                command=selected.command,
                working_directory=selected.working_directory,
                project_root=root,
                metadata=selected.metadata,
            )
            assessments = [CandidateAssessment(candidate=selected, safety=safety)]
            if not safety.is_safe:
                payload = self._build_payload(
                    selected_command=selected.command,
                    command_source=command_source,
                    detection_reason=safety.reason or "explicit command was rejected",
                    assessments=assessments,
                    working_directory=root,
                    status="blocked",
                    exit_code=None,
                    duration_seconds=0.0,
                    timeout_seconds=timeout_seconds,
                    timed_out=False,
                    timestamp=timestamp,
                    project_root=root,
                )
                self._write_artifacts(run_directory, payload, stdout="", stderr="")
                raise TestRunError(
                    f"Unsafe test command: {payload['detection_reason']}",
                    run_directory=run_directory,
                )
        else:
            assessments = self.detect_candidates(root)
            for assessment in assessments:
                if assessment.safety.is_safe:
                    selected = assessment.candidate
                    detection_reason = selected.reason
                    break
            if selected is None:
                detection_reason = (
                    "No safe test command detected. Pass --command to agentforge test run."
                )
                payload = self._build_payload(
                    selected_command=None,
                    command_source=command_source,
                    detection_reason=detection_reason,
                    assessments=assessments,
                    working_directory=root,
                    status="no_command_detected",
                    exit_code=None,
                    duration_seconds=0.0,
                    timeout_seconds=timeout_seconds,
                    timed_out=False,
                    timestamp=timestamp,
                    project_root=root,
                )
                self._write_artifacts(run_directory, payload, stdout="", stderr="")
                raise TestRunError(detection_reason, run_directory=run_directory)

        start = time.monotonic()
        stdout = ""
        stderr = ""
        timed_out = False
        exit_code: int | None
        try:
            completed = subprocess.run(
                selected.command,
                cwd=selected.working_directory,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout_seconds,
                shell=False,
                check=False,
            )
            stdout = completed.stdout
            stderr = completed.stderr
            exit_code = completed.returncode
            status = "passed" if completed.returncode == 0 else "failed"
        except subprocess.TimeoutExpired as error:
            stdout = _decode_timeout_output(error.stdout)
            stderr = _decode_timeout_output(error.stderr)
            exit_code = None
            timed_out = True
            status = "timeout"
        except OSError as error:
            exit_code = None
            status = "error"
            stderr = str(error)

        duration_seconds = round(time.monotonic() - start, 6)
        payload = self._build_payload(
            selected_command=selected.command,
            command_source=command_source,
            detection_reason=detection_reason,
            assessments=assessments,
            working_directory=selected.working_directory,
            status=status,
            exit_code=exit_code,
            duration_seconds=duration_seconds,
            timeout_seconds=timeout_seconds,
            timed_out=timed_out,
            timestamp=timestamp,
            project_root=root,
        )
        self._write_artifacts(run_directory, payload, stdout=stdout, stderr=stderr)

        return TestRunResult(
            run_id=run_id,
            run_directory=run_directory,
            selected_command=selected.command,
            command_source=command_source,
            detection_reason=detection_reason,
            all_candidates=payload["all_candidates"],
            working_directory=selected.working_directory,
            status=status,
            exit_code=exit_code,
            duration_seconds=duration_seconds,
            timeout_seconds=timeout_seconds,
            timed_out=timed_out,
            timestamp=timestamp,
        )

    def _build_payload(
        self,
        *,
        selected_command: list[str] | None,
        command_source: str,
        detection_reason: str,
        assessments: list[CandidateAssessment],
        working_directory: Path,
        status: str,
        exit_code: int | None,
        duration_seconds: float,
        timeout_seconds: int,
        timed_out: bool,
        timestamp: str,
        project_root: Path,
    ) -> dict[str, Any]:
        return {
            "selected_command": selected_command,
            "command_source": command_source,
            "detection_reason": detection_reason,
            "all_candidates": [
                {
                    **assessment.candidate.to_dict(project_root),
                    "safe": assessment.safety.is_safe,
                    "rejection_reason": assessment.safety.reason,
                }
                for assessment in assessments
            ],
            "working_directory": str(working_directory.resolve(strict=False)),
            "status": status,
            "exit_code": exit_code,
            "duration_seconds": duration_seconds,
            "timeout_seconds": timeout_seconds,
            "timed_out": timed_out,
            "timestamp": timestamp,
        }

    @staticmethod
    def _write_artifacts(
        run_directory: Path,
        payload: dict[str, Any],
        *,
        stdout: str,
        stderr: str,
    ) -> None:
        (run_directory / "test_results.json").write_text(
            f"{json.dumps(payload, indent=2, sort_keys=True)}\n",
            encoding="utf-8",
        )
        (run_directory / "test_output.txt").write_text(
            "\n".join(["# stdout", stdout, "# stderr", stderr]),
            encoding="utf-8",
        )

    @staticmethod
    def _create_run_id() -> str:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        return f"{timestamp}-{uuid4().hex[:8]}"


def _decode_timeout_output(output: str | bytes | None) -> str:
    if output is None:
        return ""
    if isinstance(output, bytes):
        return output.decode("utf-8", errors="replace")
    return output
