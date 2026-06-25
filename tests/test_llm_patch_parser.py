import pytest

from agentforge.config.schemas import AgentConfig
from agentforge.patches import LLMPatchParseError, parse_llm_patch_proposals


def test_parse_one_valid_agentforge_patch_block() -> None:
    proposals = parse_llm_patch_proposals(
        _patch_response("src/app.py", "Add health endpoint"),
        agent_config=_agent_config(),
        patch_sequence=3,
    )

    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal.id == "003-backend"
    assert proposal.agent_name == "backend"
    assert proposal.title == "Add health endpoint"
    assert proposal.description == "Adds a GET /health endpoint."
    assert proposal.target_file == "src/app.py"
    assert proposal.patch_file == "patches/003-backend.diff"
    assert proposal.status == "proposed"
    assert "diff --git a/src/app.py b/src/app.py" in proposal.diff


def test_parse_multiple_agentforge_patch_blocks() -> None:
    content = "\n\n".join(
        [
            _patch_response("src/app.py", "Add health endpoint"),
            _patch_response("tests/test_app.py", "Test health endpoint"),
        ]
    )

    proposals = parse_llm_patch_proposals(
        content,
        agent_config=_agent_config(),
        patch_sequence=3,
    )

    assert [proposal.id for proposal in proposals] == ["003-backend", "003-backend-2"]
    assert [proposal.patch_file for proposal in proposals] == [
        "patches/003-backend.diff",
        "patches/003-backend-2.diff",
    ]
    assert [proposal.target_file for proposal in proposals] == [
        "src/app.py",
        "tests/test_app.py",
    ]


def test_parse_rejects_absolute_target_path() -> None:
    with pytest.raises(LLMPatchParseError, match="target_file must be relative"):
        parse_llm_patch_proposals(
            _patch_response("/tmp/app.py", "Bad patch"),
            agent_config=_agent_config(),
            patch_sequence=1,
        )


def test_parse_rejects_target_path_traversal() -> None:
    with pytest.raises(LLMPatchParseError, match="cannot contain '..'"):
        parse_llm_patch_proposals(
            _patch_response("../src/app.py", "Bad patch"),
            agent_config=_agent_config(),
            patch_sequence=1,
        )


def test_parse_returns_empty_list_without_patch_blocks() -> None:
    proposals = parse_llm_patch_proposals(
        "A normal planning response without a patch artifact.",
        agent_config=_agent_config(),
        patch_sequence=1,
    )

    assert proposals == []


def _patch_response(target_file: str, title: str) -> str:
    return f"""
The plan is below.

```agentforge-patch
target_file: {target_file}
title: {title}
description: Adds a GET /health endpoint.
---BEGIN DIFF---
diff --git a/{target_file} b/{target_file}
--- a/{target_file}
+++ b/{target_file}
@@ -1,3 +1,7 @@
+def health():
+    return {{"status": "ok"}}
---END DIFF---
```
""".strip()


def _agent_config() -> AgentConfig:
    return AgentConfig(
        name="backend",
        description="Builds backend changes.",
        system_prompt="Implement backend changes.",
        allowed_tools=[],
        input_keys=["plan"],
        output_key="backend_plan",
        produces_patches=True,
    )
