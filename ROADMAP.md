# AgentForge Roadmap

## Phase 0: Project Definition

**Goal:** Define the project scope, MVP, architecture, and example configs.

**Status:** Implemented.

**Deliverables:**

- `README.md`
- `SPEC.md`
- `ROADMAP.md`
- `ARCHITECTURE.md`
- Example agent YAML files
- Example workflow YAML file

## Phase 1: YAML-Driven Workflow Runner

**Goal:** Build the first working CLI version.

**Status:** Implemented.

**Features:**

- Load workflow YAML
- Load agent YAML files
- Validate configs with Pydantic
- Run agents sequentially
- Use mock LLM client
- Maintain shared state
- Write trace and result files

**Command:**

```bash
agentforge run examples/workflows/basic_feature.yaml --input "Add a todo endpoint to a FastAPI app"
```

**Artifacts:**

```text
.agentforge/runs/<run_id>/
  input.txt
  state.json
  trace.json
  final_report.md
```

**Default agents:**

- Planner Agent
- Frontend Agent
- Backend Agent
- Testing Agent
- Reviewer Agent

## Phase 2: Read-Only Tool System

**Goal:** Let agents inspect a project directory through controlled, read-only tools.

**Status:** Implemented.

**Implemented tools:**

- `list_files`
- `read_file`
- `search_files`
- `inspect_tree`

**Implemented features:**

- Tool registry
- Agent `allowed_tools` validation
- Deterministic tool context gathered by the runner
- Project-root sandboxing
- Path traversal rejection
- `tool_calls.json` artifact
- `--project-root` CLI option
- `--no-project-context` CLI option
- Default project root behavior using the current working directory

**Important constraints:**

- No file writing.
- No patch generation.
- No test execution tool.
- No dynamic agent-decided tool calling.

Phase 2 lets agents understand a project directory before proposing plans. It does not let agents modify files.

## Phase 3: Patch Proposal System

**Goal:** Let agents propose code changes without immediately applying them.

**Status:** Implemented.

**Implemented features:**

- Agent `produces_patches` config field, defaulting to `false`
- Deterministic mock patch proposal generation for patch-producing agents
- Readable unified-diff-like files written under `.agentforge/runs/<run_id>/patches/`
- Run-level `patch_manifest.json` artifact
- `patch_manifest.json` always written, with `[]` when no patches are proposed
- Patch proposal summaries and patch file paths in `final_report.md`

**Important constraints:**

- Patches are artifacts only.
- Patches are not applied in Phase 3.
- Project source files are not modified by patch proposal generation.
- File modification is intentionally deferred to Phase 4.
- Humans remain in control of future approval and application decisions.

The system should still avoid direct autonomous source modification.

## Phase 4: Human-Approved Patch Application

**Goal:** Safely apply approved patches.

**Status:** Planned.

**Features:**

- Patch review command
- Patch apply command
- Patch rejection flow
- Backup or rollback strategy
- Clear reporting of modified files

**Example future commands:**

```bash
agentforge patch review
agentforge patch apply <patch_id>
```

## Phase 5: Test Execution and Debugging Loop

**Goal:** Run tests and let a debugging agent respond to failures.

**Status:** Planned.

**Features:**

- `run_tests` tool
- Test output capture
- Failure parsing
- Debugger Agent
- Max retry limit
- Trace logging for each debug attempt

**Example future flow:**

```text
Apply approved patch
  |
  v
Run tests
  |
  v
If tests fail, Debugger Agent proposes a fix
  |
  v
User approves or rejects
  |
  v
Run tests again
```

## Future Phase: Agent-Decided Dynamic Tool Calling

**Goal:** Allow an agent step to request tool calls dynamically during model interaction.

**Status:** Planned.

This is intentionally not part of Phase 2. Phase 2 uses deterministic runner-gathered context based on `allowed_tools`.

**Potential features:**

- Tool call request schema
- Tool call result messages
- Tool permission enforcement
- Tool call limits
- Safer error handling for model-requested tools
- Richer tool observability

## Phase 6: Python SDK

**Goal:** Make AgentForge usable as a Python library.

**Status:** Planned.

Example:

```python
from agentforge import Workflow

workflow = Workflow.from_file("examples/workflows/basic_feature.yaml")
result = workflow.run("Add a todo endpoint")
print(result.final_report)
```

The SDK should expose the core workflow engine without requiring the CLI.

## Phase 7: Local Dashboard

**Goal:** Add a local dashboard for visual workflow execution.

**Status:** Planned.

**Features:**

- Run workflow from UI
- Choose workflow
- Enable or disable agents
- Inspect shared state
- Inspect trace logs
- Inspect tool call logs
- Review patches
- View test output
- Compare runs

The dashboard should come after the CLI and SDK are stable.

## Phase 8: Dockerized Local Platform

**Goal:** Let users run the full platform locally with Docker.

**Status:** Planned.

Example command:

```bash
docker compose up
```

Expected local interface:

```text
http://localhost:3000
```

This phase supports the long-term goal of a locally hosted tool where users bring their own API keys.

## Phase 9: Custom Agent Creation

**Goal:** Let users create and configure their own agents.

**Status:** Planned.

**Features:**

- Agent templates
- Prompt editor
- Tool permission selection
- Model selection
- Input/output schema selection
- Import/export agent configs
- Save agents as YAML

This phase moves AgentForge closer to a plug-and-play agent workflow platform.

## Phase 10: Workflow Library

**Goal:** Provide reusable development workflows.

**Status:** Planned.

**Possible workflows:**

- Full-stack feature planning
- Frontend component design
- Backend endpoint design
- Test generation
- Bug investigation
- Security review
- Documentation generation
- Deployment preparation
- Database migration planning

## Phase 11: Non-Technical Guided Mode

**Goal:** Make AgentForge useful for less technical users.

**Status:** Planned.

**Features:**

- Plain-English project intake
- Workflow recommendation
- Agent recommendation
- Guided approval checkpoints
- Simplified explanations of technical decisions
- Safer defaults

This phase supports the broader goal of making high-quality software workflows more accessible to non-technical users.

## Long-Term Vision

AgentForge becomes a local-first platform for composing specialist software-development agents through CLI, SDK, and dashboard interfaces.

Users should eventually be able to:

- Plug in their own API keys
- Choose which agents to use
- Create custom agents
- Run workflows locally
- Inspect every intermediate step
- Approve or reject generated changes
- Use the tool from terminal, Python code, or local dashboard
