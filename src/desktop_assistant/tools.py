from __future__ import annotations

from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, urlparse, urlsplit, urlunsplit
import json
import os
import re
import sqlite3
import subprocess
import sys
import webbrowser

from .audit import AuditLog
from .confirmations import ConfirmationQueue
from .desktop_context import DesktopContextCollector
from .memory import MemoryStore


TOOL_SPECS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_desktop_context",
            "description": "读取当前前台应用、窗口标题、焦点控件文本和可见窗口列表。默认不发送截图。",
            "parameters": {
                "type": "object",
                "properties": {
                    "include_ocr": {
                        "type": "boolean",
                        "description": "是否在本机截屏并 OCR。仅返回文本，不返回图片。",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_path",
            "description": "用系统默认应用打开本地文件或目录。",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "本地文件或目录路径。"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reveal_path",
            "description": "在系统文件管理器中定位本地文件或目录。",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "本地文件或目录路径。"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_url",
            "description": "用默认浏览器打开明确的 http 或 https URL。网页搜索请使用 web_search，不要自行拼接百度、Google、Bing 等搜索 URL。",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "要打开的 URL。"}},
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "用 Microsoft Edge 配置的默认搜索引擎搜索关键词。不要指定百度、Google、Bing 等固定搜索引擎。",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "要搜索的关键词。"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "launch_app",
            "description": "启动本机应用，例如 Safari、Finder、Notepad、Visual Studio Code。",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string", "description": "应用名称。"}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "保存用户明确表达的长期偏好、稳定事实、项目背景或用户要求记住的内容。不要保存密钥、密码等敏感信息。",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "要持久化保存的记忆内容。"},
                    "category": {
                        "type": "string",
                        "enum": ["profile", "preference", "project", "workflow", "note"],
                        "description": "记忆类别。",
                    },
                    "importance": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1,
                        "description": "重要程度，0 到 1。",
                    },
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_memories",
            "description": "查询已保存的长期记忆。",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "可选记忆类别过滤。"},
                    "query": {"type": "string", "description": "可选关键词过滤。"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_memory",
            "description": "更新一条已保存的长期记忆。",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "记忆 ID。"},
                    "content": {"type": "string", "description": "新的记忆内容。"},
                    "category": {"type": "string", "description": "新的记忆类别。"},
                    "importance": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_memory",
            "description": "删除一条已保存的长期记忆。",
            "parameters": {
                "type": "object",
                "properties": {"id": {"type": "string", "description": "记忆 ID。"}},
                "required": ["id"],
            },
        },
    },
]


class ToolExecutor:
    def __init__(
        self,
        collector: DesktopContextCollector,
        audit_log: AuditLog,
        max_context_chars: int = 5000,
        allow_ocr: bool = False,
        memory_store: MemoryStore | None = None,
        confirmation_queue: ConfirmationQueue | None = None,
        permission_policy: Any | None = None,
    ) -> None:
        self.collector = collector
        self.audit_log = audit_log
        self.max_context_chars = max_context_chars
        self.allow_ocr = allow_ocr
        self.memory_store = memory_store
        self.confirmation_queue = confirmation_queue or ConfirmationQueue()
        self.permission_policy = permission_policy
        self._handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            "get_desktop_context": self._get_desktop_context,
            "open_path": self._open_path,
            "reveal_path": self._reveal_path,
            "open_url": self._open_url,
            "web_search": self._web_search,
            "launch_app": self._launch_app,
            "save_memory": self._save_memory,
            "list_memories": self._list_memories,
            "update_memory": self._update_memory,
            "delete_memory": self._delete_memory,
        }

    def execute(self, name: str, arguments: str | dict[str, Any] | None) -> dict[str, Any]:
        return self._execute(name, arguments, bypass_permission=False)

    def execute_confirmed(self, name: str, arguments: str | dict[str, Any] | None) -> dict[str, Any]:
        return self._execute(name, arguments, bypass_permission=True)

    def _execute(
        self,
        name: str,
        arguments: str | dict[str, Any] | None,
        *,
        bypass_permission: bool,
    ) -> dict[str, Any]:
        try:
            parsed = self._parse_arguments(arguments)
        except Exception as exc:
            result = _tool_result(False, error=f"工具参数解析失败：{exc}", action=name)
            self.audit_log.record("tool_call", {"name": name, "arguments": arguments, "result": result})
            return result
        handler = self._handlers.get(name)
        if handler is None:
            result = _tool_result(False, error=f"未知工具：{name}", action=name)
        else:
            try:
                preflight_result = self._preflight_arguments(name, parsed)
                permission_result = (
                    self._check_permission(name, parsed)
                    if not bypass_permission and preflight_result is None
                    else None
                )
                if preflight_result is not None:
                    result = preflight_result
                else:
                    result = permission_result or handler(parsed)
            except Exception as exc:
                result = _tool_result(False, error=str(exc), action=name)
        self.audit_log.record("tool_call", {"name": name, "arguments": parsed, "result": result})
        return result

    def _parse_arguments(self, arguments: str | dict[str, Any] | None) -> dict[str, Any]:
        if arguments is None:
            return {}
        if isinstance(arguments, dict):
            return arguments
        if not arguments.strip():
            return {}
        return json.loads(arguments)

    def _get_desktop_context(self, arguments: dict[str, Any]) -> dict[str, Any]:
        include_ocr = bool(arguments.get("include_ocr")) and self.allow_ocr
        context = self.collector.snapshot(include_ocr=include_ocr, max_chars=self.max_context_chars)
        return _tool_result(
            True,
            action="get_desktop_context",
            result={"context": context.to_dict(), "prompt_text": context.to_prompt_text(self.max_context_chars)},
        )

    def _open_path(self, arguments: dict[str, Any]) -> dict[str, Any]:
        path = _resolve_path(arguments.get("path"))
        if not path.exists():
            return _tool_result(False, action="open_path", error=f"路径不存在：{path}")
        _open_local_path(path)
        return _tool_result(True, action="open_path", result={"opened": str(path)})

    def _reveal_path(self, arguments: dict[str, Any]) -> dict[str, Any]:
        path = _resolve_path(arguments.get("path"))
        if not path.exists():
            return _tool_result(False, action="reveal_path", error=f"路径不存在：{path}")
        _reveal_local_path(path)
        return _tool_result(True, action="reveal_path", result={"revealed": str(path)})

    def _open_url(self, arguments: dict[str, Any]) -> dict[str, Any]:
        url = str(arguments.get("url") or "").strip()
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return _tool_result(False, action="open_url", error="只允许打开 http/https URL。")
        normalized = _normalize_url(url)
        if not webbrowser.open(normalized):
            raise RuntimeError("默认浏览器打开 URL 失败。")
        return _tool_result(True, action="open_url", result={"opened": normalized})

    def _web_search(self, arguments: dict[str, Any]) -> dict[str, Any]:
        query = str(arguments.get("query") or "").strip()
        if not query:
            return _tool_result(False, action="web_search", error="搜索关键词不能为空。")
        try:
            method = _open_web_search(query)
        except Exception as exc:
            return _tool_result(False, action="web_search", error=_web_search_error_message(exc))
        return _tool_result(True, action="web_search", result={"query": query, "method": method})

    def _launch_app(self, arguments: dict[str, Any]) -> dict[str, Any]:
        name = str(arguments.get("name") or "").strip()
        if not name:
            return _tool_result(False, action="launch_app", error="应用名称不能为空。")
        _launch_application(name)
        return _tool_result(True, action="launch_app", result={"launched": name})

    def _save_memory(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if self.memory_store is None:
            return _tool_result(False, action="save_memory", error="长期记忆未启用。")
        entry = self.memory_store.add(
            content=str(arguments.get("content") or ""),
            category=str(arguments.get("category") or "note"),
            importance=float(arguments.get("importance", 0.5)),
            source="assistant_tool",
        )
        return _tool_result(True, action="save_memory", result={"memory": entry.to_dict()})

    def _list_memories(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if self.memory_store is None:
            return _tool_result(False, action="list_memories", error="长期记忆未启用。")
        entries = self.memory_store.list(
            category=arguments.get("category"),
            query=arguments.get("query"),
            limit=int(arguments.get("limit", 20)),
        )
        return _tool_result(True, action="list_memories", result={"memories": [entry.to_dict() for entry in entries]})

    def _update_memory(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if self.memory_store is None:
            return _tool_result(False, action="update_memory", error="长期记忆未启用。")
        entry = self.memory_store.update(
            memory_id=str(arguments.get("id") or ""),
            content=arguments.get("content"),
            category=arguments.get("category"),
            importance=arguments.get("importance"),
        )
        return _tool_result(True, action="update_memory", result={"memory": entry.to_dict()})

    def _delete_memory(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if self.memory_store is None:
            return _tool_result(False, action="delete_memory", error="长期记忆未启用。")
        memory_id = str(arguments.get("id") or "")
        deleted = self.memory_store.delete(memory_id)
        return _tool_result(True, action="delete_memory", result={"deleted": deleted, "id": memory_id})

    def request_confirmation(self, action: str, arguments: dict[str, Any], reason: str) -> dict[str, Any]:
        request = self.confirmation_queue.add(action=action, arguments=arguments, reason=reason)
        result = _tool_result(
            False,
            action=action,
            error="该操作需要用户确认。",
            requires_confirmation=True,
            result={"confirmation": request.to_dict()},
        )
        self.audit_log.record("confirmation_requested", result)
        return result

    def _check_permission(self, name: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
        actions = ["desktop_context"] if name == "get_desktop_context" else [name]
        if name == "get_desktop_context" and bool(arguments.get("include_ocr")):
            actions.append("ocr")
        for action in actions:
            policy = _permission_value(self.permission_policy, action)
            if policy == "deny":
                return _tool_result(False, action=name, error=f"工具权限已禁用：{action}")
            if policy == "ask":
                return self.request_confirmation(name, arguments, f"工具 {name} 需要用户确认。")
        return None

    def _preflight_arguments(self, name: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
        if name not in {"open_path", "reveal_path"}:
            return None
        try:
            _reject_other_user_home(str(arguments.get("path") or ""))
        except ValueError as exc:
            return _tool_result(False, action=name, error=str(exc))
        return None


def _resolve_path(value: Any) -> Path:
    if not value:
        raise ValueError("路径不能为空。")
    raw = str(value).strip()
    _reject_other_user_home(raw)
    path = Path(raw).expanduser().resolve()
    _reject_other_user_home(str(path))
    return path


def _permission_value(policy: Any, action: str) -> str:
    if policy is None:
        return "allow"
    if isinstance(policy, dict):
        value = policy.get(action, "allow")
    else:
        value = getattr(policy, action, "allow")
    normalized = str(value or "allow").strip().lower()
    return normalized if normalized in {"allow", "ask", "deny"} else "allow"


def _normalize_url(value: str) -> str:
    parts = urlsplit(value.strip())
    hostname = parts.hostname.encode("idna").decode("ascii") if parts.hostname else ""
    netloc = hostname
    if parts.port is not None:
        netloc = f"{netloc}:{parts.port}"
    if parts.username:
        userinfo = quote(parts.username, safe="%")
        if parts.password:
            userinfo = f"{userinfo}:{quote(parts.password, safe='%')}"
        netloc = f"{userinfo}@{netloc}"

    path = quote(parts.path, safe="/:@%")
    query = quote(parts.query, safe="=&;%:+,/?@")
    fragment = quote(parts.fragment, safe="/?=&;%:+,@")
    return urlunsplit((parts.scheme, netloc or parts.netloc, path, query, fragment))


def _open_web_search(query: str) -> str:
    search_url = _edge_default_search_url(query)
    method = "microsoft_edge_default_search_provider"
    if search_url is None:
        search_url = _baidu_search_url(query)
        method = "microsoft_edge_baidu_search_url"

    if sys.platform == "darwin":
        _open_edge_macos(search_url)
        return method
    if sys.platform.startswith("win"):
        _open_edge_windows(search_url)
        return method

    if webbrowser.open(search_url):
        return "default_browser_search_url"
    raise RuntimeError("当前平台无法打开搜索 URL。")


def _baidu_search_url(query: str) -> str:
    return _normalize_url(f"https://www.baidu.com/s?wd={quote(query, safe='')}")


def _open_edge_macos(target: str) -> None:
    try:
        subprocess.run(["open", "-b", "com.microsoft.edgemac", target], check=True)
    except FileNotFoundError as exc:
        raise RuntimeError("未找到 macOS open 命令，无法启动 Microsoft Edge。") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError("无法启动 Microsoft Edge，请确认已安装 Edge。") from exc


def _open_edge_windows(target: str) -> None:
    try:
        subprocess.run(["cmd", "/c", "start", "", "msedge", target], check=True)
    except FileNotFoundError as exc:
        raise RuntimeError("未找到 Windows cmd，无法启动 Microsoft Edge。") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError("无法启动 Microsoft Edge，请确认已安装 Edge。") from exc


def _edge_default_search_url(query: str) -> str | None:
    user_data_dir = _edge_user_data_dir()
    if user_data_dir is None:
        return None
    for profile_dir in _edge_profile_dirs(user_data_dir):
        preferences_path = profile_dir / "Preferences"
        try:
            preferences = json.loads(preferences_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        template = _edge_search_template(preferences)
        if template:
            return _render_search_template(template, query)
        template = _edge_search_template_from_web_data(profile_dir)
        if template:
            return _render_search_template(template, query)
    return None


def _edge_user_data_dir() -> Path | None:
    override = os.environ.get("DESKTOP_ASSISTANT_EDGE_USER_DATA_DIR")
    if override:
        return Path(override).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Microsoft Edge"
    if sys.platform.startswith("win"):
        local_app_data = os.environ.get("LOCALAPPDATA")
        if not local_app_data:
            return None
        return Path(local_app_data) / "Microsoft" / "Edge" / "User Data"
    return None


def _edge_profile_dirs(user_data_dir: Path) -> list[Path]:
    candidates: list[str] = []
    local_state_path = user_data_dir / "Local State"
    try:
        local_state = json.loads(local_state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        local_state = {}

    profile_state = local_state.get("profile") if isinstance(local_state, dict) else {}
    if isinstance(profile_state, dict):
        for key in ("last_used", "last_active_profiles"):
            value = profile_state.get(key)
            if isinstance(value, str):
                candidates.append(value)
            elif isinstance(value, list):
                candidates.extend(item for item in value if isinstance(item, str))
        info_cache = profile_state.get("info_cache")
        if isinstance(info_cache, dict):
            candidates.extend(key for key in info_cache if isinstance(key, str))

    candidates.extend(["Default", "Profile 1", "Profile 2", "Profile 3"])
    seen: set[str] = set()
    profiles: list[Path] = []
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        profile_dir = user_data_dir / candidate
        if (profile_dir / "Preferences").exists():
            profiles.append(profile_dir)
    return profiles


def _edge_search_template(preferences: dict[str, Any]) -> str | None:
    provider = preferences.get("default_search_provider")
    if not isinstance(provider, dict):
        return None
    if provider.get("enabled") is False:
        return None
    search_url = provider.get("search_url")
    if not isinstance(search_url, str) or "{searchTerms}" not in search_url:
        return None
    parsed = urlparse(search_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return search_url


def _edge_search_template_from_web_data(profile_dir: Path) -> str | None:
    web_data_path = profile_dir / "Web Data"
    if not web_data_path.exists():
        return None
    uri = f"file:{web_data_path}?mode=ro&immutable=1"
    try:
        connection = sqlite3.connect(uri, uri=True)
    except sqlite3.Error:
        return None
    try:
        rows = connection.execute(
            """
            select url, prepopulate_id, safe_for_autoreplace, is_active, starter_pack_id, id
            from keywords
            where url like '%{searchTerms}%'
            """
        ).fetchall()
    except sqlite3.Error:
        return None
    finally:
        connection.close()

    candidates: list[tuple[str, int, int, int, int, int]] = []
    for row in rows:
        url, prepopulate_id, safe_for_autoreplace, is_active, starter_pack_id, row_id = row
        if not isinstance(url, str) or "{searchTerms}" not in url:
            continue
        if url.startswith("edge://"):
            continue
        if int(is_active or 0) == 0:
            continue
        if int(starter_pack_id or 0) != 0:
            continue
        candidates.append(
            (
                url,
                int(prepopulate_id or 0),
                int(safe_for_autoreplace or 0),
                int(is_active or 0),
                int(starter_pack_id or 0),
                int(row_id or 0),
            )
        )
    if not candidates:
        return None

    candidates.sort(key=lambda item: (item[1] != 1, -item[2], item[5]))
    return candidates[0][0]


def _render_search_template(template: str, query: str) -> str:
    rendered = template.replace("{searchTerms}", quote(query, safe=""))
    rendered = rendered.replace("{bing:baseURL}", "https://www.bing.com/")
    rendered = rendered.replace("{bing:cnBaseURL}", "https://cn.bing.com/")
    rendered = rendered.replace("{inputEncoding}", "UTF-8")
    rendered = rendered.replace("{language}", "zh-CN")
    rendered = rendered.replace("{count}", "10")
    rendered = rendered.replace("{startIndex}", "0")
    rendered = rendered.replace("{startPage}", "1")
    rendered = rendered.replace("{google:baseURL}", "https://www.google.com/")
    rendered = re.sub(r"\{[^{}]+\}", "", rendered)
    rendered = re.sub(r"&{2,}", "&", rendered)
    rendered = rendered.replace("?&", "?").rstrip("?&")
    return _normalize_url(rendered)


def _web_search_error_message(exc: Exception) -> str:
    detail = str(exc).strip()
    if isinstance(exc, subprocess.CalledProcessError):
        command = " ".join(str(part) for part in exc.cmd)
        detail = f"命令退出码 {exc.returncode}: {command}".strip()
    if not detail:
        detail = exc.__class__.__name__
    return f"网页搜索失败：{detail}"


def _reject_other_user_home(value: str) -> None:
    user = _explicit_user_home_name(value)
    if not user or user.casefold() in _shared_user_home_names():
        return

    current_home = _current_home_text()
    current_user = _explicit_user_home_name(current_home) or Path(current_home).name
    if user.casefold() == current_user.casefold():
        return

    raise ValueError(
        f"路径指向其他用户目录：{value}；当前用户目录是 {current_home}。"
        "请使用 ~/... 或当前用户目录下的绝对路径，不要猜测其他用户名。"
    )


def _explicit_user_home_name(value: str) -> str | None:
    text = value.strip()
    if not text:
        return None
    if text.startswith("~") and text not in {"~"} and not text.startswith(("~/", "~\\")):
        user = re.split(r"[/\\]", text[1:], maxsplit=1)[0]
        return user or None
    is_absolute = text.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:[/\\]", text) is not None
    if not is_absolute:
        return None

    normalized = text.replace("\\", "/")
    parts = [part for part in normalized.split("/") if part]
    if parts and parts[0].endswith(":"):
        parts = parts[1:]
    if len(parts) >= 2 and parts[0].casefold() in {"users", "home"}:
        return parts[1]
    return None


def _shared_user_home_names() -> set[str]:
    return {"shared", "public", "default", "default user", "all users"}


def _current_home_text() -> str:
    return str(Path.home().expanduser().resolve())


def _open_local_path(path: Path) -> None:
    if sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=True)
        return
    if sys.platform.startswith("win"):
        os.startfile(str(path))  # type: ignore[attr-defined]
        return
    subprocess.run(["xdg-open", str(path)], check=True)


def _reveal_local_path(path: Path) -> None:
    if sys.platform == "darwin":
        subprocess.run(["open", "-R", str(path)], check=True)
        return
    if sys.platform.startswith("win"):
        if path.is_dir():
            subprocess.run(["explorer", str(path)], check=True)
        else:
            subprocess.run(["explorer", f"/select,{path}"], check=True)
        return
    target = path if path.is_dir() else path.parent
    subprocess.run(["xdg-open", str(target)], check=True)


def _launch_application(name: str) -> None:
    if sys.platform == "darwin":
        subprocess.run(["open", "-a", name], check=True)
        return
    if sys.platform.startswith("win"):
        subprocess.run(["cmd", "/c", "start", "", name], check=True)
        return
    subprocess.run([name], check=True)


def _tool_result(
    ok: bool,
    action: str,
    result: dict[str, Any] | None = None,
    error: str | None = None,
    requires_confirmation: bool = False,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "action": action,
        "result": result or {},
        "error": error,
        "requires_confirmation": requires_confirmation,
    }
