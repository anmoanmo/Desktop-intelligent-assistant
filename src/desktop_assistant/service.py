from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path
from typing import Any
import json
import sys
import time

from .desktop_context import DesktopContext
from .llm import WEB_TOOL_NAMES, allows_multiple_web_opens, allows_web_tools
from .memory import Persona, PersonaStore
from .profiles import ConversationStore, ProfileStore
from .runtime import RuntimeFactory
from .settings import AppSettings


class AssistantService:
    def __init__(self, settings: AppSettings, extra_model_dirs: list[str] | None = None) -> None:
        self.settings = settings
        self.extra_model_dirs = extra_model_dirs or []
        self.profile_store = ProfileStore(settings.root)
        self.last_context: DesktopContext | None = None
        self.max_history_messages = 12
        self.last_proactive_at = 0.0
        self.proactive_sent_at: list[float] = []
        self.active_profile = self.profile_store.apply_active_to_settings(self.settings)
        self.runtime = RuntimeFactory(settings, extra_model_dirs=self.extra_model_dirs).build()
        self.conversation_store = ConversationStore(self.profile_store.paths(self.active_profile.id).conversations)
        self.history: list[dict[str, Any]] = self.conversation_store.recent_messages(self.max_history_messages)
        self.active_model_id: str | None = self._initial_model_id()

    def public_state(self) -> dict[str, Any]:
        return {
            "settings": {
                "llm": {
                    "provider_profile": self.settings.llm.provider_profile,
                    "base_url": self.settings.llm.base_url,
                    "model": self.settings.llm.model,
                    "api_key_env": self.settings.llm.api_key_env,
                    "configured": self.runtime.llm.configured,
                },
                "context": {
                    "mode": self.settings.context.mode,
                    "ocr_enabled": self.settings.context.ocr_enabled,
                },
                "privacy": {
                    "send_screenshots": self.settings.privacy.send_screenshots,
                },
                "permissions": asdict(self.settings.permissions),
                "runtime_permissions": self.last_context.permissions if self.last_context else {},
                "persona": {
                    "name": self.runtime.persona.name,
                    "role": self.runtime.persona.role,
                    "personality": self.runtime.persona.personality,
                    "speaking_style": self.runtime.persona.speaking_style,
                    "path": self.settings.persona.path,
                },
                "memory": {
                    "enabled": self.settings.memory.enabled,
                    "path": self.settings.memory.path,
                    "count": self.runtime.memory_store.count() if self.runtime.memory_store else 0,
                    "auto_extract_enabled": self.settings.memory.auto_extract_enabled,
                    "auto_extract_max_entries": self.settings.memory.auto_extract_max_entries,
                },
                "profile": {
                    "active_id": self.active_profile.id,
                    "name": self.active_profile.name,
                    "profiles": [profile.to_dict() for profile in self.profile_store.list()],
                    "path": str(self.profile_store.paths(self.active_profile.id).directory),
                    "settings_file": str(self.profile_store.paths(self.active_profile.id).settings),
                    "conversation_count": self.conversation_store.count(),
                },
                "autonomy": {
                    "enabled": self.settings.autonomy.enabled,
                    "interval_seconds": self.settings.autonomy.interval_seconds,
                    "cooldown_seconds": self.settings.autonomy.cooldown_seconds,
                    "window_seconds": self.settings.autonomy.window_seconds,
                    "max_messages_per_window": self.settings.autonomy.max_messages_per_window,
                    "min_interval_seconds": self.settings.autonomy.min_interval_seconds,
                    "max_interval_seconds": self.settings.autonomy.max_interval_seconds,
                },
                "models": {
                    "source_dirs": self.runtime.model_registry.source_dirs,
                    "sources_file": self.settings.models.sources_file,
                    "env_var": self.settings.models.env_var,
                    "default_id": self.settings.models.default_id,
                },
                "config": {
                    "env_file": str(self.settings.env_file) if self.settings.env_file else None,
                    "settings_file": str(self.settings.config_path) if self.settings.config_path else None,
                    "profile_settings_file": str(self.profile_store.paths(self.active_profile.id).settings),
                    "config_mode": "root-config-first",
                },
                "ui": {
                    "avatar_x": self.settings.ui.avatar_x,
                    "avatar_y": self.settings.ui.avatar_y,
                    "avatar_scale": self.settings.ui.avatar_scale,
                    "avatar_always_on_top": self.settings.ui.avatar_always_on_top,
                    "main_x": self.settings.ui.main_x,
                    "main_y": self.settings.ui.main_y,
                    "main_width": self.settings.ui.main_width,
                    "main_height": self.settings.ui.main_height,
                },
            },
            "models": self.runtime.model_registry.to_frontend(),
            "active_model_id": self.active_model_id,
            "confirmations": [item.to_dict() for item in self.runtime.confirmation_queue.list()],
        }

    def set_active_model(self, model_id: str) -> dict[str, Any]:
        if not self.runtime.model_registry.exists(model_id):
            return {"ok": False, "error": f"未知模型：{model_id}"}
        self.active_model_id = model_id
        self.settings.models.default_id = model_id
        settings_path = self.profile_store.save_active_settings(self.settings)
        return {"ok": True, "active_model_id": self.active_model_id, "settings_file": str(settings_path)}

    def save_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            if not isinstance(payload, dict):
                raise ValueError("设置 payload 必须是对象。")
            self._apply_model_settings(payload.get("models", {}))
            self._apply_ui_settings(payload.get("ui", {}))
            self._apply_autonomy_settings(payload.get("autonomy", {}))
            self._apply_memory_settings(payload.get("memory", {}))
            self._apply_permission_settings(payload.get("permissions", {}))
            self._apply_persona_settings(payload.get("persona", {}))
            settings_path = self.profile_store.save_active_settings(self.settings)
        except (TypeError, ValueError) as exc:
            return {"ok": False, "error": str(exc), "state": self.public_state()}

        state = self.public_state()
        return {"ok": True, "settings_file": str(settings_path), "state": state}

    def create_profile(self, name: str) -> dict[str, Any]:
        try:
            profile = self.profile_store.create(name, self.settings, persona=self.runtime.persona)
            self.profile_store.switch(profile.id)
            self._reload_active_profile()
        except (TypeError, ValueError) as exc:
            return {"ok": False, "error": str(exc), "state": self.public_state()}
        return {"ok": True, "profile": self.active_profile.to_dict(), "state": self.public_state()}

    def switch_profile(self, profile_id: str) -> dict[str, Any]:
        try:
            self.profile_store.switch(profile_id)
            self._reload_active_profile()
        except (TypeError, ValueError) as exc:
            return {"ok": False, "error": str(exc), "state": self.public_state()}
        return {"ok": True, "profile": self.active_profile.to_dict(), "state": self.public_state()}

    def rename_profile(self, profile_id: str, name: str) -> dict[str, Any]:
        try:
            profile = self.profile_store.rename(profile_id, name)
            if profile.id == self.active_profile.id:
                self.active_profile = profile
        except (TypeError, ValueError) as exc:
            return {"ok": False, "error": str(exc), "state": self.public_state()}
        return {"ok": True, "profile": profile.to_dict(), "state": self.public_state()}

    def delete_profile(self, profile_id: str) -> dict[str, Any]:
        try:
            previous_active_id = self.active_profile.id
            active = self.profile_store.delete(profile_id)
            if active.id != previous_active_id or profile_id == previous_active_id:
                self._reload_active_profile()
        except (TypeError, ValueError) as exc:
            return {"ok": False, "error": str(exc), "state": self.public_state()}
        return {"ok": True, "profile": self.active_profile.to_dict(), "state": self.public_state()}

    def refresh_context(self, include_ocr: bool | None = None) -> DesktopContext:
        context_policy = _permission_value(self.settings.permissions.desktop_context)
        if context_policy != "allow":
            self.last_context = _restricted_context(
                f"桌面上下文权限为 {context_policy}，已跳过自动采集。"
            )
            return self.last_context
        do_ocr = self.settings.context.ocr_enabled if include_ocr is None else include_ocr
        ocr_policy = _permission_value(self.settings.permissions.ocr)
        ocr_blocked = do_ocr and ocr_policy != "allow"
        if ocr_blocked:
            do_ocr = False
        self.last_context = self.runtime.collector.snapshot(
            include_ocr=do_ocr,
            max_chars=self.settings.context.max_context_chars,
        )
        if ocr_blocked:
            self.last_context.permissions["ocr"] = f"blocked_by_policy:{ocr_policy}"
            self.last_context.permission_notes.append(f"OCR 权限为 {ocr_policy}，已跳过 OCR。")
        return self.last_context

    def resolve_confirmation(self, request_id: str, approved: bool) -> dict[str, Any]:
        try:
            request = self.runtime.confirmation_queue.resolve(request_id, approved)
        except KeyError:
            return {"ok": False, "error": f"未知确认请求：{request_id}"}
        tool_result = None
        if approved:
            tool_result = self.runtime.tools.execute_confirmed(request.action, request.arguments)
        return {"ok": True, "confirmation": request.to_dict(), "tool_result": tool_result}

    def chat_stream(self, user_text: str) -> Iterable[str]:
        context = self.refresh_context(include_ocr=False)
        desktop_prompt = context.to_prompt_text(self.settings.context.max_context_chars)
        memory_prompt = (
            self.runtime.memory_store.to_prompt_text(
                limit=self.settings.memory.max_prompt_entries,
                max_chars=self.settings.memory.max_prompt_chars,
            )
            if self.runtime.memory_store
            else "长期记忆：未启用。"
        )
        full: list[str] = []
        scoped_tools = _ScopedToolExecutor(user_text, self.runtime.tools.execute)
        for delta in self.runtime.llm.chat_stream(
            user_text=user_text,
            desktop_prompt=desktop_prompt,
            persona_prompt=self.runtime.persona.to_prompt_text(),
            memory_prompt=memory_prompt,
            history=self.history,
            execute_tool=scoped_tools.execute,
        ):
            full.append(delta)
            yield delta
        assistant_text = "".join(full).strip()
        if assistant_text:
            self._append_history(user_text, assistant_text)
            self._auto_extract_memories(user_text, assistant_text, memory_prompt)

    def proactive_message(self) -> str:
        if not self.settings.autonomy.enabled:
            return ""
        now = time.monotonic()
        window_seconds = max(60, int(self.settings.autonomy.window_seconds))
        self.proactive_sent_at = [sent_at for sent_at in self.proactive_sent_at if now - sent_at < window_seconds]
        if len(self.proactive_sent_at) >= max(1, int(self.settings.autonomy.max_messages_per_window)):
            return ""
        minimum_gap = max(30, int(self.settings.autonomy.min_interval_seconds))
        if self.last_proactive_at and now - self.last_proactive_at < minimum_gap:
            return ""

        context = self.refresh_context(include_ocr=False)
        desktop_prompt = context.to_prompt_text(self.settings.context.max_context_chars)
        memory_prompt = (
            self.runtime.memory_store.to_prompt_text(
                limit=self.settings.memory.max_prompt_entries,
                max_chars=self.settings.memory.max_prompt_chars,
            )
            if self.runtime.memory_store
            else "长期记忆：未启用。"
        )
        text = self.runtime.llm.proactive_message(
            desktop_prompt=desktop_prompt,
            persona_prompt=self.runtime.persona.to_prompt_text(),
            memory_prompt=memory_prompt,
            history=self.history,
        ).strip()
        if text:
            self.last_proactive_at = now
            self.proactive_sent_at.append(now)
            self.conversation_store.append("assistant", text, source="proactive")
            self.history.append({"role": "assistant", "content": text})
            if len(self.history) > self.max_history_messages:
                self.history = self.history[-self.max_history_messages :]
        return text

    def _append_history(self, user_text: str, assistant_text: str) -> None:
        self.history.extend(
            [
                {"role": "user", "content": user_text},
                {"role": "assistant", "content": assistant_text},
            ]
        )
        if len(self.history) > self.max_history_messages:
            self.history = self.history[-self.max_history_messages :]
        self.conversation_store.append_pair(user_text, assistant_text)

    def _auto_extract_memories(self, user_text: str, assistant_text: str, memory_prompt: str) -> list[dict[str, Any]]:
        if not self.settings.memory.enabled or not self.settings.memory.auto_extract_enabled:
            return []
        if self.runtime.memory_store is None:
            return []
        if not getattr(self.runtime.llm, "configured", False):
            return []
        extractor = getattr(self.runtime.llm, "extract_memories", None)
        if extractor is None:
            return []

        try:
            candidates = extractor(
                user_text=user_text,
                assistant_text=assistant_text,
                persona_prompt=self.runtime.persona.to_prompt_text(),
                memory_prompt=memory_prompt,
                max_entries=max(0, int(self.settings.memory.auto_extract_max_entries)),
            )
        except Exception:
            return []

        saved: list[dict[str, Any]] = []
        for item in candidates:
            if not isinstance(item, dict):
                continue
            try:
                entry = self.runtime.memory_store.add(
                    content=str(item.get("content") or ""),
                    category=str(item.get("category") or "note"),
                    importance=float(item.get("importance", 0.5)),
                    source="auto_extract",
                )
            except (TypeError, ValueError):
                continue
            saved.append(entry.to_dict())
        return saved

    def _reload_active_profile(self) -> None:
        self.active_profile = self.profile_store.apply_active_to_settings(self.settings)
        self.runtime = RuntimeFactory(self.settings, extra_model_dirs=self.extra_model_dirs).build()
        self.conversation_store = ConversationStore(self.profile_store.paths(self.active_profile.id).conversations)
        self.history = self.conversation_store.recent_messages(self.max_history_messages)
        self.active_model_id = self._initial_model_id()
        self.last_context = None
        self.last_proactive_at = 0.0
        self.proactive_sent_at = []

    def _initial_model_id(self) -> str | None:
        configured = self.settings.models.default_id.strip()
        if configured and self.runtime.model_registry.exists(configured):
            return configured
        return self.runtime.model_registry.default_id()

    def _apply_model_settings(self, values: Any) -> None:
        if not isinstance(values, dict):
            return
        if "default_id" not in values:
            return
        model_id = str(values.get("default_id") or "").strip()
        if model_id and not self.runtime.model_registry.exists(model_id):
            raise ValueError(f"未知模型：{model_id}")
        self.settings.models.default_id = model_id
        if model_id:
            self.active_model_id = model_id

    def _apply_ui_settings(self, values: Any) -> None:
        if not isinstance(values, dict):
            return
        if "avatar_x" in values:
            self.settings.ui.avatar_x = _clamp_int(values["avatar_x"], -100000, 100000, "avatar_x")
        if "avatar_y" in values:
            self.settings.ui.avatar_y = _clamp_int(values["avatar_y"], -100000, 100000, "avatar_y")
        if "avatar_scale" in values:
            self.settings.ui.avatar_scale = _clamp_float(values["avatar_scale"], 0.35, 2.5, "avatar_scale")
        if "avatar_always_on_top" in values:
            self.settings.ui.avatar_always_on_top = _coerce_bool(values["avatar_always_on_top"])
        if "main_x" in values:
            self.settings.ui.main_x = _clamp_int(values["main_x"], -100000, 100000, "main_x")
        if "main_y" in values:
            self.settings.ui.main_y = _clamp_int(values["main_y"], -100000, 100000, "main_y")
        if "main_width" in values:
            self.settings.ui.main_width = _clamp_int(values["main_width"], 320, 1200, "main_width")
        if "main_height" in values:
            self.settings.ui.main_height = _clamp_int(values["main_height"], 360, 1000, "main_height")

    def _apply_autonomy_settings(self, values: Any) -> None:
        if not isinstance(values, dict):
            return
        if "enabled" in values:
            self.settings.autonomy.enabled = _coerce_bool(values["enabled"])
        if "interval_seconds" in values:
            self.settings.autonomy.interval_seconds = _clamp_int(values["interval_seconds"], 30, 86400, "interval_seconds")
        if "cooldown_seconds" in values:
            self.settings.autonomy.cooldown_seconds = _clamp_int(values["cooldown_seconds"], 0, 86400, "cooldown_seconds")
        if "window_seconds" in values:
            self.settings.autonomy.window_seconds = _clamp_int(values["window_seconds"], 60, 86400, "window_seconds")
        if "max_messages_per_window" in values:
            self.settings.autonomy.max_messages_per_window = _clamp_int(
                values["max_messages_per_window"],
                1,
                20,
                "max_messages_per_window",
            )
        if "min_interval_seconds" in values:
            self.settings.autonomy.min_interval_seconds = _clamp_int(values["min_interval_seconds"], 30, 86400, "min_interval_seconds")
        if "max_interval_seconds" in values:
            self.settings.autonomy.max_interval_seconds = _clamp_int(values["max_interval_seconds"], 30, 86400, "max_interval_seconds")
        if self.settings.autonomy.max_interval_seconds < self.settings.autonomy.min_interval_seconds:
            self.settings.autonomy.max_interval_seconds = self.settings.autonomy.min_interval_seconds

    def _apply_memory_settings(self, values: Any) -> None:
        if not isinstance(values, dict):
            return
        if "auto_extract_enabled" in values:
            self.settings.memory.auto_extract_enabled = _coerce_bool(values["auto_extract_enabled"])
        if "auto_extract_max_entries" in values:
            self.settings.memory.auto_extract_max_entries = _clamp_int(
                values["auto_extract_max_entries"],
                0,
                10,
                "auto_extract_max_entries",
            )

    def _apply_permission_settings(self, values: Any) -> None:
        if not isinstance(values, dict):
            return
        allowed = set(self.settings.permissions.__dataclass_fields__)  # type: ignore[attr-defined]
        for key, value in values.items():
            if key not in allowed:
                continue
            setattr(self.settings.permissions, key, _permission_policy(value, key))

    def _apply_persona_settings(self, values: Any) -> None:
        if not isinstance(values, dict) or not values:
            return
        current = self.runtime.persona
        persona = Persona(
            name=_limited_text(values.get("name", current.name), 80, "name"),
            role=current.role,
            personality=_limited_text(values.get("personality", current.personality), 1000, "personality"),
            speaking_style=_limited_text(values.get("speaking_style", current.speaking_style), 1000, "speaking_style"),
            instructions=list(current.instructions),
        )
        if not persona.name:
            raise ValueError("人设名称不能为空。")
        if "role" in values:
            persona.role = _limited_text(values.get("role", current.role), 200, "role") or current.role
        PersonaStore(_rooted_path(self.settings.root, self.settings.persona.path)).save(persona)
        self.runtime.persona = persona


def _rooted_path(root: Path, path_value: str) -> Path:
    path = Path(path_value).expanduser()
    return path if path.is_absolute() else root / path


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _clamp_int(value: Any, minimum: int, maximum: int, name: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} 必须是整数。") from exc
    return max(minimum, min(maximum, number))


def _clamp_float(value: Any, minimum: float, maximum: float, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} 必须是数字。") from exc
    return max(minimum, min(maximum, number))


def _limited_text(value: Any, max_length: int, name: str) -> str:
    text = str(value or "").strip()
    if len(text) > max_length:
        raise ValueError(f"{name} 超过 {max_length} 字。")
    return text


def _permission_policy(value: Any, name: str) -> str:
    policy = str(value or "allow").strip().lower()
    if policy not in {"allow", "ask", "deny"}:
        raise ValueError(f"{name} 权限策略必须是 allow、ask 或 deny。")
    return policy


def _permission_value(value: Any) -> str:
    policy = str(value or "allow").strip().lower()
    return policy if policy in {"allow", "ask", "deny"} else "allow"


def _restricted_context(note: str) -> DesktopContext:
    context = DesktopContext(platform=_platform_label())
    context.permissions["accessibility"] = "blocked_by_policy"
    context.permissions["screen_recording"] = "blocked_by_policy"
    context.permissions["ocr"] = "blocked_by_policy"
    context.permission_notes.append(note)
    return context


class _ScopedToolExecutor:
    def __init__(self, user_text: str, execute_tool: Any) -> None:
        self.execute_tool = execute_tool
        self.web_allowed = allows_web_tools(user_text)
        self.web_limit = 3 if allows_multiple_web_opens(user_text) else 1
        self.web_count = 0
        self.seen_web_calls: set[str] = set()

    def execute(self, name: str, arguments: str | dict[str, Any] | None) -> dict[str, Any]:
        if name not in WEB_TOOL_NAMES:
            return self.execute_tool(name, arguments)
        if not self.web_allowed:
            return _skipped_tool_result(
                name,
                "requires_explicit_web_action",
                "网页工具已跳过：用户没有明确要求打开或搜索网页。",
            )

        key = _tool_call_key(name, arguments)
        if key in self.seen_web_calls:
            return _skipped_tool_result(name, "duplicate", "网页工具已跳过：本轮已执行过相同请求。")
        if self.web_count >= self.web_limit:
            return _skipped_tool_result(
                name,
                "limit",
                f"网页工具已跳过：本轮最多允许打开 {self.web_limit} 个网页。",
            )

        self.seen_web_calls.add(key)
        self.web_count += 1
        return self.execute_tool(name, arguments)


def _tool_call_key(name: str, arguments: str | dict[str, Any] | None) -> str:
    parsed: Any = arguments
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments) if arguments.strip() else {}
        except json.JSONDecodeError:
            parsed = arguments
    elif arguments is None:
        parsed = {}
    return json.dumps({"name": name, "arguments": parsed}, ensure_ascii=False, sort_keys=True, default=str)


def _skipped_tool_result(action: str, reason: str, message: str) -> dict[str, Any]:
    return {
        "ok": False,
        "action": action,
        "result": {"skipped": reason},
        "error": message,
        "requires_confirmation": False,
    }


def _platform_label() -> str:
    if sys.platform == "darwin":
        return "macOS"
    if sys.platform.startswith("win"):
        return "Windows"
    if sys.platform.startswith("linux"):
        return "Linux"
    return sys.platform
