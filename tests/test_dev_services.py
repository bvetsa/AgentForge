import json
from pathlib import Path

from agentforge.dev import DevSummaryWriter, PlannerDecisionService, TestingReportService


def test_planner_decision_service_owns_special_case_statuses_and_verdicts() -> None:
    service = PlannerDecisionService()

    assert service.approval_declined_status() == "user_declined"
    assert service.approval_declined_final_verdict(2) == (
        "No changes were applied because approval was declined for cycle 2."
    )
    assert service.no_patches_status() == "no_patches"
    assert service.no_patches_final_verdict() == (
        "No patch proposals were generated, so the dev run cannot continue."
    )
    assert service.apply_error_status() == "apply_failed"
    assert service.apply_error_final_verdict("bad patch") == (
        "Patch application failed: bad patch"
    )


def test_planner_decision_service_continues_failed_tests_before_max_cycle() -> None:
    service = PlannerDecisionService()
    testing_report = {
        "status": "failed",
        "recommended_focus": "implementation",
    }

    decision = service.for_test_report(
        cycle_number=1,
        test_status="failed",
        testing_report=testing_report,
        max_cycles=2,
        selected_agents=["frontend", "backend", "testing"],
        test_error=None,
    )

    assert decision["next_action"] == "continue"
    assert decision["recommended_focus"] == "implementation"
    assert decision["selected_agents"] == ["backend", "testing"]
    assert service.status(decision, "failed") == "continuing"
    assert (
        service.final_verdict(
            decision=decision,
            test_status="failed",
            cycle_number=1,
            max_cycles=2,
            test_error=None,
        )
        == ""
    )


def test_planner_decision_service_stops_at_max_cycles() -> None:
    service = PlannerDecisionService()
    decision = service.for_test_report(
        cycle_number=2,
        test_status="failed",
        testing_report={"status": "failed", "recommended_focus": "implementation"},
        max_cycles=2,
        selected_agents=["backend", "testing"],
        test_error="pytest failed",
    )

    assert decision["next_action"] == "stopped_max_cycles"
    assert decision["selected_agents"] == []
    assert service.status(decision, "failed") == "max_cycles_reached"
    assert service.final_verdict(
        decision=decision,
        test_status="failed",
        cycle_number=2,
        max_cycles=2,
        test_error="pytest failed",
    ) == (
        "Tests still failed after 2 cycle(s); max cycles (2) were reached. "
        "Test runner note: pytest failed"
    )


def test_testing_report_service_preserves_report_schema() -> None:
    service = TestingReportService()

    report = service.build(
        status="failed",
        test_command=["pytest"],
        test_error=None,
        artifact_paths={
            "test_results_artifact": "/tmp/cycle_1_test_results.json",
            "test_output_artifact": "/tmp/cycle_1_test_output.txt",
        },
    )

    assert report == {
        "status": "failed",
        "summary": "Tests failed.",
        "test_command": ["pytest"],
        "test_results_artifact": "/tmp/cycle_1_test_results.json",
        "test_output_artifact": "/tmp/cycle_1_test_output.txt",
        "recommended_focus": "implementation",
    }
    assert service.not_run("Tests have not run.") == {
        "status": "not_run",
        "summary": "Tests have not run.",
        "test_command": None,
        "test_results_artifact": None,
        "test_output_artifact": None,
        "recommended_focus": None,
    }


def test_dev_summary_writer_merges_cycles_and_aggregates_lists(tmp_path: Path) -> None:
    writer = DevSummaryWriter()
    writer.write(tmp_path, _summary_payload(cycle=1, patch_id="cycle1_patch"))
    writer.write(tmp_path, _summary_payload(cycle=2, patch_id="cycle2_patch"))

    summary = json.loads(
        (tmp_path / "dev_run_summary.json").read_text(encoding="utf-8")
    )

    assert [cycle["cycle"] for cycle in summary["cycles"]] == [1, 2]
    assert [patch["id"] for patch in summary["generated_patches"]] == [
        "cycle1_patch",
        "cycle2_patch",
    ]
    assert [decision["cycle"] for decision in summary["planner_decisions"]] == [1, 2]


def test_dev_summary_writer_upsert_replaces_existing_cycle() -> None:
    cycles = DevSummaryWriter.upsert_cycle(
        [{"cycle": 1, "status": "pending"}, {"cycle": 2, "status": "old"}],
        {"cycle": 2, "status": "updated"},
    )

    assert cycles == [
        {"cycle": 1, "status": "pending"},
        {"cycle": 2, "status": "updated"},
    ]


def _summary_payload(*, cycle: int, patch_id: str) -> dict[str, object]:
    decision = {
        "cycle": cycle,
        "next_action": "continue" if cycle == 1 else "stopped_max_cycles",
    }
    patch = {"id": patch_id}
    return {
        "run_id": "run-1",
        "status": "continuing" if cycle == 1 else "max_cycles_reached",
        "cycles": [
            {
                "cycle": cycle,
                "generated_patches": [patch],
                "applied_patches": [patch],
                "planner_decision": decision,
            }
        ],
        "generated_patches": [patch],
        "applied_patches": [patch],
        "planner_decisions": [decision],
    }
