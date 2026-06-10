# AgentForge Specification

## Project Summary

AgentForge is a local-first composable agent workflow engine for software development.

It lets users define specialist agents, compose them into workflows, run those workflows through a CLI, inspect intermediate outputs, and eventually approve generated code changes safely.

## Core Thesis

Modern AI coding tools are powerful but often monolithic and opaque. AgentForge applies the Unix philosophy of composability to AI-assisted development by making software-development agents small, configurable, inspectable, and composable.

Instead of one general assistant attempting to perform the entire development process, AgentForge separates the process into specialized roles such as planning, frontend design, backend design, testing, security review, debugging, documentation, and DevOps.

## Current Scope

Phase 1 implemented the YAML-driven workflow runner.

Phase 2 implemented a read-only project inspection tool system. The runner can now gather deterministic project context for agents from controlled filesystem tools before calling the mock LLM client.

Phase 3 implemented patch proposal artifacts. Patch-producing agents can now emit deterministic, reviewable diff files and a run-level patch manifest.

Phase 4 implemented human-approved patch review and application commands. A user can list proposals for a run, inspect one diff, and explicitly apply one selected patch to a provided project root.

The current scope is still intentionally limited. AgentForge does not automatically apply patches, execute tests as an agent tool, commit changes to Git, integrate real LLM APIs, provide a dashboard, or let agents dynamically decide which tools to call. File modification only happens after an explicit `agentforge patch apply <run_id> <patch_id> --project-root <path>` command.

## User Story

As a developer, I can run:

```bash
agentforge run examples/workflows/basic_feature.yaml --input "Add a todo endpoint to a FastAPI app"
```

Then AgentForge runs the configured agents in order, uses the current working directory as read-only project context, and writes:

```text
.agentforge/runs/<run_id>/
  input.txt
  state.json
  trace.json
  tool_calls.json
  patch_manifest.json
  patches/
  final_report.md
```

If I want to inspect a different directory, I can run:

```bash
agentforge run examples/workflows/basic_feature.yaml --input "Add a todo endpoint to a FastAPI app" --project-root examples/sample_project
```

If I want to disable project context entirely, I can run:

```bash
agentforge run examples/workflows/basic_feature.yaml --input "Add a todo endpoint to a FastAPI app" --no-project-context
```

Then I can review and apply patch proposals from that run:

```bash
agentforge patch list <run_id>
agentforge patch show <run_id> <patch_id>
agentforge patch apply <run_id> <patch_id> --project-root examples/sample_project
```

## Workflow

The initial workflow is:

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

Each agent reads specific keys from shared state and writes one new output key back into state.

## Included Capabilities

- Python package
- Typer CLI
- YAML agent configs
- YAML workflow configs
- Pydantic config validation
- Sequential workflow runner
- Shared workflow state
- Mock LLM client
- Trace logging
- Read-only project inspection tools
- Tool registry
- Tool call logging
- Patch proposal artifacts
- Human-approved patch review and application commands
- Saved run artifacts
- Basic tests

## Excluded Capabilities

AgentForge currently does not include:

- Real LLM API integrations
- LangGraph
- Dashboard
- SDK
- Docker
- Automatic patch application
- Filesystem modification by agents
- Git integration
- Test execution as an agent tool
- User accounts
- Agent marketplace
- Autonomous app generation
- Custom agent creation UI
- Dynamic agent-decided tool calling

These exclusions are intentional. The early phases build a reliable, understandable, and safe engine before adding more powerful surfaces.

## Core Objects

### Agent

An agent is a configured specialist role.

Required fields:

- `name`
- `description`
- `system_prompt`
- `input_keys`
- `output_key`
- `allowed_tools`

Optional fields:

- `produces_patches` defaults to `false`

Example:

```yaml
name: frontend
description: Proposes frontend implementation details.
system_prompt: |
  You are a frontend engineering agent specializing in React and TypeScript.
input_keys:
  - user_request
  - plan
output_key: frontend_plan
allowed_tools:
  - inspect_tree
  - list_files
  - search_files
produces_patches: true
```

### Workflow

A workflow defines a sequence of agents.

Required fields:

- `name`
- `description`
- `agents`

Example:

```yaml
name: basic_feature
description: A simple sequential workflow for planning a full-stack feature.
agents:
  - examples/agents/planner.yaml
  - examples/agents/frontend.yaml
  - examples/agents/backend.yaml
  - examples/agents/testing.yaml
  - examples/agents/reviewer.yaml
```

### State

State stores all information produced during a workflow run.

Initial state:

```json
{
  "user_request": "Add a todo endpoint to a FastAPI app"
}
```

Example state after the full workflow:

```json
{
  "user_request": "Add a todo endpoint to a FastAPI app",
  "plan": "...",
  "frontend_plan": "...",
  "backend_plan": "...",
  "test_plan": "...",
  "review": "..."
}
```

### Tool

A tool is a controlled capability that can be exposed to agents by the runner.

Phase 2 tools are read-only filesystem inspection tools:

- `list_files`
- `read_file`
- `search_files`
- `inspect_tree`

Each tool accepts explicit inputs, runs inside the configured project root sandbox, and returns structured or text output. Tools must not modify project files.

### Tool Registry

The tool registry stores available tools by name and lets the runner retrieve them when an agent is configured to use them.

The registry is intentionally simple in Phase 2. It provides controlled lookup, not dynamic LLM-directed tool calling.

### `allowed_tools`

`allowed_tools` is the list of tool names an agent is allowed to receive context from.

The runner deterministically gathers tool context from this list before each agent runs. The LLM does not choose tools at runtime in Phase 2.

`allowed_tools` must be a list of strings.

### Patch Proposal

A patch proposal is a reviewable code change artifact. Phase 3 generates deterministic mock proposals for agents configured with:

```yaml
produces_patches: true
```

Each proposal includes:

- `id`
- `agent_name`
- `title`
- `description`
- `target_file`
- `patch_file`
- `status`
- `diff`

Patch files use a readable unified-diff-like format and are written under:

```text
.agentforge/runs/<run_id>/patches/
```

Patch proposals are not applied during workflow execution. They do not modify the inspected `project_root`; they are generated artifacts for human review.

Phase 4 adds these review commands:

```bash
agentforge patch list <run_id>
agentforge patch show <run_id> <patch_id>
agentforge patch apply <run_id> <patch_id> --project-root <path>
```

`patch apply` applies only the selected proposal after explicit command invocation and changes that proposal's manifest status from `proposed` to `applied`.

Patch proposal `target_file` values must be project-relative source or test files. The current deterministic mock generator uses sample-project fixture targets such as `src/app.py`, `src/models.py`, and `tests/test_app.py` only to exercise patch artifact and application behavior. Intelligent target selection is not implemented yet. Future versions will use project inspection, dynamic tool calling, and real model output to choose target files.

Patch proposals must not point at `proposed/*.txt` files inside the project root.

### Trace

Trace records each step of a workflow run.

Each trace event includes:

- Agent name
- Input keys
- Output key
- Status
- Timestamp
- Error message, if applicable

Example:

```json
{
  "agent": "frontend",
  "input_keys": ["user_request", "plan"],
  "output_key": "frontend_plan",
  "status": "success",
  "timestamp": "2026-06-01T12:00:00Z"
}
```

## Project Context Behavior

Project context is enabled by default.

- If `--project-root <path>` is provided, `<path>` is used as the sandbox root.
- If `--project-root` is omitted and `--no-project-context` is not used, the current working directory is used as the sandbox root.
- If `--no-project-context` is used, no tools run and `tool_calls.json` is written as an empty list.
- `--project-root` and `--no-project-context` must not be used together.

## Tool Call Artifact Contract

Every run writes:

```text
tool_calls.json
```

Each record includes:

- `agent`
- `tool`
- `status`
- `input`
- `output_preview`
- `timestamp`
- `error`, when applicable

When project context is disabled, `tool_calls.json` contains:

```json
[]
```

## Patch Artifact Contract

Every run writes:

```text
patch_manifest.json
```

When patches are proposed, each manifest entry references a diff file under `patches/`. When no patches are proposed, `patch_manifest.json` contains:

```json
[]
```

The manifest is part of the run artifact contract and supports the Phase 4 review and approval flow. Patch statuses begin as `proposed`; after a successful explicit apply command, the selected proposal is updated to `applied`.

## Safety Requirements

- Tools are read-only.
- Tools are sandboxed to `project_root`.
- Path traversal must be rejected.
- Absolute paths must be rejected for file reads.
- Directory reads through `read_file` must be rejected.
- Large files should be rejected or skipped according to tool behavior.
- Patch proposals must be written only as run artifacts.
- Patch proposals must not be applied during workflow execution.
- Patch application must require `--project-root`.
- Patch application must apply only the selected patch ID.
- Patch target paths must be relative paths inside `project_root`.
- Absolute patch target paths must be rejected.
- `../` traversal in patch target paths must be rejected.
- `proposed/` patch targets inside `project_root` must be rejected.
- Patch targets that resolve outside `project_root` must be rejected.
- Missing patch IDs and missing patch files must fail with clear errors.
- Phase 4 must not run tests after applying a patch.
- Phase 4 must not commit changes to Git.
- Project source files must not be modified by patch proposal generation.
- Generated run artifacts under `.agentforge/runs/` are not source files and should not be committed.

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

Responsibilities:

- Preserve the original user request
- Save final shared state
- Save trace events
- Save tool call records
- Save patch proposal manifests and patch files
- Generate a human-readable report

Run artifacts make AgentForge inspectable and reproducible.

## Design Principles

1. Build the engine before the dashboard.
2. Prefer explicit workflows over hidden autonomous behavior.
3. Make every agent output inspectable.
4. Use structured state instead of unstructured message passing.
5. Require human approval before file modifications.
6. Use mock LLMs before real LLM APIs.
7. Keep early phases small enough to fully understand.
8. Treat agents as composable modules, not magical autonomous workers.
9. Make workflow runs reproducible and debuggable.
10. Prioritize safety and clarity before automation power.

## Long-Term Product Vision

AgentForge should eventually support:

- CLI execution
- Python SDK usage
- Local dashboard
- Dockerized local deployment
- Configurable agents
- Custom workflows
- Tool permissions
- Patch proposals
- Human-approved file changes
- Test execution
- Debugging loops
- Git integration
- Trace visualization
- User-provided API keys
- Model-provider flexibility

The long-term goal is to help technical and semi-technical users build better software by composing specialized AI agents into inspectable development workflows.
