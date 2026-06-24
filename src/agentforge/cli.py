"""Command-line interface for AgentForge."""

from pathlib import Path
from typing import Annotated

import typer

from agentforge.config.loader import ConfigLoadError
from agentforge.core.runner import WorkflowExecutionError, WorkflowRunner
from agentforge.dev import DevPipelineError, DevPipelineRunner, DevRunResult, DevRunSession
from agentforge.llm import (
    LLMConfigError,
    LLMProvider,
    create_llm_provider,
    load_llm_provider_config,
    non_secret_config_dict,
    reset_project_llm_config,
    set_project_llm_config,
)
from agentforge.llm.config import parse_timeout_seconds, validate_provider_name
from agentforge.patches import PatchReviewError, PatchReviewService
from agentforge.testing import DEFAULT_TEST_TIMEOUT_SECONDS, TestRunError, TestRunner

app = typer.Typer(help="Run composable software-development agent workflows.")
config_app = typer.Typer(help="Manage project AgentForge configuration.")
patch_app = typer.Typer(help="Review and apply patch proposals from a previous run.")
test_app = typer.Typer(help="Detect and run project test commands.")
dev_app = typer.Typer(help="Run the human-approved end-to-end development pipeline.")
app.add_typer(config_app, name="config")
app.add_typer(patch_app, name="patch")
app.add_typer(test_app, name="test")
app.add_typer(dev_app, name="dev")

DEFAULT_DEV_WORKFLOW_PATH = Path("examples/workflows/basic_feature.yaml")


@app.callback()
def main() -> None:
    """Run composable software-development agent workflows."""


@app.command()
def run(
    workflow_path: Annotated[
        Path,
        typer.Argument(help="Path to a workflow YAML file."),
    ],
    input_text: Annotated[
        str,
        typer.Option("--input", help="Request for the workflow to process."),
    ],
    project_root: Annotated[
        Path | None,
        typer.Option("--project-root", help="Project directory exposed to read-only tools."),
    ] = None,
    no_project_context: Annotated[
        bool,
        typer.Option("--no-project-context", help="Disable deterministic read-only project tools."),
    ] = False,
) -> None:
    """Run a YAML-defined workflow."""
    if project_root is not None and no_project_context:
        typer.echo(
            "Error: --project-root and --no-project-context cannot be used together.",
            err=True,
        )
        raise typer.Exit(code=1)

    try:
        llm_provider = _create_configured_llm_provider()
        result = WorkflowRunner(llm_provider=llm_provider).run(
            workflow_path,
            input_text,
            project_root=project_root,
            use_project_context=not no_project_context,
        )
    except (ConfigLoadError, LLMConfigError, WorkflowExecutionError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(code=1) from error

    typer.echo(f"Workflow '{result.workflow_name}' completed successfully.")
    typer.echo(f"Run artifacts: {result.run_directory}")


@config_app.command("show")
def show_config() -> None:
    """Show effective non-secret AgentForge configuration."""
    try:
        config = load_llm_provider_config()
    except LLMConfigError as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(code=1) from error

    for key, value in non_secret_config_dict(config).items():
        if value is None:
            value = "null"
        typer.echo(f"{key}: {value}")


@config_app.command("set")
def set_config(
    llm_provider: Annotated[
        str | None,
        typer.Option("--llm-provider", help="LLM provider name."),
    ] = None,
    llm_model: Annotated[
        str | None,
        typer.Option("--llm-model", help="LLM model name."),
    ] = None,
    llm_base_url: Annotated[
        str | None,
        typer.Option("--llm-base-url", help="Chat-completions-compatible base URL."),
    ] = None,
    llm_timeout: Annotated[
        str | None,
        typer.Option("--llm-timeout", help="LLM request timeout in seconds."),
    ] = None,
) -> None:
    """Set project-local non-secret LLM configuration values."""
    updates: dict[str, object] = {}
    try:
        if llm_provider is not None:
            updates["provider"] = validate_provider_name(
                llm_provider,
                source="--llm-provider",
            )
        if llm_model is not None:
            updates["model"] = llm_model
        if llm_base_url is not None:
            updates["base_url"] = llm_base_url
        if llm_timeout is not None:
            updates["timeout_seconds"] = parse_timeout_seconds(
                llm_timeout,
                source="--llm-timeout",
            )
        if not updates:
            raise LLMConfigError("Provide at least one config value to set.")
        config_path = set_project_llm_config(updates)
    except LLMConfigError as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(code=1) from error

    typer.echo(f"Wrote {config_path}")


@config_app.command("reset")
def reset_config() -> None:
    """Remove project-local AgentForge configuration."""
    removed = reset_project_llm_config()
    if removed:
        typer.echo("Removed .agentforge/config.toml")
    else:
        typer.echo("No project config file found.")


@patch_app.command("list")
def list_patches(
    run_id: Annotated[
        str,
        typer.Argument(help="Run ID under .agentforge/runs."),
    ],
) -> None:
    """List patch proposals generated by a previous run."""
    try:
        proposals = PatchReviewService().list_patches(run_id)
    except PatchReviewError as error:
        _exit_with_error(error)

    if not proposals:
        typer.echo("No patch proposals found.")
        return

    typer.echo("ID\tAgent\tTarget file\tStatus\tTitle")
    for proposal in proposals:
        typer.echo(
            "\t".join(
                [
                    proposal.id,
                    proposal.agent_name,
                    proposal.target_file,
                    proposal.status,
                    proposal.title,
                ]
            )
        )


@patch_app.command("show")
def show_patch(
    run_id: Annotated[
        str,
        typer.Argument(help="Run ID under .agentforge/runs."),
    ],
    patch_id: Annotated[
        str,
        typer.Argument(help="Patch proposal ID to display."),
    ],
) -> None:
    """Print the diff for one patch proposal."""
    try:
        diff_text = PatchReviewService().show_patch(run_id, patch_id)
    except PatchReviewError as error:
        _exit_with_error(error)

    typer.echo(diff_text.rstrip("\n"))


@patch_app.command("apply")
def apply_patch(
    run_id: Annotated[
        str,
        typer.Argument(help="Run ID under .agentforge/runs."),
    ],
    patch_id: Annotated[
        str,
        typer.Argument(help="Patch proposal ID to apply."),
    ],
    project_root: Annotated[
        Path,
        typer.Option(
            "--project-root",
            exists=True,
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
            help="Project root where the selected patch may write.",
        ),
    ],
) -> None:
    """Apply one explicitly selected patch proposal."""
    try:
        target_path = PatchReviewService().apply_patch(run_id, patch_id, project_root)
    except PatchReviewError as error:
        _exit_with_error(error)

    typer.echo(f"Applied patch '{patch_id}' to {target_path}")


@test_app.command("detect")
def detect_test_command(
    project_root: Annotated[
        Path,
        typer.Option(
            "--project-root",
            exists=True,
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
            help="Project root to inspect for likely test commands.",
        ),
    ],
) -> None:
    """Show likely test commands without running them."""
    try:
        assessments = TestRunner().detect_candidates(project_root)
    except TestRunError as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(code=1) from error

    if not assessments:
        typer.echo("No test command candidates detected.")
        return

    typer.echo("Safety\tConfidence\tSource\tWorking directory\tCommand\tReason")
    for assessment in assessments:
        candidate = assessment.candidate
        safety = "safe" if assessment.safety.is_safe else "unsafe"
        command_text = " ".join(candidate.command)
        reason = candidate.reason
        if assessment.safety.reason:
            reason = f"{reason} ({assessment.safety.reason})"
        typer.echo(
            "\t".join(
                [
                    safety,
                    f"{candidate.confidence:.2f}",
                    candidate.source_type,
                    str(candidate.working_directory.resolve(strict=False)),
                    command_text,
                    reason,
                ]
            )
        )


@test_app.command("run")
def run_test_command(
    project_root: Annotated[
        Path,
        typer.Option(
            "--project-root",
            exists=True,
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
            help="Project root where tests should be detected and run.",
        ),
    ],
    command: Annotated[
        str | None,
        typer.Option(
            "--command",
            help="Explicit test command to run instead of auto-detection.",
        ),
    ] = None,
    timeout_seconds: Annotated[
        int,
        typer.Option("--timeout", help="Maximum test command runtime in seconds."),
    ] = DEFAULT_TEST_TIMEOUT_SECONDS,
) -> None:
    """Run an explicit or auto-detected safe test command."""
    try:
        result = TestRunner().run(
            project_root=project_root,
            command=command,
            timeout_seconds=timeout_seconds,
        )
    except TestRunError as error:
        typer.echo(f"Error: {error}", err=True)
        if error.run_directory is not None:
            typer.echo(f"Test artifacts: {error.run_directory}", err=True)
        raise typer.Exit(code=1) from error

    typer.echo(f"Test command: {' '.join(result.selected_command)}")
    typer.echo(f"Command source: {result.command_source}")
    typer.echo(f"Status: {result.status}")
    typer.echo(f"Exit code: {result.exit_code}")
    typer.echo(f"Test artifacts: {result.run_directory}")

    if result.exit_code not in (None, 0):
        raise typer.Exit(code=result.exit_code)
    if result.timed_out or result.status == "error":
        raise typer.Exit(code=1)


@dev_app.command("run")
def run_dev_pipeline(
    input_text: Annotated[
        str,
        typer.Option("--input", help="Request for the dev pipeline to process."),
    ],
    project_root: Annotated[
        Path | None,
        typer.Option(
            "--project-root",
            exists=True,
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
            help="Project root where approved patches and tests should run.",
        ),
    ] = None,
    workflow_path: Annotated[
        Path,
        typer.Option("--workflow", help="Workflow YAML file to run."),
    ] = DEFAULT_DEV_WORKFLOW_PATH,
    yes: Annotated[
        bool,
        typer.Option("--yes", help="Apply all proposed patches without prompting."),
    ] = False,
    max_cycles: Annotated[
        int,
        typer.Option("--max-cycles", help="Maximum dev cycles. Defaults to 3."),
    ] = 3,
) -> None:
    """Run the planner-controlled iterative development pipeline."""
    resolved_project_root = Path.cwd() if project_root is None else project_root
    resolved_workflow_path = _resolve_workflow_path(workflow_path)

    try:
        llm_provider = _create_configured_llm_provider()
        workflow_runner = WorkflowRunner(llm_provider=llm_provider)
        pipeline = DevPipelineRunner(workflow_runner=workflow_runner)
        session = pipeline.prepare(
            user_request=input_text,
            project_root=resolved_project_root,
            workflow_path=resolved_workflow_path,
            max_cycles=max_cycles,
        )
    except (LLMConfigError, DevPipelineError) as error:
        typer.echo(f"Error: {error}", err=True)
        run_directory = getattr(error, "run_directory", None)
        if run_directory is not None:
            typer.echo(f"Run artifacts: {run_directory}", err=True)
        raise typer.Exit(code=1) from error

    while True:
        _echo_dev_approval_summary(session)
        if not session.generated_patches:
            approved = True
        elif yes:
            approved = True
            typer.echo(
                f"Patches for cycle {session.cycle_number} auto-approved by --yes."
            )
        else:
            approved = typer.confirm(
                f"Apply all proposed patches for cycle {session.cycle_number}?",
                default=False,
            )

        try:
            result = pipeline.finish(session, approved=approved)
        except DevPipelineError as error:
            typer.echo(f"Error: {error}", err=True)
            if error.run_directory is not None:
                typer.echo(f"Run artifacts: {error.run_directory}", err=True)
            raise typer.Exit(code=1) from error

        _echo_dev_cycle_completion(result, approved=approved)
        decision = result.planner_decisions[-1] if result.planner_decisions else {}
        if decision.get("next_action") != "continue":
            _echo_dev_final_result(result)
            break

        _echo_dev_continue(result)
        try:
            session = pipeline.prepare_next_cycle(result)
        except DevPipelineError as error:
            typer.echo(f"Error: {error}", err=True)
            if error.run_directory is not None:
                typer.echo(f"Run artifacts: {error.run_directory}", err=True)
            raise typer.Exit(code=1) from error


def _create_configured_llm_provider() -> LLMProvider:
    config = load_llm_provider_config()
    return create_llm_provider(config)


def _exit_with_error(error: PatchReviewError) -> None:
    typer.echo(f"Error: {error}", err=True)
    raise typer.Exit(code=1) from error


def _resolve_workflow_path(workflow_path: Path) -> Path:
    if workflow_path.exists() or workflow_path.is_absolute():
        return workflow_path.resolve(strict=False)

    repository_candidate = Path(__file__).resolve().parents[2] / workflow_path
    if repository_candidate.exists():
        return repository_candidate.resolve()

    return workflow_path.resolve(strict=False)


def _echo_dev_approval_summary(session: DevRunSession) -> None:
    typer.echo("AgentForge Dev Run")
    typer.echo()
    typer.echo("Request:")
    typer.echo(session.user_request)
    typer.echo()
    typer.echo("Project root:")
    typer.echo(str(session.project_root.resolve(strict=False)))
    typer.echo()
    typer.echo("Workflow:")
    typer.echo(str(session.workflow_path))
    typer.echo()
    typer.echo(f"Cycle {session.cycle_number}")
    typer.echo()
    typer.echo("Planner:")
    typer.echo(f"- {session.planner_summary}")
    if session.planned_focus:
        typer.echo(f"- Focus: {session.planned_focus}")
    typer.echo()
    typer.echo("Selected agents:")
    if session.selected_agents:
        for agent_name in session.selected_agents:
            typer.echo(f"- {agent_name}")
    else:
        typer.echo("- None")
    typer.echo()
    typer.echo("Generated patches:")
    if session.generated_patches:
        for index, patch in enumerate(session.generated_patches, start=1):
            typer.echo(f"{index}. {patch['id']} -> {patch['target_file']}")
    else:
        typer.echo("- None")
    typer.echo()


def _echo_dev_cycle_completion(result: DevRunResult, *, approved: bool) -> None:
    if not approved:
        typer.echo()
        typer.echo("No changes were applied.")
    else:
        typer.echo()
        if result.generated_patches:
            typer.echo("Applying patches...")
            if result.applied_patches:
                for patch in result.applied_patches:
                    typer.echo(f"[ok] Applied {patch['id']}")
            else:
                typer.echo("[ok] No proposed patches to apply")
        else:
            typer.echo("No patches were generated.")

        if result.test_status != "not_run":
            typer.echo()
            typer.echo("Running tests...")
            if result.test_command:
                typer.echo(f"[ok] Detected command: {' '.join(result.test_command)}")
            else:
                typer.echo("[warn] No test command was selected")

            if result.test_status == "passed":
                typer.echo("[ok] Tests passed")
            else:
                typer.echo(f"[warn] Tests ended with status: {result.test_status}")

    decision = result.planner_decisions[-1] if result.planner_decisions else {}
    typer.echo()
    typer.echo("Planner decision:")
    notes = decision.get("notes", [])
    if isinstance(notes, list):
        for note in notes:
            typer.echo(f"- {note}")
    if decision.get("next_action"):
        typer.echo(f"- Next action: {decision['next_action']}")
    if decision.get("recommended_focus"):
        typer.echo(f"- Focus: {decision['recommended_focus']}")


def _echo_dev_continue(result: DevRunResult) -> None:
    typer.echo()
    if result.test_status == "passed":
        typer.echo("Tests passed.")
    else:
        typer.echo("Tests failed.")
    typer.echo("Planner decision:")
    typer.echo("- Continue to another cycle.")
    decision = result.planner_decisions[-1] if result.planner_decisions else {}
    focus = decision.get("recommended_focus")
    if focus:
        typer.echo(f"- Focus: {focus}.")


def _echo_dev_final_result(result: DevRunResult) -> None:
    typer.echo()
    typer.echo("Final verdict:")
    typer.echo(result.final_verdict)
    typer.echo()
    typer.echo("Artifacts:")
    typer.echo(str(result.run_directory))


if __name__ == "__main__":
    app()
