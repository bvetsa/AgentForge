# AgentForge Roadmap

## Project Direction

AgentForge is a CLI-first, local-first developer tool for composable agent workflows. The CLI and core engine should become stable, useful, inspectable, and safe before AgentForge adds SDK or dashboard surfaces.

Completed phases establish workflow execution, read-only project inspection, patch proposal artifacts, explicit human-approved patch application, and safe test execution. Planned phases should keep file modification safety, artifact visibility, and command-line ergonomics as the primary product constraints.

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

**Status:** Implemented.

**Implemented features:**

- `agentforge patch list <run_id>`
- `agentforge patch show <run_id> <patch_id>`
- `agentforge patch apply <run_id> <patch_id> --project-root <path>`
- Human-approved application of one selected patch proposal
- `patch_manifest.json` status update from `proposed` to `applied`
- Missing patch ID and missing patch file errors
- Rejection of absolute patch target paths
- Rejection of `../` path traversal
- Rejection of targets that resolve outside `project_root`
- Deterministic mock patch generation isolated from patch application

**Commands:**

```bash
agentforge patch list <run_id>
agentforge patch show <run_id> <patch_id>
agentforge patch apply <run_id> <patch_id> --project-root examples/sample_project
```

**Important constraints:**

- Patch application is never automatic.
- `--project-root` is required for patch application.
- Applying one patch does not apply every proposal in the run.
- The current mock generator uses sample-project fixture targets only to test the infrastructure.
- Intelligent file target selection is not implemented yet.
- Phase 4 does not run tests after applying patches.
- Phase 4 does not commit changes to Git.

## Phase 5: Test Execution System

**Goal:** Safely run configured project test commands and save their results.

**Status:** Implemented.

**Implemented features:**

- Deterministic project scanner for file tree, language extensions, package files, test files, docs, CI workflows, Makefile targets, package scripts, and Python/Django indicators
- Evidence-based test command detector with ranked candidates
- `agentforge test detect --project-root <path>`
- `agentforge test run --project-root <path>`
- Timeout override with `agentforge test run --project-root <path> --timeout 30`
- Explicit override with `agentforge test run --project-root <path> --command "pytest"`
- Explicit command plus timeout with `agentforge test run --project-root <path> --command "pytest" --timeout 30`
- Safe command execution boundaries
- Captured stdout
- Captured stderr
- Captured exit code
- Captured duration
- Default 30-second timeout and `timeout_seconds` recording
- Timeout status recorded as `status: "timeout"` with `timed_out: true`
- `test_results.json` artifact
- `test_output.txt` artifact

**Detection priority:**

1. Explicit `--command`
2. CI workflow test commands
3. README or CONTRIBUTING documented test commands
4. Task runner targets such as `make test`
5. Package manager scripts such as `npm test`
6. Framework-specific commands
7. Language default commands
8. No detection

**Initial safe command forms:**

- `pytest`
- `python -m pytest`
- `python manage.py test`
- `npm test`
- `npm run test`
- `make test`

**Important constraints:**

- No debugger loop yet.
- No automatic patch application.
- No Git commits.
- Test execution should be inspectable and reproducible from saved artifacts.
- Detected and user-provided commands pass through the same safety validator.
- Commands are run with `shell=False`.
- Dangerous shell operators are rejected.
- The selected working directory must resolve inside `project_root`.
- Long-running commands are stopped at the configured timeout and still write artifacts.

## Phase 6: Debugger Loop

**Goal:** Use failed test output as input for a debugger agent that proposes follow-up patches.

**Status:** Planned.

**Features:**

- Debugger Agent
- Failed test output passed into debugger context
- Follow-up patch proposal artifacts
- Trace logging for debugger attempts
- Clear stop conditions and retry limits

**Important constraints:**

- Human still reviews and applies patches.
- No automatic patch application.
- No hidden file modification.

## Phase 7: Real LLM Provider Layer

**Goal:** Add real model providers without losing deterministic tests.

**Status:** Planned.

**Features:**

- Provider abstraction
- Mock provider retained for tests
- OpenAI-compatible provider and/or Ollama/local provider
- Environment-variable configuration
- `.env.example`

**Important constraints:**

- Do not hardcode secrets.
- Keep provider behavior observable in artifacts where useful.
- Preserve reliable tests through the mock provider.

## Phase 8: Dynamic Agent-Decided Tool Calling

**Goal:** Allow agents to request tools during execution while preserving tool permissions and observability.

**Status:** Planned.

**Features:**

- Tool call request schema
- Tool call result messages
- `allowed_tools` enforcement
- Tool input validation
- Tool call recording
- Maximum tool-iteration caps
- Safe error handling for model-requested tools

**Important constraints:**

- Keep project-root sandboxing.
- Keep read/write boundaries explicit.
- Do not let dynamic tool calling bypass configured permissions.

## Phase 9: Custom Agents and Workflows

**Goal:** Improve CLI support for creating, validating, discovering, and organizing agent and workflow configs.

**Status:** Planned.

**Features:**

- CLI validation for agent and workflow configs
- CLI listing for available agents and workflows
- CLI creation commands for starter configs
- Templates for new agents and workflows
- Local config registry if appropriate

## Phase 10: CLI Cleanup and UX Polish

**Goal:** Make the command-line product complete, coherent, and pleasant to use before adding other surfaces.

**Status:** Planned.

**Features:**

- Improved command structure
- Better help text
- Better errors
- Latest-run shortcuts
- Readable output tables
- `--json` mode where appropriate
- `--verbose` mode where appropriate

## Phase 11: Python SDK

**Goal:** Expose the stable engine through a Python API after the CLI product is complete.

**Status:** Planned.

Example:

```python
from agentforge import Workflow

workflow = Workflow.from_file("examples/workflows/basic_feature.yaml")
result = workflow.run("Add a todo endpoint")
print(result.final_report)
```

The SDK should expose the core workflow engine without requiring the CLI.

## Phase 12: Dashboard

**Goal:** Add a visual interface after the CLI and SDK foundations are stable.

**Status:** Planned.

**Features:**

- Run workflows
- Inspect shared state
- Inspect trace logs
- Inspect tool call logs
- Review patches
- Inspect test results
- Inspect debugger loops
- Manage agents and workflows
- Compare runs

## Long-Term Vision

AgentForge becomes a local-first platform for composing specialist software-development agents. The CLI is the primary product surface until the engine, safety model, and developer workflows are complete.

Users should eventually be able to:

- Plug in their own API keys
- Choose which agents to use
- Create custom agents
- Run workflows locally
- Inspect every intermediate step
- Approve or reject generated changes
- Run configured tests and inspect results
- Use the tool from the terminal first, then from Python code or a local dashboard
