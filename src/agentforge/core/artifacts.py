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
        llm_calls: list[dict[str, Any]],
        patch_proposals: list[PatchProposal] | None = None,
        merge_patch_manifest: bool = False,
    ) -> Path:
        """Write all artifacts for one workflow run and return its directory."""
        run_directory = self.runs_directory / run_id
        run_directory.mkdir(parents=True, exist_ok=merge_patch_manifest)
        patch_proposals = patch_proposals or []

        (run_directory / "input.txt").write_text(f"{input_text}\n", encoding="utf-8")
        self._write_json(run_directory / "state.json", state)
        self._write_json(run_directory / "trace.json", trace_events)
        self._write_json(run_directory / "tool_calls.json", tool_calls)
        if merge_patch_manifest:
            llm_calls = self._merge_llm_calls(run_directory, llm_calls)
        self._write_json(run_directory / "llm_calls.json", llm_calls)
        self.patch_writer.write(run_directory, patch_proposals)
        manifest_data = [proposal.model_dump() for proposal in patch_proposals]
        if merge_patch_manifest:
            manifest_data = self._merge_patch_manifest(run_directory, manifest_data)
        self._write_json(run_directory / "patch_manifest.json", manifest_data)
        self._write_final_report(
            run_directory=run_directory,
            workflow_name=workflow_name,
            input_text=input_text,
            agent_outputs=agent_outputs,
            patch_proposals=patch_proposals,
            append=merge_patch_manifest,
        )

        return run_directory

    @staticmethod
    def _merge_patch_manifest(
        run_directory: Path,
        patch_proposals: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        manifest_path = run_directory / "patch_manifest.json"
        if not manifest_path.exists():
            return patch_proposals

        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return patch_proposals
        if not isinstance(existing, list):
            return patch_proposals

        proposal_ids = {
            proposal.get("id")
            for proposal in patch_proposals
            if isinstance(proposal, dict)
        }
        retained = [
            proposal
            for proposal in existing
            if isinstance(proposal, dict) and proposal.get("id") not in proposal_ids
        ]
        return retained + patch_proposals

    @staticmethod
    def _merge_llm_calls(
        run_directory: Path,
        llm_calls: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        llm_calls_path = run_directory / "llm_calls.json"
        if not llm_calls_path.exists():
            return llm_calls

        try:
            existing = json.loads(llm_calls_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return llm_calls
        if not isinstance(existing, list):
            return llm_calls

        return [call for call in existing if isinstance(call, dict)] + llm_calls

    @staticmethod
    def _write_json(path: Path, data: Any) -> None:
        path.write_text(f"{json.dumps(data, indent=2, sort_keys=True)}\n", encoding="utf-8")

    @classmethod
    def _write_final_report(
        cls,
        *,
        run_directory: Path,
        workflow_name: str,
        input_text: str,
        agent_outputs: list[tuple[str, str]],
        patch_proposals: list[PatchProposal],
        append: bool,
    ) -> None:
        report_path = run_directory / "final_report.md"
        report_text = cls._build_final_report(
            workflow_name,
            input_text,
            agent_outputs,
            patch_proposals,
        )
        if append and report_path.exists():
            existing = report_path.read_text(encoding="utf-8").rstrip()
            report_text = f"{existing}\n\n---\n\n{report_text}"
        report_path.write_text(report_text, encoding="utf-8")

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
