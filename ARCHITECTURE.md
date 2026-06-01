# AgentForge Architecture

## Initial Architecture

The MVP architecture is intentionally simple.

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
 v
Shared State
 |
 v
Mock LLM Client
 |
 v
Run Artifacts
```

The first version should prove the core workflow engine before adding real LLM APIs, tools, dashboards, SDKs, Docker, or file modification.

## MVP Workflow

The initial MVP workflow is sequential:

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

Each agent reads from shared state and writes one output back to shared state.

## Components

### CLI

The CLI is the user's first interface.

Primary command:

```bash
agentforge run <workflow_path> --input "<request>"
```

Responsibilities:

- Parse command-line arguments
- Receive user input
- Invoke the workflow runner
- Print the run directory and final status

The CLI should stay thin. Most logic should live in the core engine.

### Config Loader

The config loader loads YAML files and validates them.

Responsibilities:

- Load workflow YAML
- Load agent YAML
- Validate required fields
- Raise clear errors for invalid configs
- Resolve agent file paths from workflow configs

The config loader should use safe YAML parsing and schema validation.

### Agent

An agent represents one specialist role in the workflow.

Responsibilities:

- Store agent configuration
- Identify required input keys
- Build a prompt from shared state
- Call the LLM client
- Return output for its configured output key

In the MVP, agents call a mock LLM client. Future versions may call real model providers.

### Workflow

A workflow represents an ordered list of agents.

Responsibilities:

- Store workflow metadata
- Store agent order
- Define the composition of a development process

The MVP supports sequential workflows only. Future versions may support graph-based workflows with branching, loops, and approval gates.

### Workflow Runner

The workflow runner executes the workflow.

Responsibilities:

- Initialize shared state
- Run agents in order
- Check that required input keys exist
- Update state after each agent
- Record trace events
- Save run artifacts

The runner is the core of the MVP.

### Shared State

Shared state stores information across the workflow run.

Initial state:

```json
{
  "user_request": "Add a todo endpoint to a FastAPI app"
}
```

Example state after the MVP workflow:

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

Design rule: Agents communicate through shared state, not direct hidden messages.

### Trace Logger

The trace logger records execution history.

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
- Record inputs and outputs used
- Record success or failure
- Record timestamps
- Support future debugging and dashboard visualization

### Mock LLM Client

The mock LLM client simulates LLM responses for MVP testing.

Reasons for using a mock first:

- Avoids API costs
- Avoids nondeterminism
- Makes tests reliable
- Lets the engine be tested before integrating real model providers

The mock client should return deterministic output that includes the agent name and input summary.

### Run Artifacts

Each workflow run should write artifacts to:

```text
.agentforge/runs/<run_id>/
```

Required files:

```text
input.txt
state.json
trace.json
final_report.md
```

Responsibilities:

- Preserve the original user request
- Save final shared state
- Save trace events
- Generate a human-readable report

Run artifacts make AgentForge inspectable and reproducible.

## Future Architecture

The long-term architecture expands the MVP engine into a full platform.

```text
CLI / SDK / Dashboard
        |
        v
Workflow Engine
        |
        v
Agent Registry
        |
        v
Tool Registry
        |
        v
LLM Provider Layer
        |
        v
Patch / Test / Git Tools
        |
        v
Trace Store
```

## Future Components

### Agent Registry

Stores available agents and allows users to enable, disable, or create agents.

### Tool Registry

Stores reusable tools such as:

- List files
- Read file
- Search files
- Write patch proposal
- Run tests
- Inspect Git status
- Apply patch after approval

### LLM Provider Layer

Abstracts model providers.

Possible providers:

- OpenAI
- Anthropic
- Google
- Local Ollama
- Other OpenAI-compatible APIs

The provider layer should allow users to bring their own API keys.

### Patch System

Allows agents to propose file changes as patches instead of directly modifying files.

Design rule: The system should require human approval before applying patches.

### Test Runner

Runs project tests and captures output.

Future debugging workflows can use test output as input for a Debugger Agent.

### Dashboard

Provides a local visual interface for:

- Choosing workflows
- Enabling or disabling agents
- Viewing traces
- Reviewing patches
- Inspecting test output
- Comparing runs

## Design Principles

- Engine before dashboard
- CLI before UI
- Mock before real LLM
- Sequential before graph-based
- Inspectable before autonomous
- Safe before automatic
- Explicit workflows before hidden behavior
- Shared state before unstructured message passing
- Human approval before file modification
- Composable agents before monolithic assistants
