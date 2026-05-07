from pathlib import Path
import tomllib

from desktop_assistant.models import discover_models
from desktop_assistant.service import AssistantService
from desktop_assistant.settings import load_settings


def _create_live2d_model(root: Path) -> str:
    model_dir = root / "models" / "avatar"
    model_dir.mkdir(parents=True)
    (model_dir / "avatar.model3.json").write_text("{}", encoding="utf-8")
    return discover_models(["./models"], root=root)[0].id


def test_service_uses_configured_default_model(tmp_path: Path) -> None:
    model_id = _create_live2d_model(tmp_path)
    settings = load_settings(root=tmp_path)
    settings.models.search_dirs = ["./models"]
    settings.models.default_id = model_id

    service = AssistantService(settings)

    assert service.active_model_id == model_id


def test_service_save_settings_persists_runtime_and_persona(tmp_path: Path) -> None:
    model_id = _create_live2d_model(tmp_path)
    settings = load_settings(root=tmp_path)
    settings.models.search_dirs = ["./models"]
    service = AssistantService(settings)

    result = service.save_settings(
        {
            "models": {"default_id": model_id},
            "ui": {
                "avatar_x": 24,
                "avatar_y": 48,
                "avatar_scale": 1.4,
                "avatar_always_on_top": False,
                "main_x": 400,
                "main_y": 120,
                "main_width": 900,
                "main_height": 780,
            },
            "autonomy": {
                "enabled": False,
                "interval_seconds": 10,
                "cooldown_seconds": 12,
                "window_seconds": 30,
                "max_messages_per_window": 25,
                "min_interval_seconds": 20,
                "max_interval_seconds": 10,
            },
            "memory": {
                "auto_extract_enabled": False,
                "auto_extract_max_entries": 2,
            },
            "permissions": {
                "open_url": "deny",
                "save_memory": "allow",
            },
            "persona": {"name": "小助理", "personality": "冷静", "speaking_style": "短句"},
        }
    )

    assert result["ok"] is True
    assert service.active_model_id == model_id
    assert service.settings.autonomy.interval_seconds == 30
    profile_dir = tmp_path / "data" / "assistants" / "default"
    raw = tomllib.loads((profile_dir / "settings.toml").read_text(encoding="utf-8"))
    assert raw["models"]["default_id"] == model_id
    assert raw["ui"]["avatar_x"] == 24
    assert raw["ui"]["avatar_y"] == 48
    assert raw["ui"]["avatar_scale"] == 1.4
    assert raw["ui"]["avatar_always_on_top"] is False
    assert raw["ui"]["main_x"] == 400
    assert raw["ui"]["main_y"] == 120
    assert raw["ui"]["main_width"] == 900
    assert raw["ui"]["main_height"] == 780
    assert raw["autonomy"]["enabled"] is False
    assert raw["autonomy"]["interval_seconds"] == 30
    assert raw["autonomy"]["window_seconds"] == 60
    assert raw["autonomy"]["max_messages_per_window"] == 20
    assert raw["autonomy"]["min_interval_seconds"] == 30
    assert raw["autonomy"]["max_interval_seconds"] == 30
    assert raw["memory"]["auto_extract_enabled"] is False
    assert raw["memory"]["auto_extract_max_entries"] == 2
    assert raw["permissions"]["open_url"] == "deny"
    assert raw["permissions"]["save_memory"] == "allow"
    persona = (profile_dir / "persona.toml").read_text(encoding="utf-8")
    assert 'name = "小助理"' in persona
    assert 'speaking_style = "短句"' in persona


def test_service_set_active_model_persists_profile_default(tmp_path: Path) -> None:
    model_id = _create_live2d_model(tmp_path)
    settings = load_settings(root=tmp_path)
    settings.models.search_dirs = ["./models"]
    service = AssistantService(settings)

    result = service.set_active_model(model_id)
    restarted_settings = load_settings(root=tmp_path)
    restarted_settings.models.search_dirs = ["./models"]
    restarted = AssistantService(restarted_settings)

    assert result["ok"] is True
    assert restarted.active_model_id == model_id
    raw = tomllib.loads((tmp_path / "data" / "assistants" / "default" / "settings.toml").read_text(encoding="utf-8"))
    assert raw["models"]["default_id"] == model_id


def test_service_permission_confirmation_executes_confirmed_tool(tmp_path: Path) -> None:
    settings = load_settings(root=tmp_path)
    settings.permissions.save_memory = "ask"
    service = AssistantService(settings)

    requested = service.runtime.tools.execute("save_memory", {"content": "用户喜欢先看测试结果。"})
    confirmation_id = requested["result"]["confirmation"]["id"]
    resolved = service.resolve_confirmation(confirmation_id, True)

    assert requested["requires_confirmation"] is True
    assert resolved["ok"] is True
    assert resolved["tool_result"]["ok"] is True
    assert service.runtime.memory_store.count() == 1  # type: ignore[union-attr]


def test_service_desktop_context_permission_blocks_auto_refresh(tmp_path: Path) -> None:
    settings = load_settings(root=tmp_path)
    settings.permissions.desktop_context = "deny"
    service = AssistantService(settings)

    context = service.refresh_context()

    assert context.permissions["accessibility"] == "blocked_by_policy"
    assert "跳过自动采集" in context.permission_notes[0]


def test_service_profiles_isolate_persona_and_conversations(tmp_path: Path) -> None:
    settings = load_settings(root=tmp_path)
    service = AssistantService(settings)

    created = service.create_profile("测试小人")
    service._append_history("你好", "你好。")  # noqa: SLF001
    service.save_settings({"persona": {"name": "测试小人", "personality": "活泼", "speaking_style": "短句"}})
    switched = service.switch_profile("default")

    assert created["ok"] is True
    assert switched["ok"] is True
    assert service.runtime.persona.name == "桌面助理"
    other_history = (tmp_path / "data" / "assistants" / "测试小人" / "conversations.jsonl").read_text(encoding="utf-8")
    assert "你好" in other_history


class FakeProactiveLLM:
    configured = True

    def proactive_message(self, **kwargs) -> str:
        return "该休息一下了。"


class FakeLearningLLM:
    configured = True

    def chat_stream(self, **kwargs):
        yield "我会记住你的学习节奏。"

    def extract_memories(self, **kwargs):
        return [
            {
                "content": "用户偏好每天晚上复习 Python。",
                "category": "preference",
                "importance": 0.8,
            },
            {
                "content": "token should not be saved",
                "category": "note",
                "importance": 1,
            },
        ]


class FakeToolCallingLLM:
    configured = True

    def __init__(self, tool_calls):
        self.tool_calls = tool_calls
        self.results = []

    def chat_stream(self, **kwargs):
        execute_tool = kwargs["execute_tool"]
        for name, arguments in self.tool_calls:
            self.results.append(execute_tool(name, arguments))
        yield "工具处理完成。"

    def extract_memories(self, **kwargs):
        return []


def test_service_proactive_message_uses_window_quota(tmp_path: Path) -> None:
    settings = load_settings(root=tmp_path)
    settings.autonomy.enabled = True
    settings.autonomy.window_seconds = 600
    settings.autonomy.max_messages_per_window = 1
    settings.autonomy.min_interval_seconds = 30
    service = AssistantService(settings)
    service.runtime.llm = FakeProactiveLLM()  # type: ignore[assignment]

    first = service.proactive_message()
    second = service.proactive_message()

    assert first == "该休息一下了。"
    assert second == ""


def test_service_auto_extracts_memories_after_chat(tmp_path: Path) -> None:
    settings = load_settings(root=tmp_path)
    settings.memory.auto_extract_enabled = True
    service = AssistantService(settings)
    service.runtime.llm = FakeLearningLLM()  # type: ignore[assignment]

    text = "".join(service.chat_stream("我一般晚上复习 Python。"))
    memories = service.runtime.memory_store.list()  # type: ignore[union-attr]

    assert text == "我会记住你的学习节奏。"
    assert len(memories) == 1
    assert memories[0].content == "用户偏好每天晚上复习 Python。"
    assert memories[0].source == "auto_extract"


def test_service_blocks_web_tools_without_explicit_web_action(tmp_path: Path) -> None:
    settings = load_settings(root=tmp_path)
    service = AssistantService(settings)
    fake_llm = FakeToolCallingLLM([("web_search", {"query": "哈尔滨天气"})])
    executed = []
    service.runtime.llm = fake_llm  # type: ignore[assignment]
    service.runtime.tools.execute = lambda name, args: executed.append((name, args)) or {"ok": True, "action": name, "result": {}}  # type: ignore[method-assign]

    text = "".join(service.chat_stream("哈尔滨天气怎么样？"))

    assert text == "工具处理完成。"
    assert executed == []
    assert fake_llm.results[0]["result"]["skipped"] == "requires_explicit_web_action"


def test_service_allows_plain_search_request_web_tool(tmp_path: Path) -> None:
    settings = load_settings(root=tmp_path)
    service = AssistantService(settings)
    fake_llm = FakeToolCallingLLM([("web_search", {"query": "哈尔滨天气"})])
    executed = []
    service.runtime.llm = fake_llm  # type: ignore[assignment]
    service.runtime.tools.execute = lambda name, args: executed.append((name, args)) or {"ok": True, "action": name, "result": {}}  # type: ignore[method-assign]

    "".join(service.chat_stream("为我搜索哈尔滨天气"))

    assert executed == [("web_search", {"query": "哈尔滨天气"})]
    assert fake_llm.results[0]["ok"] is True


def test_service_deduplicates_and_limits_single_web_open(tmp_path: Path) -> None:
    settings = load_settings(root=tmp_path)
    service = AssistantService(settings)
    fake_llm = FakeToolCallingLLM(
        [
            ("web_search", {"query": "初音未来"}),
            ("web_search", {"query": "初音未来"}),
            ("open_url", {"url": "https://example.com"}),
        ]
    )
    executed = []
    service.runtime.llm = fake_llm  # type: ignore[assignment]
    service.runtime.tools.execute = lambda name, args: executed.append((name, args)) or {"ok": True, "action": name, "result": {}}  # type: ignore[method-assign]

    "".join(service.chat_stream("打开网页搜索初音未来"))

    assert executed == [("web_search", {"query": "初音未来"})]
    assert fake_llm.results[1]["result"]["skipped"] == "duplicate"
    assert fake_llm.results[2]["result"]["skipped"] == "limit"


def test_service_allows_at_most_three_explicit_multi_web_opens(tmp_path: Path) -> None:
    settings = load_settings(root=tmp_path)
    service = AssistantService(settings)
    fake_llm = FakeToolCallingLLM(
        [
            ("open_url", {"url": "https://a.example"}),
            ("open_url", {"url": "https://b.example"}),
            ("open_url", {"url": "https://c.example"}),
            ("open_url", {"url": "https://d.example"}),
        ]
    )
    executed = []
    service.runtime.llm = fake_llm  # type: ignore[assignment]
    service.runtime.tools.execute = lambda name, args: executed.append((name, args)) or {"ok": True, "action": name, "result": {}}  # type: ignore[method-assign]

    "".join(
        service.chat_stream(
            "请分别打开以下链接：https://a.example https://b.example https://c.example https://d.example"
        )
    )

    assert [name for name, _args in executed] == ["open_url", "open_url", "open_url"]
    assert fake_llm.results[3]["result"]["skipped"] == "limit"
