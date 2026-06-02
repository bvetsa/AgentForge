"""Command-line interface for AgentForge."""

from pathlib import Path
from typing import Annotated

import typer

from agentforge.config.loader import ConfigLoadError
from agentforge.core.runner import WorkflowExecutionError, WorkflowRunner

app = typer.Typer(help="Run composable software-development agent workflows.")


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
) -> None:
    """Run a YAML-defined workflow."""
    try:
        result = WorkflowRunner().run(workflow_path, input_text)
    except (ConfigLoadError, WorkflowExecutionError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(code=1) from error

    typer.echo(f"Workflow '{result.workflow_name}' completed successfully.")
    typer.echo(f"Run artifacts: {result.run_directory}")


if __name__ == "__main__":
    app()
