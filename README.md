# AgentForge

AgentForge is a local-first composable agent workflow engine for software development.

It applies the Unix philosophy to AI-assisted development by letting users define small specialist agents, compose them into workflows, inspect intermediate outputs, and eventually approve generated code changes safely.

## Project Thesis

Modern AI coding tools are powerful, but they are often monolithic and opaque. AgentForge treats AI-assisted development as a composable workflow problem: instead of relying on one large assistant to do everything, users can assemble smaller specialist agents for planning, frontend, backend, testing, security review, documentation, debugging, and other development tasks.

The long-term goal is to make high-quality AI-assisted software development more modular, inspectable, and configurable.

## Current Status

**Phase 1:** Implemented the YAML-driven workflow runner.

**Phase 2:** Implemented the read-only project inspection tool system.

**Phase 3:** Implemented patch proposal artifacts.

The current implementation is a CLI tool that loads YAML-defined agents and workflows, runs agents sequentially using a mock LLM client, passes structured shared state between agents, gathers deterministic read-only project context from configured tools, and writes traceable run artifacts. Agents can now be configured to produce reviewable patch proposal artifacts.

AgentForge still does not apply patches, modify project source files, execute tests as an agent tool, call real LLM APIs, or let agents dynamically decide which tools to call. File modification is intentionally deferred to Phase 4 so humans remain in control.

## Local Setup

Create a virtual environment and install the package with development tools:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

## Continuous Integration

GitHub Actions runs CI on pull requests and pushes to `main`. The workflow installs AgentForge with development dependencies, then runs `pytest`, `ruff check .`, and a CLI smoke test against `examples/workflows/basic_feature.yaml`.

## CLI Usage

Run a workflow with the current working directory as project context:

```bash
agentforge run examples/workflows/basic_feature.yaml --input "Add a todo endpoint to a FastAPI app"
```

Run a workflow with an explicit project root:

```bash
agentforge run examples/workflows/basic_feature.yaml --input "Add a todo endpoint to a FastAPI app" --project-root examples/sample_project
```

Run a workflow without project context:

```bash
agentforge run examples/workflows/basic_feature.yaml --input "Add a todo endpoint to a FastAPI app" --no-project-context
```

`--project-root` and `--no-project-context` are mutually exclusive.

## Read-Only Project Inspection Tools

Phase 2 adds a controlled tool layer for inspecting a project directory. Tools are selected from each agent's `allowed_tools` list and are called deterministically by the runner before that agent runs.

Available tools:

- `list_files` - recursively lists project files as relative paths
- `read_file` - reads one UTF-8 text file under the project root
- `search_files` - searches text files for a query and returns matching lines
- `inspect_tree` - returns a readable directory tree

Safety rules:

- Tools are read-only.
- Tools are sandboxed to the configured project root.
- Path traversal and absolute paths are rejected.
- Common junk directories such as `.git`, `.venv`, `__pycache__`, `node_modules`, `.pytest_cache`, and `.ruff_cache` are ignored.

Project root behavior:

- If `--project-root` is provided, that directory is used as the sandbox root.
- If `--project-root` is omitted and `--no-project-context` is not used, the current working directory is used.
- If `--no-project-context` is used, no tools run and `tool_calls.json` contains `[]`.

## Run Artifacts

Each workflow run writes artifacts to:

```text
.agentforge/runs/<run_id>/
```

Required files:

```text
input.txt
state.json
trace.json
tool_calls.json
patch_manifest.json
final_report.md
```

Patch proposal files, when generated, are written under:

```text
.agentforge/runs/<run_id>/patches/
```

Artifact purposes:

- `input.txt` stores the original user request.
- `state.json` stores the final shared workflow state.
- `trace.json` stores agent execution events.
- `tool_calls.json` stores deterministic tool call records, including agent, tool, status, input, output preview, timestamp, and error when applicable.
- `patch_manifest.json` stores the run-level list of patch proposals. It is always written and contains `[]` when no patches are proposed.
- `final_report.md` stores the human-readable agent output report.

Patch proposals are artifacts only. The current system writes readable unified-diff-like files for review, but it does not apply them or modify files in the inspected project root. Run artifacts are generated output, not source files. They should not be committed.

## Core Ideas

### Agents

Agents are small specialist roles. Each agent has a name, description, system prompt, input keys, output key, and allowed tools.

Agents may also set `produces_patches: true` to emit deterministic Phase 3 patch proposal artifacts. The default is `false`.

Example agents:

- Planner Agent
- Frontend Agent
- Backend Agent
- Testing Agent
- Reviewer Agent

### Workflows

Workflows compose agents into an ordered process.

The current workflow runner supports sequential workflows. Later versions may support graph-based workflows with branching, loops, human approval points, and conditional execution.

### Shared State

Agents communicate through shared state rather than directly messaging each other.

The initial state contains the user's request. Each agent reads required keys from state and writes its own output back to state.

### Trace Logs

Every workflow run produces trace data that records which agents ran, what inputs they used, which output key they wrote, and whether each step succeeded.

Trace logs and tool call logs make the system inspectable and debuggable.

## Example Workflow

The initial example workflow is:

```text
Planner Agent
  |
  v
Frontend Agent
  |
  v
Backend Agent
  |
  v
Testing Agent
  |
  v
Reviewer Agent
```

This workflow does not modify files. It inspects project context, then produces planning, review, and patch proposal artifacts for human review.

## Smoke Tests

Run the automated checks:

```bash
pytest
ruff check .
```

Run the default current-directory project context workflow:

```bash
agentforge run examples/workflows/basic_feature.yaml --input "Add a todo endpoint to a FastAPI app"
```

Run with an explicit project root:

```bash
agentforge run examples/workflows/basic_feature.yaml --input "Add a todo endpoint to a FastAPI app" --project-root examples/sample_project
```

Run without project context:

```bash
agentforge run examples/workflows/basic_feature.yaml --input "Add a todo endpoint to a FastAPI app" --no-project-context
```

## Long-Term Vision

AgentForge will eventually support three usage modes:

1. CLI interface
2. Python SDK
3. Local dashboard through Docker and localhost

The long-term product vision is a local-first platform where users can compose configurable specialist agents into development workflows, plug in their own API keys, inspect each step, approve code changes, and extend the system with custom agents.

## Documentation

- [SPEC.md](SPEC.md) - Project specification
- [ROADMAP.md](ROADMAP.md) - Phased implementation roadmap
- [ARCHITECTURE.md](ARCHITECTURE.md) - System architecture and design principles
