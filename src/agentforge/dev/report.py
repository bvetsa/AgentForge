"""Append dev pipeline sections to workflow final reports."""

from agentforge.dev.models import DevRunResult


class DevReportWriter:
    """Append one completed dev cycle section to final_report.md."""

    @staticmethod
    def append(result: DevRunResult) -> None:
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
            section.extend(["### Final Verdict", "", result.final_verdict, ""])
        else:
            section.extend(
                [
                    "The planner selected another cycle; no final verdict was returned.",
                    "",
                ]
            )
        section_text = "\n".join(section)
        report_path.write_text(f"{existing.rstrip()}\n{section_text}", encoding="utf-8")
