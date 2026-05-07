from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from desktop_assistant.llm import LLMClient
from desktop_assistant.settings import LLMSettings


@dataclass
class FakeFunction:
    name: str
    arguments: str


@dataclass
class FakeToolCall:
    id: str
    function: FakeFunction


class FakeMessage:
    def __init__(self, content: str = "", tool_calls: list[FakeToolCall] | None = None) -> None:
        self.content = content
        self.tool_calls = tool_calls or []

    def model_dump(self, exclude_none: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {"role": "assistant"}
        if self.content:
            payload["content"] = self.content
        if self.tool_calls:
            payload["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.function.name, "arguments": call.function.arguments},
                }
                for call in self.tool_calls
            ]
        return payload


class FakeChoice:
    def __init__(self, message: FakeMessage) -> None:
        self.message = message


class FakeResponse:
    def __init__(self, message: FakeMessage) -> None:
        self.choices = [FakeChoice(message)]


class FakeCompletions:
    def __init__(self, responses: list[FakeResponse] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.responses = responses or [
            FakeResponse(FakeMessage(tool_calls=[FakeToolCall("call_1", FakeFunction("list_memories", "{}"))])),
            FakeResponse(FakeMessage(content="已查询记忆。")),
        ]

    def create(self, **kwargs: Any) -> FakeResponse:
        self.calls.append(kwargs)
        return self.responses.pop(0)


class FakeChat:
    def __init__(self, responses: list[FakeResponse] | None = None) -> None:
        self.completions = FakeCompletions(responses)


class FakeClient:
    def __init__(self, responses: list[FakeResponse] | None = None) -> None:
        self.chat = FakeChat(responses)


class FakeLLMClient(LLMClient):
    def __init__(self, fake_client: FakeClient) -> None:
        super().__init__(LLMSettings())
        self.fake_client = fake_client

    @property
    def configured(self) -> bool:
        return True

    def client(self) -> FakeClient:
        return self.fake_client


def test_chat_stream_executes_tool_loop() -> None:
    fake_client = FakeClient()
    llm = FakeLLMClient(fake_client)
    calls: list[str] = []

    output = "".join(
        llm.chat_stream(
            user_text="查一下记忆",
            desktop_prompt="desktop",
            persona_prompt="persona",
            memory_prompt="memory",
            history=[],
            execute_tool=lambda name, args: calls.append(name) or {"ok": True, "action": name, "result": {}},
        )
    )

    assert output == "已查询记忆。"
    assert calls == ["list_memories"]
    assert len(fake_client.chat.completions.calls) == 2


def test_chat_stream_hides_web_tools_for_normal_question() -> None:
    fake_client = FakeClient([FakeResponse(FakeMessage(content="哈尔滨今天可能较冷，需要实时天气我可以再查。"))])
    llm = FakeLLMClient(fake_client)

    output = "".join(
        llm.chat_stream(
            user_text="哈尔滨天气怎么样？",
            desktop_prompt="desktop",
            persona_prompt="persona",
            memory_prompt="memory",
            history=[],
            execute_tool=lambda name, args: {"ok": True, "action": name, "result": {}},
        )
    )

    tool_names = _tool_names(fake_client.chat.completions.calls[0]["tools"])
    assert output == "哈尔滨今天可能较冷，需要实时天气我可以再查。"
    assert "web_search" not in tool_names
    assert "open_url" not in tool_names


def test_chat_stream_exposes_web_tools_for_explicit_web_search() -> None:
    fake_client = FakeClient([FakeResponse(FakeMessage(content="我来打开网页搜索。"))])
    llm = FakeLLMClient(fake_client)

    "".join(
        llm.chat_stream(
            user_text="打开网页为我搜索初音未来",
            desktop_prompt="desktop",
            persona_prompt="persona",
            memory_prompt="memory",
            history=[],
            execute_tool=lambda name, args: {"ok": True, "action": name, "result": {}},
        )
    )

    tool_names = _tool_names(fake_client.chat.completions.calls[0]["tools"])
    assert "web_search" in tool_names
    assert "open_url" in tool_names


def test_chat_stream_exposes_web_tools_for_plain_search_request() -> None:
    fake_client = FakeClient([FakeResponse(FakeMessage(content="我来搜索。"))])
    llm = FakeLLMClient(fake_client)

    "".join(
        llm.chat_stream(
            user_text="为我搜索哈尔滨天气",
            desktop_prompt="desktop",
            persona_prompt="persona",
            memory_prompt="memory",
            history=[],
            execute_tool=lambda name, args: {"ok": True, "action": name, "result": {}},
        )
    )

    tool_names = _tool_names(fake_client.chat.completions.calls[0]["tools"])
    assert "web_search" in tool_names


def test_chat_stream_keeps_web_tools_hidden_for_local_search() -> None:
    fake_client = FakeClient([FakeResponse(FakeMessage(content="请告诉我要找的文件名。"))])
    llm = FakeLLMClient(fake_client)

    "".join(
        llm.chat_stream(
            user_text="帮我搜索本地文件",
            desktop_prompt="desktop",
            persona_prompt="persona",
            memory_prompt="memory",
            history=[],
            execute_tool=lambda name, args: {"ok": True, "action": name, "result": {}},
        )
    )

    tool_names = _tool_names(fake_client.chat.completions.calls[0]["tools"])
    assert "web_search" not in tool_names
    assert "open_url" not in tool_names


def _tool_names(specs: list[dict[str, Any]]) -> set[str]:
    return {str(spec.get("function", {}).get("name")) for spec in specs}
