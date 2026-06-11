# AgentForge Architecture

## Current Architecture

AgentForge is currently a local-first CLI workflow engine with deterministic read-only project inspection, patch proposal artifacts, human-approved patch application, and safe project test command execution.

```text
CLI
 |
 v
Workflow Loader
 |
 v
Agent Loader
 |
 v
Workflow Runner
 |
 +--> Shared State
 |
 +--> Tool Context
 |      |
 |      v
 |    Tool Registry
 |      |
 |      v
 |    Filesystem Tools
 |
 v
Mock LLM Client
 |
 +--> Patch Proposal Writer
 |
 v
Run Artifacts
 |
 v
Patch Review CLI
 |
 v
Selected Project File

Test CLI
 |
 v
ProjectScanner -> ProjectEvidence -> TestCommandDetector -> TestCommandCandidate[]
 |
 v
CommandSafetyValidator
 |
 v
TestRunner -> Test Artifacts
```

Phase 1 proved the YAML-driven sequential workflow runner. Phase 2 added a controlled read-only tool layer for inspecting a project directory before each agent runs. Phase 3 added reviewable patch proposal artifacts for agents configured with `produces_patches: true`. Phase 4 added explicit CLI commands for listing, showing, and applying one selected patch proposal. Phase 5 added deterministic test command detection and execution.

AgentForge still does not automatically apply patches, call real LLM APIs, run tests as an agent tool, commit changes to Git, or let agents dynamically choose tools. Source modification requires a human to invoke `agentforge patch apply` with a run ID, patch ID, and project root.

## Phase 2 Tool Flow

```text
CLI -> Workflow Runner -> Agent -> Tool Context -> Tool Registry -> Filesystem Tools -> Run Artifacts
```

Detailed flow:

1. The CLI parses the workflow path, user input, and project context options.
2. The workflow runner loads the workflow and agent configs.
3. Before each agent runs, the runner reads that agent's `allowed_tools`.
4. The runner calls the allowed read-only tools deterministically.
5. Tool output is formatted into `tool_context`.
6. The mock LLM client receives the agent config plus normal state inputs and `tool_context`.
7. Agents configured with `produces_patches: true` ask the configured patch generator for deterministic mock patch proposal artifacts.
8. Agent outputs, trace events, tool call records, patch files, and the patch manifest are written to run artifacts.

Dynamic LLM-directed tool calling and intelligent patch target selection are intentionally deferred to later phases.

## Phase 4 Patch Flow

```text
CLI -> Patch Review Service -> Run Patch Manifest -> Selected Diff -> Project Root
```

Detailed flow:

1. The user runs `agentforge patch list <run_id>` to see proposal IDs, agents, targets, statuses, and titles.
2. The user runs `agentforge patch show <run_id> <patch_id>` to inspect one diff.
3. The user runs `agentforge patch apply <run_id> <patch_id> --project-root <path>` to approve one selected patch.
4. The patch review service validates the run ID, manifest, patch ID, patch file path, and target path.
5. The target path must be relative, must not contain `../`, must not target `proposed/`, and must resolve inside `project_root`.
6. The service applies the unified diff to the manifest's target file.
7. After the file write succeeds, the selected manifest entry is updated from `proposed` to `applied`.

Phase 4 does not run tests, start a debugging loop, or commit changes to Git.

## Phase 5 Test Flow

```text
CLI -> ProjectScanner -> ProjectEvidence -> TestCommandDetector -> TestCommandCandidate[]
    -> CommandSafetyValidator -> TestRunner -> Test Artifacts
```

Detailed flow:

1. The user runs `agentforge test detect --project-root <path>` or `agentforge test run --project-root <path>`.
2. If `--command` is provided to `test run`, it becomes the highest-priority candidate.
3. Otherwise, `ProjectScanner` gathers deterministic evidence from the project tree, docs, GitHub Actions workflows, Makefiles, package scripts, test files, and Python/Django indicators.
4. `TestCommandDetector` turns that evidence into ranked `TestCommandCandidate` values.
5. `CommandSafetyValidator` rejects dangerous shell syntax, unsupported command forms, and working directories outside `project_root`.
6. `TestRunner` executes the selected command with `shell=False` and a default 30-second timeout unless `--timeout` overrides it.
7. If the command exceeds the timeout, AgentForge records `status: "timeout"`, `timed_out: true`, `timeout_seconds`, and any available stdout or stderr.
8. `test_results.json` and `test_output.txt` are written under `.agentforge/test-runs/<run_id>/`.

Phase 5 is deterministic. It does not use an LLM, start a debugger loop, apply patches, or commit changes.

## Components

### CLI

The CLI is the user's first interface.

Primary command:

```bash
agentforge run <workflow_path> --input "<request>"
```

Patch review commands:

```bash
agentforge patch list <run_id>
agentforge patch show <run_id> <patch_id>
agentforge patch apply <run_id> <patch_id> --project-root <path>
```

Test commands:

```bash
agentforge test detect --project-root <path>
agentforge test run --project-root <path>
agentforge test run --project-root <path> --timeout 30
agentforge test run --project-root <path> --command "pytest"
agentforge test run --project-root <path> --command "pytest" --timeout 30
```

Project context options:

```bash
agentforge run <workflow_path> --input "<request>" --project-root <path>
agentforge run <workflow_path> --input "<request>" --no-project-context
```

Responsibilities:

- Parse command-line arguments
- Receive user input
- Validate mutually exclusive project context flags
- Invoke the workflow runner
- Print the run directory and final status
- List patch proposal metadata for a previous run
- Print one selected patch diff
- Apply one selected patch only after explicit user invocation
- Detect and safely run likely project test commands

The CLI stays thin. Most logic lives in the core engine and the dedicated test execution package.

### Config Loader

The config loader loads YAML files and validates them.

Responsibilities:

- Load workflow YAML
- Load agent YAML
- Validate required fields
- Validate that `allowed_tools` is a list of strings
- Raise clear errors for invalid configs
- Resolve agent file paths from workflow configs

The config loader uses safe YAML parsing and Pydantic schema validation.

### Agent

An agent represents one specialist role in the workflow.

Responsibilities:

- Store agent configuration
- Identify required input keys
- Declare allowed read-only tools
- Declare whether it produces patch proposal artifacts
- Return output for its configured output key

In the current implementation, agents use a mock LLM client. Future versions may call real model providers.

### Workflow

A workflow represents an ordered list of agents.

Responsibilities:

- Store workflow metadata
- Store agent order
- Define the composition of a development process

The current runner supports sequential workflows only. Future versions may support graph-based workflows with branching, loops, and approval gates.

### Workflow Runner

The workflow runner executes the workflow.

Responsibilities:

- Initialize shared state
- Resolve project context behavior
- Initialize the tool registry when project context is enabled
- Gather deterministic tool context from each agent's `allowed_tools`
- Run agents in order
- Check that required input keys exist
- Update state after each agent
- Generate deterministic patch proposals for patch-producing agents
- Record trace events
- Record tool call events
- Save run artifacts

The runner is the core engine. It, not the LLM, decides which Phase 2 tools are called.

### Shared State

Shared state stores information across the workflow run.

Initial state:

```json
{
  "user_request": "Add a todo endpoint to a FastAPI app"
}
```

Example state after the workflow:

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

Design rule: agents communicate through shared state, not direct hidden messages.

### Tools Package

The `src/agentforge/tools` package contains the Phase 2 tool system.

Current modules:

- `base.py` - base `Tool` abstraction and `ToolError`
- `registry.py` - `ToolRegistry` and registry errors
- `filesystem.py` - read-only filesystem tools and project-root sandbox
- `__init__.py` - public exports

The package is intentionally small. It provides controlled, read-only project inspection rather than a general plugin system.

### Tool Registry

The tool registry stores reusable tools by name.

Responsibilities:

- Register available tools
- Retrieve tools by name
- Reject unknown tools with clear errors

In Phase 2, the registry is initialized with the filesystem tools for a single project root.

### Filesystem Tools

Current read-only tools:

- `list_files`
- `read_file`
- `search_files`
- `inspect_tree`

Responsibilities:

- Inspect only files under the configured project root
- Return relative paths where applicable
- Ignore common junk directories
- Reject unsafe file paths
- Avoid writing, modifying, deleting, or patching files

### Project Root Sandbox

The filesystem sandbox constrains tool access to one project root.

Project root behavior:

- `--project-root <path>` uses the provided directory.
- Omitting `--project-root` uses the current working directory.
- `--no-project-context` disables tools for the run.

Safety behavior:

- Path traversal is rejected.
- Absolute file paths are rejected for file reads.
- Directory reads through `read_file` are rejected.
- Files outside `project_root` cannot be read.

### Trace Logger

The trace logger records agent execution history.

Example event:

```json
{
  "agent": "frontend",
  "input_keys": ["user_request", "plan"],
  "output_key": "frontend_plan",
  "status": "success",
  "timestamp": "2026-06-01T12:00:00Z"
}
```

Responsibilities:

- Record agent execution order
- Record inputs and output keys used
- Record success or failure
- Record timestamps
- Support future debugging and dashboard visualization

### Tool-Call Logging

Tool-call logging records deterministic tool calls made by the runner.

Each record includes:

- Agent name
- Tool name
- Status
- Input
- Output preview
- Timestamp
- Error, if applicable

This data is written to `tool_calls.json`. It gives future dashboards a clean observability surface for showing which tools ran, what context was gathered, and where failures occurred.

### Patch Proposal System

The `src/agentforge/patches` package contains the patch proposal and review system.

Current modules:

- `mock_generator.py` - deterministic sample-project patch generation for tests and examples
- `models.py` - `PatchProposal` artifact model
- `review.py` - manifest loading, diff inspection, safe selected-patch application
- `writer.py` - patch file writing under the run artifact directory
- `__init__.py` - public exports

Patch-producing agents emit one deterministic mock proposal per successful agent step through the configured `PatchGenerator`. The default `DeterministicPatchGenerator` uses an explicit sample-project target list so tests can apply real diffs to real files. This is temporary mock behavior, not a production file-selection strategy and not a mapping from agent names to files.

The patch writer only writes under the run directory. It does not apply diffs, open Git, execute tests, or modify the inspected project root.

The patch review service is independent of patch generation. It applies one selected diff only when the user runs `agentforge patch apply`, using the `target_file` stored in `patch_manifest.json`. It rejects absolute target paths, path traversal, `proposed/` targets, missing patch IDs, missing patch files, and targets that resolve outside `project_root`. It does not run tests or commit changes to Git after applying a patch.

### Mock LLM Client

The mock LLM client simulates LLM responses for local testing.

Reasons for using a mock first:

- Avoids API costs
- Avoids nondeterminism
- Makes tests reliable
- Lets the engine be tested before integrating real model providers

The mock client returns deterministic output that includes the agent name and input summary.

### Run Artifacts

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

Patch proposal files are written under:

```text
patches/
```

Responsibilities:

- Preserve the original user request
- Save final shared state
- Save trace events
- Save tool call records
- Save patch proposal manifests and diff files
- Generate a human-readable report

Run artifacts make AgentForge inspectable and reproducible. They are generated output and should not be committed.

## Future Architecture

The next architecture work stays CLI-first. Phases 6-10 should complete the command-line product and core engine before the Python SDK and dashboard call into the same stable internals.

```text
CLI
 |
 v
Core Engine
 |
 +--> Agent and Workflow Configs
 |
 +--> Tool Registry
 |
 +--> Patch Review Service
 |
 |
 +--> Debugger Loop
 |
 +--> LLM Provider Layer
 |
 v
Run Artifacts

Later surfaces:

Python SDK -> Core Engine
Dashboard  -> Core Engine
```

## Current and Future Components

### Test Execution System

Runs explicit or auto-detected project test commands from the CLI and captures stdout, stderr, exit code, duration, timeout status, and `timeout_seconds`. The default timeout is 30 seconds.

Artifacts:

- `test_results.json`
- `test_output.txt`

The implemented pipeline is:

```text
ProjectScanner -> ProjectEvidence -> TestCommandDetector -> TestCommandCandidate[]
    -> CommandSafetyValidator -> TestRunner
```

Phase 5 does not include a debugger loop or automatic patch application.

### Debugger Loop

Uses failed test output as context for a debugger agent. The debugger may propose follow-up patch artifacts, but humans still review and apply patches explicitly.

### LLM Provider Layer

Abstracts model providers.

Possible providers:

- OpenAI-compatible APIs
- Local Ollama
- Other local providers

The provider layer should allow users to bring their own API keys through environment variables. Secrets should not be hardcoded. The mock provider should remain available for deterministic tests.

### Dynamic Tool Calling

Allows model outputs to request tool calls during an agent step.

Dynamic tool calling must enforce `allowed_tools`, validate tool inputs, record tool calls, cap tool iterations, and preserve project-root sandbox boundaries.

### Agent and Workflow Config Management

Adds CLI support for validating, listing, and creating agent and workflow configs. Templates and a local config registry can be added if they make common workflows easier to manage.

### CLI UX Layer

Improves command structure, help text, error messages, latest-run shortcuts, readable output tables, and optional `--json` or `--verbose` modes.

### Patch System

Allows agents to propose file changes as patches instead of directly modifying files.

Design rule: the system requires human approval before applying patches. The current CLI supports explicit single-patch application; future phases may add richer review metadata, rollback, and reporting.

### Python SDK

Exposes the stable core engine through a Python API after the CLI product is complete.

### Dashboard

Provides a local visual interface after the CLI and SDK foundations are stable.

Expected views include:

- Running workflows
- Viewing traces
- Viewing tool call logs
- Reviewing patches
- Inspecting test output
- Inspecting debugger loops
- Managing agents and workflows
- Comparing runs

## Design Principles

- CLI product before SDK or dashboard
- Local-first execution
- Mock before real LLM
- Sequential before graph-based
- Inspectable before autonomous
- Safe before automatic
- Artifacts before hidden state
- Explicit workflows before hidden behavior
- Shared state before unstructured message passing
- Human approval before file modification
- Composable agents before monolithic assistants
