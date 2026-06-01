# AgentForge Roadmap

## Phase 0: Project Definition

**Goal:** Define the project scope, MVP, architecture, and example configs.

**Deliverables:**

- `README.md`
- `SPEC.md`
- `ROADMAP.md`
- `ARCHITECTURE.md`
- Example agent YAML files
- Example workflow YAML file

**Status:** Current phase.

## Phase 1: YAML-Driven Workflow Runner

**Goal:** Build the first working CLI version.

**Features:**

- Load workflow YAML
- Load agent YAML files
- Validate configs with Pydantic
- Run agents sequentially
- Use mock LLM client
- Maintain shared state
- Write trace and result files

**Expected command:**

```bash
agentforge run examples/workflows/basic_feature.yaml --input "Add a todo endpoint to a FastAPI app"
```

**Expected output:**

```text
.agentforge/runs/<run_id>/
  input.txt
  state.json
  trace.json
  final_report.md
```

**Default MVP agents:**

- Planner Agent
- Frontend Agent
- Backend Agent
- Testing Agent
- Reviewer Agent

## Phase 2: Tool System

**Goal:** Let agents use controlled tools.

**Initial read-only tools:**

- `list_files`
- `read_file`
- `search_files`
- `inspect_tree`

**Important constraint:** No file writing yet.

The purpose of this phase is to let agents understand a project directory before proposing changes.

## Phase 3: Patch Proposal System

**Goal:** Let agents propose code changes without immediately applying them.

**Features:**

- Generate patch proposals
- Write `.diff` files
- Show patch summaries
- Associate patches with workflow runs
- Require approval before applying patches

The system should still avoid direct autonomous file modification.

## Phase 4: Human-Approved Patch Application

**Goal:** Safely apply approved patches.

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

**Features:**

- `run_tests` tool
- Test output capture
- Failure parsing
- Debugger Agent
- Max retry limit
- Trace logging for each debug attempt

**Example future flow:**

```text
Apply patch
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

## Phase 6: Python SDK

**Goal:** Make AgentForge usable as a Python library.

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

**Features:**

- Run workflow from UI
- Choose workflow
- Enable or disable agents
- Inspect shared state
- Inspect trace logs
- Review patches
- View test output
- Compare runs

The dashboard should come after the CLI and SDK are stable.

## Phase 8: Dockerized Local Platform

**Goal:** Let users run the full platform locally with Docker.

Example command:

```bash
docker compose up
```

Expected local interface:

```text
http://localhost:3000
```

This phase supports the long-term goal of a locally hosted, free tool where users bring their own API keys.

## Phase 9: Custom Agent Creation

**Goal:** Let users create and configure their own agents.

**Features:**

- Agent templates
- Prompt editor
- Tool permission selection
- Model selection
- Input/output schema selection
- Import/export agent configs
- Save agents as YAML

This phase moves AgentForge closer to the original plug-and-play agent platform vision.

## Phase 10: Workflow Library

**Goal:** Provide reusable development workflows.

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

**Features:**

- Plain-English project intake
- Workflow recommendation
- Agent recommendation
- Guided approval checkpoints
- Simplified explanations of technical decisions
- Safer defaults

This phase supports the broader goal of making high-quality code generation more accessible to non-technical users.

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
