# AgentForge Specification

## Project Summary

AgentForge is a local-first composable agent workflow engine for software development.

It lets users define specialist agents, compose them into workflows, run those workflows through a CLI, inspect intermediate outputs, and eventually approve generated code changes safely.

## Core Thesis

Modern AI coding tools are powerful but often monolithic and opaque. AgentForge applies the Unix philosophy of composability to AI-assisted development by making software-development agents small, configurable, inspectable, and composable.

Instead of one general assistant attempting to perform the entire development process, AgentForge separates the process into specialized roles such as planning, frontend design, backend design, testing, security review, debugging, documentation, and DevOps.

## Product Direction

AgentForge is a CLI-first project. The command-line developer tool and core engine should become stable, useful, polished, and safe before SDK or dashboard surfaces are added.

The product should remain local-first, artifact-driven, and explicit about file modification. Agents and workflows should stay composable, and users should be able to inspect outputs, traces, tool calls, patches, and future test results before approving further action.

## Current Scope

Phase 1 implemented the YAML-driven workflow runner.

Phase 2 implemented a read-only project inspection tool system. The runner can now gather deterministic project context for agents from controlled filesystem tools before calling the mock LLM provider.

Phase 3 implemented patch proposal artifacts. Patch-producing agents can now emit deterministic, reviewable diff files and a run-level patch manifest.

Phase 4 implemented human-approved patch review and application commands. A user can list proposals for a run, inspect one diff, and explicitly apply one selected patch to a provided project root.

Phase 5 implemented deterministic project test command detection and safe execution. A user can run `agentforge test run --project-root <path>` without specifying a language, framework, or test command, or provide an explicit override with `--command`.

Phase 6 implemented the end-to-end dev pipeline. A user can run `agentforge dev run --input "<request>"`, inspect generated patches at the approval gate, approve all proposed patches interactively or with `--yes`, and then have AgentForge apply approved patches and run safe detected tests in one artifact directory.

Phase 7 implemented the planner-controlled iteration loop. If tests fail and cycles remain, the testing report goes back to the planner, the planner deterministically records `continue`, another implementation cycle runs, and approval is required again before applying patches.

The current scope is still intentionally limited. AgentForge does not have a separate debugger agent, commit changes to Git, integrate real LLM APIs, provide a dashboard, dynamically create workflows, perform real LLM planning, or let agents dynamically decide which tools to call. Debugging/repair behavior comes from cycling the end-to-end pipeline. File modification only happens after explicit human approval through `agentforge patch apply` or the dev pipeline approval gate.

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
  llm_calls.json
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

I can also detect or run project tests:

```bash
agentforge test detect --project-root .
agentforge test run --project-root .
agentforge test run --project-root . --timeout 30
agentforge test run --project-root . --command "pytest"
agentforge test run --project-root . --command "pytest" --timeout 30
```

I can run the planner-controlled development pipeline:

```bash
agentforge dev run --input "Add a todo endpoint to a FastAPI app"
agentforge dev run --project-root examples/sample_project --input "Add a todo endpoint to a FastAPI app"
agentforge dev run --project-root examples/sample_project --input "Add a todo endpoint to a FastAPI app" --yes
agentforge dev run --project-root examples/sample_project --input "Add a todo endpoint to a FastAPI app" --max-cycles 3
```

`--input` is required. `--project-root` is optional and defaults to the current working directory. `--workflow` is optional and defaults to `examples/workflows/basic_feature.yaml`. `--yes` applies all proposed patches in every cycle without prompting. `--max-cycles` defaults to `3`.

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
- Mock LLM provider
- Trace logging
- Read-only project inspection tools
- Tool registry
- Tool call logging
- Patch proposal artifacts
- Human-approved patch review and application commands
- Evidence-based project test command detection
- Safe project test execution
- End-to-end dev pipeline command
- Saved run artifacts
- Basic tests

## Excluded Capabilities

AgentForge currently does not include:

- Real LLM API integrations
- LangGraph
- Dashboard
- SDK
- Docker
- Unapproved automatic patch application
- Filesystem modification by agents
- Git integration
- Separate debugger agent
- User accounts
- Agent marketplace
- Autonomous app generation
- Custom agent creation UI
- Dynamic agent-decided tool calling
- Dynamic workflow creation
- Real LLM planning

These exclusions are intentional. The completed phases build a reliable, understandable, and safe CLI foundation before adding more powerful behavior or additional surfaces.

## Planned Direction

Planned work should proceed in this order:

1. Phase 8: Real LLM Provider Layer
2. Phase 9: Dynamic Agent-Decided Tool Calling
3. Phase 10: Custom Agents and Workflows
4. Phase 11: CLI Cleanup and UX Polish
5. Phase 12: Python SDK
6. Phase 13: Dashboard

Phases 8-11 continue the CLI and core engine work. The SDK and dashboard should come after the CLI product is stable.

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

### Dev Run Summary

Dev runs add `dev_run_summary.json` to the run artifact directory.

It records:

- `run_id`
- `user_request`
- `project_root`
- `workflow_path`
- `max_cycles`
- `status`
- `cycles`
- `generated_patches`
- `applied_patches`
- `test_status`
- `test_command`
- `planner_decisions`
- `final_verdict`

The dev pipeline uses one run directory for the whole flow:

```text
.agentforge/runs/<run_id>/
  input.txt
  state.json
  trace.json
  tool_calls.json
  llm_calls.json
  patch_manifest.json
  patches/
  test_results.json, if tests were run
  test_output.txt, if tests were run
  cycle_1_test_results.json, if cycle 1 ran tests
  cycle_1_test_output.txt, if cycle 1 ran tests
  final_report.md
  dev_run_summary.json
```

The approval stop point shows generated patches and changed files, then asks `Apply all proposed patches for cycle <n>? [y/N]:`. Default approval is no. Pressing Enter does not apply patches and does not run tests. `--yes` auto-approves every cycle.

Each cycle records generated patches, approval status, applied patches, a structured testing report, a planner decision, and a final verdict or stop reason. The testing report includes `status`, `summary`, `test_command`, `test_results_artifact`, `test_output_artifact`, and `recommended_focus`.

The planner is the controller. Testing results go back to the planner stage conceptually. If tests pass, the planner records `return_final_verdict` with reason `Tests passed.` If tests fail and the current cycle is below `max_cycles`, the planner records `continue`, a deterministic recommended focus such as `implementation`, and selected next-cycle agents such as `backend` and `testing`. If tests fail at `max_cycles`, the planner records `stopped_max_cycles`. If approval is declined, the planner records `stopped_user_declined`.

Reviewer/final verdict is only reached after the planner decision. Reviewer is not used for the pre-approval stop point.

Agent categories:

- Customer-facing agents: `planner`, `reviewer`
- Coding agents: `frontend`, `backend`
- Post-coding agents: `testing`

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

## LLM Call Artifact Contract

Every run writes:

```text
llm_calls.json
```

Each record includes the executed agent, invocation inputs, prompt text, response content, provider name, model name, provider metadata, output key, and timestamp.

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
- Dev pipeline approval defaults to no in every cycle.
- Dev pipeline must not apply patches before approval.
- Dev pipeline must not run tests if patches are not applied.
- Dev pipeline `--yes` may apply all proposed patches in every cycle without prompting.
- Dev pipeline patch application must still be sandboxed to `project_root`.
- Dev pipeline tests must still use safe Phase 5 test execution.
- Dev pipeline must not call reviewer before approval.
- Dev pipeline repair behavior must come from planner-controlled cycles, not a separate debugger agent.
- Real LLM planner reasoning, dynamic workflow creation, and dynamic tool calling are not implemented.
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
llm_calls.json
patch_manifest.json
final_report.md
```

Dev runs also write:

```text
dev_run_summary.json
test_results.json, if tests were run
test_output.txt, if tests were run
cycle_<n>_test_results.json, for each cycle that ran tests
cycle_<n>_test_output.txt, for each cycle that ran tests
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

1. Build the CLI and engine before the SDK or dashboard.
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
- Configurable agents
- Custom workflows
- Tool permissions
- Patch proposals
- Human-approved file changes
- Test execution
- Debugging loops
- Trace visualization
- User-provided API keys
- Model-provider flexibility

The long-term goal is to help developers build better software by composing specialized AI agents into inspectable local workflows. The CLI is the primary product surface until the engine, safety model, and developer workflows are complete.
