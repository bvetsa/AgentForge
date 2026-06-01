# AgentForge Specification

## Project Summary

AgentForge is a local-first composable agent workflow engine for software development.

It lets users define specialist agents, compose them into workflows, run those workflows through a CLI, inspect intermediate outputs, and eventually approve generated code changes safely.

## Core Thesis

Modern AI coding tools are powerful but often monolithic and opaque. AgentForge applies the Unix philosophy of composability to AI-assisted development by making software-development agents small, configurable, inspectable, and composable.

Instead of one general assistant attempting to perform the entire development process, AgentForge separates the process into specialized roles such as planning, frontend design, backend design, testing, security review, debugging, documentation, and DevOps.

## MVP Goal

The MVP is a CLI tool that loads YAML-defined agents and workflows, runs agents sequentially using a mock LLM client, passes structured shared state between agents, and stores run artifacts for inspection.

The MVP is designed to prove the core workflow engine before adding real LLMs, code modification, dashboards, SDK usage, or Dockerized deployment.

## MVP User Story

As a developer, I can run:

```bash
agentforge run examples/workflows/basic_feature.yaml --input "Add a todo endpoint to a FastAPI app"
```

Then AgentForge runs the configured agents in order and writes:

```text
.agentforge/runs/<run_id>/
  input.txt
  state.json
  trace.json
  final_report.md
```

## MVP Workflow

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

## MVP Includes

- Python package
- Typer CLI
- YAML agent configs
- YAML workflow configs
- Pydantic config validation
- Sequential workflow runner
- Shared workflow state
- Mock LLM client
- Trace logging
- Saved run artifacts
- Basic tests

## MVP Excludes

The MVP does not include:

- Real LLM API integrations
- LangGraph
- Dashboard
- SDK
- Docker
- Code patching
- Filesystem modification
- Git integration
- Test execution
- User accounts
- Agent marketplace
- Autonomous app generation
- Custom agent creation UI

These exclusions are intentional. The first milestone should build a reliable and understandable engine before adding more powerful surfaces.

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
allowed_tools: []
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

Example state after the full MVP workflow:

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

### Trace

Trace records each step of a workflow run.

Each trace event should include:

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

## Design Principles

1. Build the engine before the dashboard.
2. Prefer explicit workflows over hidden autonomous behavior.
3. Make every agent output inspectable.
4. Use structured state instead of unstructured message passing.
5. Require human approval before future file modifications.
6. Use mock LLMs before real LLM APIs.
7. Keep the MVP small enough to fully understand.
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
