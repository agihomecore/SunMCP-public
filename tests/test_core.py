import json
import sys
from pathlib import Path

import httpx
import pytest

from sunmcp import (
    AnthropicBackend,
    MCPHub,
    OpenAICompatBackend,
    ServerConfig,
    ToolCall,
    Turn,
    run_turn,
)
from sunmcp.config import parse_config

DEMO = str(Path(__file__).parent.parent / "examples" / "demo_server.py")


def demo_servers():
    return {"demo": ServerConfig(command=sys.executable, args=[DEMO])}


class ScriptedBackend:
    """Fake model: first asks for add(2,3), then answers using the tool result."""

    def __init__(self):
        self.calls = 0

    async def complete(self, messages, tools, system=None):
        self.calls += 1
        if self.calls == 1:
            assert any(t["name"] == "demo__add" for t in tools)
            return Turn(tool_calls=[ToolCall("c1", "demo__add", {"a": 2, "b": 3})])
        last = messages[-1]
        assert last["role"] == "tool"
        return Turn(content=f"result is {last['content']}")


async def test_hub_lists_namespaced_tools():
    async with MCPHub(demo_servers()) as hub:
        names = {t["name"] for t in hub.tools}
        assert {"demo__add", "demo__shout"} <= names


async def test_hub_unknown_tool_is_error_not_exception():
    async with MCPHub(demo_servers()) as hub:
        text, err = await hub.call("nope__x", {})
        assert err and "unknown tool" in text


async def test_agent_end_to_end_with_real_mcp_server():
    history = []
    seen = []
    async with MCPHub(demo_servers()) as hub:
        out = await run_turn(
            ScriptedBackend(), hub, history, "2+3?", on_tool=lambda *a: seen.append(a)
        )
    assert out == "result is 5"
    assert seen[0][0] == "demo__add" and seen[0][3] is False
    assert [m["role"] for m in history] == ["user", "assistant", "tool", "assistant"]


async def test_agent_stops_after_max_steps():
    class Loop:
        async def complete(self, messages, tools, system=None):
            return Turn(tool_calls=[ToolCall("x", "demo__shout", {"text": "a"})])

    async with MCPHub(demo_servers()) as hub:
        out = await run_turn(Loop(), hub, [], "go", max_steps=3)
    assert "too many" in out


async def test_openai_backend_request_and_parse():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        captured["auth"] = request.headers.get("authorization")
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "t1",
                                    "type": "function",
                                    "function": {"name": "demo__add", "arguments": '{"a":1,"b":2}'},
                                }
                            ],
                        }
                    }
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    b = OpenAICompatBackend("qwen", "http://x/v1", "KEY", client=client)
    tools = [{"name": "demo__add", "description": "d", "input_schema": {"type": "object"}}]
    turn = await b.complete([{"role": "user", "content": "hi"}], tools, "sys")
    assert captured["url"] == "http://x/v1/chat/completions"
    assert captured["auth"] == "Bearer KEY"
    assert captured["body"]["messages"][0] == {"role": "system", "content": "sys"}
    assert captured["body"]["tools"][0]["function"]["parameters"] == {"type": "object"}
    assert turn.tool_calls[0].arguments == {"a": 1, "b": 2}


def test_openai_converts_tool_history():
    msgs = [
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "1", "name": "n", "arguments": {"a": 1}}]},
        {"role": "tool", "tool_call_id": "1", "name": "n", "content": "r"},
    ]
    out = OpenAICompatBackend.convert_messages(msgs, None)
    assert out[1]["tool_calls"][0]["function"]["arguments"] == '{"a": 1}'
    assert out[2] == {"role": "tool", "tool_call_id": "1", "content": "r"}


def test_anthropic_merges_parallel_tool_results_into_one_user_message():
    msgs = [
        {"role": "user", "content": "q"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": "a", "name": "x", "arguments": {}},
                {"id": "b", "name": "y", "arguments": {}},
            ],
        },
        {"role": "tool", "tool_call_id": "a", "name": "x", "content": "ra"},
        {"role": "tool", "tool_call_id": "b", "name": "y", "content": "rb"},
    ]
    out = AnthropicBackend.convert_messages(msgs)
    assert len(out) == 3
    assert [b["tool_use_id"] for b in out[2]["content"]] == ["a", "b"]


async def test_anthropic_backend_parse():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-api-key"] == "K"
        body = json.loads(request.content)
        assert body["system"] == "s" and body["tools"][0]["input_schema"] == {"type": "object"}
        return httpx.Response(
            200,
            json={
                "content": [
                    {"type": "text", "text": "hello"},
                    {"type": "tool_use", "id": "u1", "name": "demo__add", "input": {"a": 1}},
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    b = AnthropicBackend("m", "K", client=client)
    turn = await b.complete(
        [{"role": "user", "content": "hi"}],
        [{"name": "demo__add", "input_schema": {"type": "object"}}],
        "s",
    )
    assert turn.content == "hello" and turn.tool_calls[0].id == "u1"


async def test_broken_server_gives_readable_error():
    bad = {"broken": ServerConfig(command=sys.executable, args=["-c", "import sys; sys.exit(1)"])}
    with pytest.raises(RuntimeError, match="'broken' failed to start"):
        async with MCPHub(bad):
            pass


def test_config_rejects_double_underscore_server_name():
    with pytest.raises(ValueError):
        parse_config({"servers": {"a__b": {"command": "x"}}})


# ---- vision
from sunmcp import Vision, VisionConfig, attach_vision  # noqa: E402


def _vision_client(captured):
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "an error dialog"}}]})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_vision_look_sends_image_to_vl_model():
    seen: list = []
    v = Vision(VisionConfig(), capture=lambda m: b"\x89PNGfake", client=_vision_client(seen))
    assert await v.look("what is this?") == "an error dialog"
    body = seen[0]
    assert body["model"] == "qwen2.5vl:7b"
    parts = body["messages"][0]["content"]
    assert parts[0]["text"] == "what is this?"
    assert parts[1]["image_url"]["url"].startswith("data:image/png;base64,")


async def test_screenshot_tool_registered_and_callable():
    seen: list = []
    v = Vision(VisionConfig(), capture=lambda m: b"png", client=_vision_client(seen))
    async with MCPHub(demo_servers()) as hub:
        attach_vision(hub, v)
        assert any(t["name"] == "screenshot" for t in hub.tools)
        text, err = await hub.call("screenshot", {"question": "q"})
        assert (text, err) == ("an error dialog", False)


async def test_screenshot_tool_off_when_disabled():
    async with MCPHub(demo_servers()) as hub:
        attach_vision(hub, Vision(VisionConfig(tool=False)))
        assert not any(t["name"] == "screenshot" for t in hub.tools)


async def test_screenshot_tool_reports_capture_error():
    def boom(m):
        raise RuntimeError("no display")

    async with MCPHub(demo_servers()) as hub:
        attach_vision(hub, Vision(VisionConfig(), capture=boom))
        text, err = await hub.call("screenshot", {})
        assert err and "no display" in text


def test_parse_config_vision_defaults_and_override():
    assert parse_config({}).vision.model == "qwen2.5vl:7b"
    c = parse_config({"vision": {"enabled": False, "model": "x"}})
    assert c.vision.enabled is False and c.vision.model == "x"


async def test_backend_http_error_is_readable_with_hint():
    def handler(request):
        return httpx.Response(400, json={"error": {"message": "registry.ollama.ai/library/qwen2.5vl:7b does not support tools"}})

    b = OpenAICompatBackend("qwen2.5vl:7b", "http://x/v1", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    with pytest.raises(RuntimeError) as e:
        await b.complete([{"role": "user", "content": "hi"}], [{"name": "t", "input_schema": {"type": "object"}}])
    msg = str(e.value)
    assert "HTTP 400" in msg and "does not support tools" in msg and "vision.model" in msg
