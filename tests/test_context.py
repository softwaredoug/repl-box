"""Tests for Context — the synced list for LLM conversation state."""
import json

import pytest

import repl_box
from repl_box.context import Context

from openai.types.responses import (
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
    ResponseReasoningItem,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def repl():
    with repl_box.start(socket_path="/tmp/repl-box-context-test.sock") as r:
        yield r


@pytest.fixture
def reasoning_item():
    return ResponseReasoningItem(
        id="rs_abc123",
        summary=[],
        type="reasoning",
    )


@pytest.fixture
def tool_call():
    return ResponseFunctionToolCall(
        arguments='{"keywords": "electric vehicle battery"}',
        call_id="call_abc123",
        name="patent_search",
        type="function_call",
        id="fc_abc123",
        status="completed",
    )


@pytest.fixture
def output_message():
    return ResponseOutputMessage(
        id="msg_abc123",
        content=[ResponseOutputText(text="Here are some experts.", type="output_text", annotations=[])],
        role="assistant",
        status="completed",
        type="message",
    )


# ---------------------------------------------------------------------------
# Basic list semantics
# ---------------------------------------------------------------------------

def test_basic_list_operations(repl):
    ctx = repl.context("history")

    ctx.append("user: hello")
    ctx.append("assistant: hi")
    assert len(ctx) == 2
    assert repl.send("len(history)")["stdout"].find("2") != -1

    ctx.extend(["user: bye", "assistant: goodbye"])
    assert ctx[-1] == "assistant: goodbye"

    ctx[0] = "user: hey"
    assert ctx[0] == "user: hey"

    ctx.pop()
    assert len(ctx) == 3
    assert ctx == ["user: hey", "assistant: hi", "user: bye"]
    assert "assistant: hi" in ctx


def test_json_serializable(repl):
    ctx = repl.context("history")
    ctx.append({"role": "user", "content": "hello"})
    ctx.append({"role": "assistant", "content": "hi"})

    serialized = json.dumps(ctx)
    assert json.loads(serialized) == list(ctx)


def test_is_list_subclass(repl):
    ctx = repl.context("history")
    assert isinstance(ctx, list)


# ---------------------------------------------------------------------------
# Pydantic coercion
# ---------------------------------------------------------------------------

def test_coerces_reasoning_item(repl, reasoning_item):
    ctx = repl.context("inputs")
    ctx.append(reasoning_item)

    assert isinstance(ctx[0], dict)
    assert ctx[0]["id"] == "rs_abc123"
    assert ctx[0]["type"] == "reasoning"
    assert json.dumps(ctx) is not None


def test_coerces_tool_call(repl, tool_call):
    ctx = repl.context("inputs")
    ctx.append(tool_call)

    assert isinstance(ctx[0], dict)
    assert ctx[0]["name"] == "patent_search"
    assert ctx[0]["call_id"] == "call_abc123"
    assert ctx[0]["arguments"] == '{"keywords": "electric vehicle battery"}'
    assert json.dumps(ctx) is not None


def test_coerces_output_message(repl, output_message):
    ctx = repl.context("inputs")
    ctx.append(output_message)

    assert isinstance(ctx[0], dict)
    assert ctx[0]["role"] == "assistant"
    assert ctx[0]["type"] == "message"
    assert json.dumps(ctx) is not None


def test_extend_coerces(repl, reasoning_item, tool_call):
    ctx = repl.context("inputs")
    ctx.extend([reasoning_item, tool_call])

    assert all(isinstance(item, dict) for item in ctx)
    assert ctx[0]["type"] == "reasoning"
    assert ctx[1]["type"] == "function_call"


def test_iadd_coerces(repl, reasoning_item, tool_call, output_message):
    """inputs += resp.output is the primary real-world usage pattern."""
    ctx = repl.context("inputs")
    ctx.append({"role": "user", "content": "find battery experts"})

    # simulate resp.output — a mix of reasoning, tool calls, and messages
    ctx += [reasoning_item, tool_call, tool_call, output_message]

    assert len(ctx) == 5
    assert all(isinstance(item, dict) for item in ctx)
    assert json.dumps(ctx) is not None


def test_setitem_coerces(repl, tool_call):
    ctx = repl.context("inputs")
    ctx.append({"role": "user", "content": "hello"})
    ctx[0] = tool_call

    assert isinstance(ctx[0], dict)
    assert ctx[0]["name"] == "patent_search"


# ---------------------------------------------------------------------------
# Round-trip to repl server
# ---------------------------------------------------------------------------

def test_server_sees_coerced_dicts(repl, tool_call):
    ctx = repl.context("inputs")
    ctx.append({"role": "user", "content": "find experts"})
    ctx.append(tool_call)

    result = repl.send("inputs[1]['name']")
    assert "patent_search" in result["stdout"]
    assert result["error"] is None


def test_mixed_context_round_trip(repl, reasoning_item, tool_call, output_message):
    """Full conversation context syncs correctly to the repl server."""
    ctx = repl.context("inputs")
    ctx.append({"role": "user", "content": "find battery experts"})
    ctx += [reasoning_item, tool_call, output_message]

    result = repl.send("len(inputs)")
    assert "4" in result["stdout"]

    result = repl.send("inputs[0]['role']")
    assert "user" in result["stdout"]

    result = repl.send("inputs[2]['name']")
    assert "patent_search" in result["stdout"]

    result = repl.send("inputs[3]['role']")
    assert "assistant" in result["stdout"]
