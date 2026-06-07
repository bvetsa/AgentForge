"""Write inspectable artifacts for workflow runs."""

import json
from pathlib import Path
from typing import Any

from agentforge.patches import PatchProposal, PatchProposalWriter


class ArtifactWriter:
    """Persist run inputs, state, traces, and a human-readable report."""

    def __init__(self, runs_directory: str | Path = ".agentforge/runs") -> None:
        self.runs_directory = Path(runs_directory)
        self.patch_writer = PatchProposalWriter()

    def write(
        self,
        *,
        run_id: str,
        workflow_name: str,
        input_text: str,
        state: dict[str, str],
        trace_events: list[dict[str, Any]],
        agent_outputs: list[tuple[str, str]],
        tool_calls: list[dict[str, Any]],
        patch_proposals: list[PatchProposal] | None = None,
    ) -> Path:
        """Write all artifacts for one workflow run and return its directory."""
        run_directory = self.runs_directory / run_id
        run_directory.mkdir(parents=True, exist_ok=False)
        patch_proposals = patch_proposals or []

        (run_directory / "input.txt").write_text(f"{input_text}\n", encoding="utf-8")
        self._write_json(run_directory / "state.json", state)
        self._write_json(run_directory / "trace.json", trace_events)
        self._write_json(run_directory / "tool_calls.json", tool_calls)
        self.patch_writer.write(run_directory, patch_proposals)
        self._write_json(
            run_directory / "patch_manifest.json",
            [proposal.model_dump() for proposal in patch_proposals],
        )
        (run_directory / "final_report.md").write_text(
            self._build_final_report(
                workflow_name,
                input_text,
                agent_outputs,
                patch_proposals,
            ),
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
        patch_proposals: list[PatchProposal],
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

        sections.extend(["## Patch Proposals", ""])
        if patch_proposals:
            for proposal in patch_proposals:
                sections.extend(
                    [
                        f"### {proposal.title}",
                        "",
                        f"- ID: `{proposal.id}`",
                        f"- Agent: `{proposal.agent_name}`",
                        f"- Status: `{proposal.status}`",
                        f"- Target file: `{proposal.target_file}`",
                        f"- Patch file: `{proposal.patch_file}`",
                        "",
                        proposal.description,
                        "",
                    ]
                )
        else:
            sections.extend(["No patch proposals were generated.", ""])

        return "\n".join(sections)
