"""Write inspectable artifacts for workflow runs."""

import json
from pathlib import Path
from typing import Any


class ArtifactWriter:
    """Persist run inputs, state, traces, and a human-readable report."""

    def __init__(self, runs_directory: str | Path = ".agentforge/runs") -> None:
        self.runs_directory = Path(runs_directory)

    def write(
        self,
        *,
        run_id: str,
        workflow_name: str,
        input_text: str,
        state: dict[str, str],
        trace_events: list[dict[str, Any]],
        agent_outputs: list[tuple[str, str]],
    ) -> Path:
        """Write all artifacts for one workflow run and return its directory."""
        run_directory = self.runs_directory / run_id
        run_directory.mkdir(parents=True, exist_ok=False)

        (run_directory / "input.txt").write_text(f"{input_text}\n", encoding="utf-8")
        self._write_json(run_directory / "state.json", state)
        self._write_json(run_directory / "trace.json", trace_events)
        (run_directory / "final_report.md").write_text(
            self._build_final_report(workflow_name, input_text, agent_outputs),
            encoding="utf-8",
        )

        return run_directory

    @staticmethod
    def _write_json(path: Path, data: Any) -> None:
        path.write_text(f"{json.dumps(data, indent=2, sort_keys=True)}\n", encoding="utf-8")

    @staticmethod
    def _build_final_report(
        workflow_name: str,
        input_text: str,
        agent_outputs: list[tuple[str, str]],
    ) -> str:
        sections = [
            "# AgentForge Run Report",
            "",
            "## Workflow",
            "",
            workflow_name,
            "",
            "## User Request",
            "",
            input_text,
            "",
            "## Agent Outputs",
            "",
        ]

        for agent_name, output in agent_outputs:
            sections.extend([f"### {agent_name}", "", output, ""])

        return "\n".join(sections)
