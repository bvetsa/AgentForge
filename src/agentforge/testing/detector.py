"""Deterministic test command detector."""

from __future__ import annotations

from pathlib import Path

from agentforge.testing.models import EvidenceCommand, ProjectEvidence, TestCommandCandidate
from agentforge.testing.safety import CommandParseError, split_command


class TestCommandDetector:
    """Rank likely test commands from scanned project evidence."""

    def detect(self, evidence: ProjectEvidence) -> list[TestCommandCandidate]:
        """Return ranked candidates without performing safety validation."""
        candidates: list[TestCommandCandidate] = []
        candidates.extend(self._from_evidence_commands(evidence, evidence.ci_commands, 0.95))
        candidates.extend(
            self._from_evidence_commands(evidence, evidence.documentation_commands, 0.90)
        )
        candidates.extend(
            self._from_evidence_commands(evidence, evidence.make_test_targets, 0.80)
        )
        candidates.extend(
            self._from_evidence_commands(evidence, evidence.package_json_scripts, 0.75)
        )
        candidates.extend(self._framework_specific_candidates(evidence))
        candidates.extend(self._language_default_candidates(evidence))
        return self._deduplicate(candidates)

    def _from_evidence_commands(
        self,
        evidence: ProjectEvidence,
        commands: list[EvidenceCommand],
        confidence: float,
    ) -> list[TestCommandCandidate]:
        candidates: list[TestCommandCandidate] = []
        for command in commands:
            try:
                argv = split_command(command.command)
                metadata = command.metadata
            except CommandParseError as error:
                argv = [command.command]
                metadata = {**command.metadata, "parse_error": str(error)}
            candidates.append(
                TestCommandCandidate(
                    command=argv,
                    working_directory=evidence.project_root / command.working_directory,
                    confidence=confidence,
                    reason=command.reason,
                    source_type=command.source_type,
                    evidence_path=command.source_path,
                    evidence_line=command.line,
                    metadata=metadata,
                )
            )
        return candidates

    def _framework_specific_candidates(
        self,
        evidence: ProjectEvidence,
    ) -> list[TestCommandCandidate]:
        indicators = evidence.python_indicators
        candidates: list[TestCommandCandidate] = []

        if indicators.get("has_manage_py"):
            reason = "manage.py indicates a Django test command"
            if indicators.get("mentions_django"):
                reason = "manage.py and Django dependency evidence indicate a Django test command"
            candidates.append(
                TestCommandCandidate(
                    command=["python", "manage.py", "test"],
                    working_directory=evidence.project_root,
                    confidence=0.65,
                    reason=reason,
                    source_type="python_django",
                    evidence_path="manage.py",
                )
            )

        if (
            indicators.get("mentions_pytest")
            and indicators.get("has_python_test_files")
        ):
            candidates.append(
                TestCommandCandidate(
                    command=["python", "-m", "pytest"],
                    working_directory=evidence.project_root,
                    confidence=0.62,
                    reason="pytest configuration and Python test files were detected",
                    source_type="python_pytest",
                )
            )

        return candidates

    def _language_default_candidates(
        self,
        evidence: ProjectEvidence,
    ) -> list[TestCommandCandidate]:
        indicators = evidence.python_indicators
        if not (
            indicators.get("has_python_files")
            and (
                indicators.get("has_python_test_files")
                or indicators.get("has_tests_directory")
            )
        ):
            return []

        return [
            TestCommandCandidate(
                command=["python", "-m", "pytest"],
                working_directory=evidence.project_root,
                confidence=0.50,
                reason="Python files and tests were detected",
                source_type="python_default",
            )
        ]

    @staticmethod
    def _deduplicate(candidates: list[TestCommandCandidate]) -> list[TestCommandCandidate]:
        deduplicated: list[TestCommandCandidate] = []
        seen: set[tuple[tuple[str, ...], Path]] = set()
        for candidate in candidates:
            key = (
                tuple(candidate.command),
                candidate.working_directory.resolve(strict=False),
            )
            if key in seen:
                continue
            seen.add(key)
            deduplicated.append(candidate)
        return deduplicated
