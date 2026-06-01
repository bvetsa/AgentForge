# AgentForge

AgentForge is a local-first composable agent workflow engine for software development.

It applies the Unix philosophy to AI-assisted development by letting users define small specialist agents, compose them into workflows, inspect intermediate outputs, and eventually approve generated code changes safely.

## Project Thesis

Modern AI coding tools are powerful, but they are often monolithic and opaque. AgentForge treats AI-assisted development as a composable workflow problem: instead of relying on one large assistant to do everything, users can assemble smaller specialist agents for planning, frontend, backend, testing, security review, documentation, debugging, and other development tasks.

The long-term goal is to make high-quality AI-assisted software development more modular, inspectable, and configurable.

## Current Status

**Phase 0:** Project definition and initial repository structure.

The first implementation phase will build a narrow MVP: a CLI tool that loads YAML-defined agents and workflows, runs agents sequentially using a mock LLM client, passes structured shared state between agents, and writes traceable run artifacts.

## MVP Goal

The MVP is not a full autonomous coding platform. It is the core workflow engine.

The first working version should allow a user to run:

```bash
agentforge run examples/workflows/basic_feature.yaml --input "Add a todo endpoint to a FastAPI app"
```

AgentForge should then run the configured agents in sequence and write the following artifacts:

```text
.agentforge/runs/<run_id>/
  input.txt
  state.json
  trace.json
  final_report.md
```

## MVP Includes

- Python package
- CLI command
- YAML-defined agents
- YAML-defined workflows
- Config validation
- Sequential workflow runner
- Shared workflow state
- Mock LLM client
- Trace logging
- Saved run artifacts
- Basic tests

## MVP Excludes

The MVP intentionally does not include:

- Real LLM API integrations
- LangGraph
- Dashboard
- SDK
- Docker
- File editing
- Patch generation
- Git integration
- Test execution
- User accounts
- Agent marketplace
- Autonomous app generation

These features belong to later phases after the core workflow engine works.

## Core Ideas

### Agents

Agents are small specialist roles. Each agent has a name, description, system prompt, input keys, output key, and allowed tools.

Example agents:

- Planner Agent
- Frontend Agent
- Backend Agent
- Testing Agent
- Reviewer Agent

### Workflows

Workflows compose agents into an ordered process.

The initial MVP uses sequential workflows. Later versions may support graph-based workflows with branching, loops, human approval points, and conditional execution.

### Shared State

Agents communicate through shared state rather than directly messaging each other.

The initial state contains the user's request. Each agent reads required keys from state and writes its own output back to state.

### Trace Logs

Every workflow run should produce a trace that records which agents ran, what inputs they used, what output they produced, and whether each step succeeded.

Trace logs make the system inspectable and debuggable.

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

This workflow does not modify files yet. It only produces planning and review artifacts.
