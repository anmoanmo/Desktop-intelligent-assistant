import json
import sqlite3
from pathlib import Path

from desktop_assistant.audit import AuditLog
from desktop_assistant.desktop_context import DesktopContext, DesktopContextCollector
from desktop_assistant.memory import MemoryStore
from desktop_assistant import tools as tools_module
from desktop_assistant.tools import ToolExecutor


class StubCollector(DesktopContextCollector):
    def snapshot(self, include_ocr: bool = False, max_chars: int = 5000) -> DesktopContext:
        return DesktopContext(platform="macOS", frontmost_app="Tests", focused_window_title="Window")


def test_get_desktop_context_tool_records_audit(tmp_path: Path) -> None:
    audit = AuditLog(tmp_path / "audit.jsonl")
    executor = ToolExecutor(StubCollector(), audit, allow_ocr=False)

    result = executor.execute("get_desktop_context", {"include_ocr": True})

    assert result["ok"] is True
    assert result["result"]["context"]["frontmost_app"] == "Tests"
    assert result["requires_confirmation"] is False
    rows = [json.loads(line) for line in audit.path.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["event"] == "tool_call"
    audit_payload = rows[0]["payload"]
    assert audit_payload["result"]["result"]["context"]["focused_window_title"].startswith("[redacted:")
    assert "Window" not in json.dumps(audit_payload, ensure_ascii=False)


def test_open_url_rejects_non_http(tmp_path: Path) -> None:
    executor = ToolExecutor(StubCollector(), AuditLog(tmp_path / "audit.jsonl"))

    result = executor.execute("open_url", {"url": "file:///tmp/test"})

    assert result["ok"] is False
    assert result["action"] == "open_url"


def test_open_url_percent_encodes_unicode_query(tmp_path: Path, monkeypatch) -> None:
    opened: list[str] = []
    monkeypatch.setattr(tools_module.webbrowser, "open", lambda url: opened.append(url) or True)
    executor = ToolExecutor(
        StubCollector(),
        AuditLog(tmp_path / "audit.jsonl"),
        permission_policy={"open_url": "allow"},
    )

    result = executor.execute("open_url", {"url": "https://www.baidu.com/s?wd=初音未来"})

    assert result["ok"] is True
    assert opened == ["https://www.baidu.com/s?wd=%E5%88%9D%E9%9F%B3%E6%9C%AA%E6%9D%A5"]
    assert result["result"]["opened"] == opened[0]


def test_open_url_preserves_existing_percent_encoding(tmp_path: Path, monkeypatch) -> None:
    opened: list[str] = []
    monkeypatch.setattr(tools_module.webbrowser, "open", lambda url: opened.append(url) or True)
    executor = ToolExecutor(
        StubCollector(),
        AuditLog(tmp_path / "audit.jsonl"),
        permission_policy={"open_url": "allow"},
    )

    result = executor.execute("open_url", {"url": "https://www.baidu.com/s?wd=%E5%88%9D%E9%9F%B3"})

    assert result["ok"] is True
    assert opened == ["https://www.baidu.com/s?wd=%E5%88%9D%E9%9F%B3"]


def test_web_search_uses_microsoft_edge_default_search_provider(tmp_path: Path, monkeypatch) -> None:
    edge_dir = tmp_path / "edge"
    profile_dir = edge_dir / "Profile 1"
    profile_dir.mkdir(parents=True)
    (edge_dir / "Local State").write_text(
        json.dumps({"profile": {"last_used": "Profile 1"}}),
        encoding="utf-8",
    )
    (profile_dir / "Preferences").write_text(
        json.dumps(
            {
                "default_search_provider": {
                    "enabled": True,
                    "search_url": "https://search.example.test/find?q={searchTerms}&ie={inputEncoding}",
                }
            }
        ),
        encoding="utf-8",
    )
    runs: list[dict[str, object]] = []
    monkeypatch.setenv("DESKTOP_ASSISTANT_EDGE_USER_DATA_DIR", str(edge_dir))
    monkeypatch.setattr(tools_module.sys, "platform", "darwin")

    def fake_run(cmd: list[str], **kwargs):
        runs.append({"cmd": cmd, "input": kwargs.get("input")})

        class Result:
            returncode = 0
            stdout = b""

        return Result()

    monkeypatch.setattr(tools_module.subprocess, "run", fake_run)
    executor = ToolExecutor(
        StubCollector(),
        AuditLog(tmp_path / "audit.jsonl"),
        permission_policy={"web_search": "allow"},
    )

    result = executor.execute("web_search", {"query": "初音未来"})

    assert result["ok"] is True
    assert runs == [
        {
            "cmd": [
                "open",
                "-b",
                "com.microsoft.edgemac",
                "https://search.example.test/find?q=%E5%88%9D%E9%9F%B3%E6%9C%AA%E6%9D%A5&ie=UTF-8",
            ],
            "input": None,
        }
    ]
    assert result["result"]["method"] == "microsoft_edge_default_search_provider"


def test_web_search_uses_edge_web_data_default_provider(tmp_path: Path, monkeypatch) -> None:
    edge_dir = tmp_path / "edge"
    profile_dir = edge_dir / "Default"
    profile_dir.mkdir(parents=True)
    (edge_dir / "Local State").write_text(
        json.dumps({"profile": {"last_active_profiles": ["Default"]}}),
        encoding="utf-8",
    )
    (profile_dir / "Preferences").write_text("{}", encoding="utf-8")
    connection = sqlite3.connect(profile_dir / "Web Data")
    try:
        connection.execute(
            """
            create table keywords (
                id integer primary key,
                url text,
                prepopulate_id integer,
                safe_for_autoreplace integer,
                is_active integer,
                starter_pack_id integer
            )
            """
        )
        connection.execute(
            """
            insert into keywords
            (id, url, prepopulate_id, safe_for_autoreplace, is_active, starter_pack_id)
            values (1, '{bing:cnBaseURL}search?q={searchTerms}&{bing:cvid}', 1, 1, 1, 0)
            """
        )
        connection.commit()
    finally:
        connection.close()
    runs: list[dict[str, object]] = []
    monkeypatch.setenv("DESKTOP_ASSISTANT_EDGE_USER_DATA_DIR", str(edge_dir))
    monkeypatch.setattr(tools_module.sys, "platform", "darwin")

    def fake_run(cmd: list[str], **kwargs):
        runs.append({"cmd": cmd, "input": kwargs.get("input")})

        class Result:
            returncode = 0
            stdout = b""

        return Result()

    monkeypatch.setattr(tools_module.subprocess, "run", fake_run)
    executor = ToolExecutor(
        StubCollector(),
        AuditLog(tmp_path / "audit.jsonl"),
        permission_policy={"web_search": "allow"},
    )

    result = executor.execute("web_search", {"query": "初音未来"})

    assert result["ok"] is True
    assert runs == [
        {
            "cmd": [
                "open",
                "-b",
                "com.microsoft.edgemac",
                "https://cn.bing.com/search?q=%E5%88%9D%E9%9F%B3%E6%9C%AA%E6%9D%A5",
            ],
            "input": None,
        }
    ]
    assert result["result"]["method"] == "microsoft_edge_default_search_provider"


def test_web_search_falls_back_to_encoded_baidu_url_without_automation(tmp_path: Path, monkeypatch) -> None:
    runs: list[dict[str, object]] = []
    monkeypatch.setenv("DESKTOP_ASSISTANT_EDGE_USER_DATA_DIR", str(tmp_path / "missing-edge-profile"))
    monkeypatch.setattr(tools_module.sys, "platform", "darwin")

    def fake_run(cmd: list[str], **kwargs):
        runs.append({"cmd": cmd, "input": kwargs.get("input")})

        class Result:
            returncode = 0
            stdout = b"old clipboard"

        return Result()

    monkeypatch.setattr(tools_module.subprocess, "run", fake_run)
    executor = ToolExecutor(
        StubCollector(),
        AuditLog(tmp_path / "audit.jsonl"),
        permission_policy={"web_search": "allow"},
    )

    result = executor.execute("web_search", {"query": "初音未来"})

    assert result["ok"] is True
    assert runs == [
        {
            "cmd": [
                "open",
                "-b",
                "com.microsoft.edgemac",
                "https://www.baidu.com/s?wd=%E5%88%9D%E9%9F%B3%E6%9C%AA%E6%9D%A5",
            ],
            "input": None,
        }
    ]
    assert result["result"]["method"] == "microsoft_edge_baidu_search_url"


def test_web_search_falls_back_to_default_browser_on_other_platform(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DESKTOP_ASSISTANT_EDGE_USER_DATA_DIR", str(tmp_path / "missing-edge-profile"))
    monkeypatch.setattr(tools_module.sys, "platform", "linux")
    opened: list[str] = []
    monkeypatch.setattr(tools_module.webbrowser, "open", lambda url: opened.append(url) or True)
    executor = ToolExecutor(
        StubCollector(),
        AuditLog(tmp_path / "audit.jsonl"),
        permission_policy={"web_search": "allow"},
    )

    result = executor.execute("web_search", {"query": "初音未来"})

    assert result["ok"] is True
    assert opened == ["https://www.baidu.com/s?wd=%E5%88%9D%E9%9F%B3%E6%9C%AA%E6%9D%A5"]
    assert result["result"]["method"] == "default_browser_search_url"


def test_save_memory_tool(tmp_path: Path) -> None:
    memory = MemoryStore(tmp_path / "memory.json")
    executor = ToolExecutor(StubCollector(), AuditLog(tmp_path / "audit.jsonl"), memory_store=memory)

    result = executor.execute("save_memory", {"content": "用户偏好手动触发桌面助理。", "category": "preference"})

    assert result["ok"] is True
    assert memory.count() == 1


def test_audit_log_redacts_memory_content(tmp_path: Path) -> None:
    memory = MemoryStore(tmp_path / "memory.json")
    audit = AuditLog(tmp_path / "audit.jsonl")
    executor = ToolExecutor(StubCollector(), audit, memory_store=memory)

    executor.execute("save_memory", {"content": "用户偏好手动触发桌面助理。", "category": "preference"})

    raw = audit.path.read_text(encoding="utf-8")
    row = json.loads(raw.splitlines()[0])
    assert "用户偏好手动触发桌面助理" not in raw
    assert row["payload"]["arguments"]["content"].startswith("[redacted:")
    assert row["payload"]["result"]["result"]["memory"]["content"].startswith("[redacted:")


def test_update_and_delete_memory_tools(tmp_path: Path) -> None:
    memory = MemoryStore(tmp_path / "memory.json")
    entry = memory.add("旧内容", category="note")
    executor = ToolExecutor(StubCollector(), AuditLog(tmp_path / "audit.jsonl"), memory_store=memory)

    updated = executor.execute("update_memory", {"id": entry.id, "content": "新内容", "category": "workflow"})
    deleted = executor.execute("delete_memory", {"id": entry.id})

    assert updated["ok"] is True
    assert updated["result"]["memory"]["content"] == "新内容"
    assert deleted["result"]["deleted"] is True
    assert memory.count() == 0


def test_confirmation_request_is_structured(tmp_path: Path) -> None:
    executor = ToolExecutor(StubCollector(), AuditLog(tmp_path / "audit.jsonl"))

    result = executor.request_confirmation("dangerous_action", {"path": "/tmp/a"}, "需要用户确认。")

    assert result["ok"] is False
    assert result["requires_confirmation"] is True
    assert result["result"]["confirmation"]["status"] == "pending"


def test_bad_tool_json_returns_structured_error(tmp_path: Path) -> None:
    executor = ToolExecutor(StubCollector(), AuditLog(tmp_path / "audit.jsonl"))

    result = executor.execute("open_url", "{bad json")

    assert result["ok"] is False
    assert "参数解析失败" in result["error"]


def test_permission_deny_blocks_tool(tmp_path: Path) -> None:
    executor = ToolExecutor(
        StubCollector(),
        AuditLog(tmp_path / "audit.jsonl"),
        permission_policy={"open_url": "deny"},
    )

    result = executor.execute("open_url", {"url": "https://example.com"})

    assert result["ok"] is False
    assert "权限已禁用" in result["error"]


def test_permission_ask_queues_confirmation(tmp_path: Path) -> None:
    executor = ToolExecutor(
        StubCollector(),
        AuditLog(tmp_path / "audit.jsonl"),
        permission_policy={"open_url": "ask"},
    )

    result = executor.execute("open_url", {"url": "https://example.com"})

    assert result["ok"] is False
    assert result["requires_confirmation"] is True
    assert len(executor.confirmation_queue.list()) == 1


def test_confirmed_execution_bypasses_permission(tmp_path: Path, monkeypatch) -> None:
    opened: list[str] = []
    monkeypatch.setattr(tools_module.webbrowser, "open", lambda url: opened.append(url) or True)
    executor = ToolExecutor(
        StubCollector(),
        AuditLog(tmp_path / "audit.jsonl"),
        permission_policy={"open_url": "ask"},
    )

    result = executor.execute_confirmed("open_url", {"url": "https://example.com"})

    assert result["ok"] is True
    assert opened == ["https://example.com"]


def test_windows_open_path_uses_startfile(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "note.txt"
    path.write_text("hello", encoding="utf-8")
    opened: list[str] = []
    monkeypatch.setattr(tools_module.sys, "platform", "win32")
    monkeypatch.setattr(tools_module.os, "startfile", lambda value: opened.append(value), raising=False)
    executor = ToolExecutor(
        StubCollector(),
        AuditLog(tmp_path / "audit.jsonl"),
        permission_policy={"open_path": "allow"},
    )

    result = executor.execute("open_path", {"path": str(path)})

    assert result["ok"] is True
    assert opened == [str(path.resolve())]


def test_other_user_home_path_rejected_before_confirmation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(tools_module, "_current_home_text", lambda: "/Users/momo")
    executor = ToolExecutor(
        StubCollector(),
        AuditLog(tmp_path / "audit.jsonl"),
        permission_policy={"open_path": "ask"},
    )

    result = executor.execute("open_path", {"path": "/Users/wangyuxuan/yolo"})

    assert result["ok"] is False
    assert result["requires_confirmation"] is False
    assert "其他用户目录" in result["error"]
    assert "wangyuxuan" in result["error"]
    assert len(executor.confirmation_queue.list()) == 0


def test_named_tilde_other_user_path_rejected(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(tools_module, "_current_home_text", lambda: "/Users/momo")
    executor = ToolExecutor(
        StubCollector(),
        AuditLog(tmp_path / "audit.jsonl"),
        permission_policy={"open_path": "ask"},
    )

    result = executor.execute("open_path", {"path": "~wangyuxuan/yolo"})

    assert result["ok"] is False
    assert result["requires_confirmation"] is False
    assert "其他用户目录" in result["error"]
    assert len(executor.confirmation_queue.list()) == 0


def test_current_user_tilde_path_still_reaches_permission_check(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(tools_module, "_current_home_text", lambda: "/Users/momo")
    executor = ToolExecutor(
        StubCollector(),
        AuditLog(tmp_path / "audit.jsonl"),
        permission_policy={"open_path": "ask"},
    )

    result = executor.execute("open_path", {"path": "~/yolo"})

    assert result["requires_confirmation"] is True
    assert len(executor.confirmation_queue.list()) == 1


def test_windows_other_user_home_path_rejected(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(tools_module, "_current_home_text", lambda: r"C:\Users\momo")
    executor = ToolExecutor(
        StubCollector(),
        AuditLog(tmp_path / "audit.jsonl"),
        permission_policy={"open_path": "allow"},
    )

    result = executor.execute("open_path", {"path": r"C:\Users\wangyuxuan\yolo"})

    assert result["ok"] is False
    assert "其他用户目录" in result["error"]
