from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
import os
import tomllib

from .env import load_env_file


@dataclass(slots=True)
class LLMSettings:
    provider_profile: str = "deepseek"
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-v4-pro"
    api_key_env: str = "DEEPSEEK_API_KEY"
    api_key: str = ""
    temperature: float = 0.4
    timeout_seconds: int = 60

    def resolve_api_key(self) -> str | None:
        return self.api_key or os.environ.get(self.api_key_env) or None


@dataclass(slots=True)
class ContextSettings:
    mode: str = "manual"
    ocr_enabled: bool = False
    ocr_languages: list[str] = field(default_factory=lambda: ["zh-Hans", "en-US"])
    max_context_chars: int = 5000
    visible_window_limit: int = 8


@dataclass(slots=True)
class PrivacySettings:
    send_screenshots: bool = False


@dataclass(slots=True)
class PermissionsSettings:
    desktop_context: str = "allow"
    ocr: str = "deny"
    open_path: str = "ask"
    reveal_path: str = "ask"
    open_url: str = "ask"
    web_search: str = "allow"
    launch_app: str = "ask"
    save_memory: str = "ask"
    list_memories: str = "allow"
    update_memory: str = "ask"
    delete_memory: str = "ask"


@dataclass(slots=True)
class ModelSettings:
    search_dirs: list[str] = field(default_factory=list)
    sources_file: str = "config/model_sources.toml"
    env_var: str = "DESKTOP_ASSISTANT_MODEL_DIRS"
    default_id: str = ""


@dataclass(slots=True)
class PersonaSettings:
    path: str = "data/persona.toml"


@dataclass(slots=True)
class MemorySettings:
    enabled: bool = True
    path: str = "data/memory.json"
    max_prompt_entries: int = 20
    max_prompt_chars: int = 4000
    auto_extract_enabled: bool = True
    auto_extract_max_entries: int = 3


@dataclass(slots=True)
class AutonomySettings:
    enabled: bool = True
    interval_seconds: int = 180
    cooldown_seconds: int = 600
    window_seconds: int = 600
    max_messages_per_window: int = 3
    min_interval_seconds: int = 60
    max_interval_seconds: int = 180


@dataclass(slots=True)
class PathSettings:
    audit_log: str = "logs/tool_calls.jsonl"


@dataclass(slots=True)
class UISettings:
    language: str = "zh-CN"
    width: int = 420
    height: int = 680
    avatar_x: int = 0
    avatar_y: int = 0
    avatar_scale: float = 1.0
    avatar_always_on_top: bool = True
    main_x: int = 0
    main_y: int = 0
    main_width: int = 560
    main_height: int = 640


@dataclass(slots=True)
class AppSettings:
    root: Path
    llm: LLMSettings = field(default_factory=LLMSettings)
    context: ContextSettings = field(default_factory=ContextSettings)
    privacy: PrivacySettings = field(default_factory=PrivacySettings)
    permissions: PermissionsSettings = field(default_factory=PermissionsSettings)
    models: ModelSettings = field(default_factory=ModelSettings)
    persona: PersonaSettings = field(default_factory=PersonaSettings)
    memory: MemorySettings = field(default_factory=MemorySettings)
    autonomy: AutonomySettings = field(default_factory=AutonomySettings)
    paths: PathSettings = field(default_factory=PathSettings)
    ui: UISettings = field(default_factory=UISettings)
    config_path: Path | None = None
    env_file: Path | None = None
    root_env: dict[str, str] = field(default_factory=dict)

    def public_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["root"] = str(self.root)
        data["config_path"] = str(self.config_path) if self.config_path else None
        data["env_file"] = str(self.env_file) if self.env_file else None
        data["root_env"] = {key: "***" if "KEY" in key or "TOKEN" in key or "SECRET" in key else value for key, value in self.root_env.items()}
        data["llm"].pop("api_key", None)
        return data


def _section(cls: type[Any], data: dict[str, Any]) -> Any:
    allowed = set(cls.__dataclass_fields__)  # type: ignore[attr-defined]
    return cls(**{key: value for key, value in data.items() if key in allowed})


def _read_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def load_settings(config_path: Path | None = None, root: Path | None = None) -> AppSettings:
    resolved_root = (root or Path.cwd()).resolve()
    env_file, root_env = load_env_file(resolved_root)
    configured_path = config_path
    if config_path is None:
        root_config = root_env.get("DESKTOP_ASSISTANT_CONFIG")
        candidate = Path(root_config).expanduser() if root_config else resolved_root / "config" / "settings.toml"
        if not candidate.is_absolute():
            candidate = resolved_root / candidate
        configured_path = candidate
        config_path = candidate if candidate.exists() else None
    elif not config_path.is_absolute():
        configured_path = resolved_root / config_path
        config_path = configured_path

    raw: dict[str, Any] = {}
    if config_path is not None and config_path.exists():
        raw = _read_toml(config_path)

    settings = AppSettings(root=resolved_root, config_path=configured_path, env_file=env_file, root_env=root_env)
    _apply_config_overrides(settings, root_env, allow_process_env=True)
    _apply_toml_overrides(settings, raw)
    return settings


def save_runtime_settings(
    settings: AppSettings,
    config_path: Path | None = None,
    *,
    update_config_path: bool = True,
) -> Path:
    """Persist editable runtime settings without writing secrets from the environment."""

    path = config_path or settings.config_path or settings.root / "config" / "settings.toml"
    path = path.expanduser()
    if not path.is_absolute():
        path = settings.root / path

    raw: dict[str, Any] = {}
    if path.exists():
        raw = _read_toml(path)
    raw = _without_sensitive_keys(raw)

    models = _section_dict(raw, "models")
    models["default_id"] = settings.models.default_id

    permissions = _section_dict(raw, "permissions")
    for key in settings.permissions.__dataclass_fields__:  # type: ignore[attr-defined]
        permissions[key] = getattr(settings.permissions, key)

    ui = _section_dict(raw, "ui")
    ui["avatar_x"] = settings.ui.avatar_x
    ui["avatar_y"] = settings.ui.avatar_y
    ui["avatar_scale"] = settings.ui.avatar_scale
    ui["avatar_always_on_top"] = settings.ui.avatar_always_on_top
    ui["main_x"] = settings.ui.main_x
    ui["main_y"] = settings.ui.main_y
    ui["main_width"] = settings.ui.main_width
    ui["main_height"] = settings.ui.main_height

    autonomy = _section_dict(raw, "autonomy")
    autonomy["enabled"] = settings.autonomy.enabled
    autonomy["interval_seconds"] = settings.autonomy.interval_seconds
    autonomy["cooldown_seconds"] = settings.autonomy.cooldown_seconds
    autonomy["window_seconds"] = settings.autonomy.window_seconds
    autonomy["max_messages_per_window"] = settings.autonomy.max_messages_per_window
    autonomy["min_interval_seconds"] = settings.autonomy.min_interval_seconds
    autonomy["max_interval_seconds"] = settings.autonomy.max_interval_seconds

    memory = _section_dict(raw, "memory")
    memory["auto_extract_enabled"] = settings.memory.auto_extract_enabled
    memory["auto_extract_max_entries"] = settings.memory.auto_extract_max_entries

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_to_toml(raw), encoding="utf-8")
    if update_config_path:
        settings.config_path = path
    return path


def apply_runtime_settings(settings: AppSettings, raw: dict[str, Any]) -> None:
    """Apply profile-scoped runtime settings without overriding global model sources or secrets."""

    models = raw.get("models", {})
    if isinstance(models, dict) and "default_id" in models:
        settings.models.default_id = str(models.get("default_id") or "")

    sections = {
        "permissions": settings.permissions,
        "ui": settings.ui,
        "autonomy": settings.autonomy,
        "memory": settings.memory,
    }
    for section_name, target in sections.items():
        values = raw.get(section_name, {})
        if not isinstance(values, dict):
            continue
        allowed = set(target.__dataclass_fields__)  # type: ignore[attr-defined]
        for key, value in values.items():
            if key in allowed:
                setattr(target, key, value)


def _apply_config_overrides(settings: AppSettings, values: dict[str, str], allow_process_env: bool) -> None:
    _set_str(settings.llm, "provider_profile", "DESKTOP_ASSISTANT_LLM_PROVIDER", values, allow_process_env)
    _set_str(settings.llm, "base_url", "DESKTOP_ASSISTANT_LLM_BASE_URL", values, allow_process_env)
    _set_str(settings.llm, "model", "DESKTOP_ASSISTANT_LLM_MODEL", values, allow_process_env)
    _set_str(settings.llm, "api_key", "DEEPSEEK_API_KEY", values, allow_process_env)
    _set_str(settings.llm, "api_key_env", "DESKTOP_ASSISTANT_LLM_API_KEY_ENV", values, allow_process_env)
    _set_float(settings.llm, "temperature", "DESKTOP_ASSISTANT_LLM_TEMPERATURE", values, allow_process_env)
    _set_int(settings.llm, "timeout_seconds", "DESKTOP_ASSISTANT_LLM_TIMEOUT_SECONDS", values, allow_process_env)

    _set_str(settings.context, "mode", "DESKTOP_ASSISTANT_CONTEXT_MODE", values, allow_process_env)
    _set_bool(settings.context, "ocr_enabled", "DESKTOP_ASSISTANT_OCR_ENABLED", values, allow_process_env)
    _set_list(settings.context, "ocr_languages", "DESKTOP_ASSISTANT_OCR_LANGUAGES", values, allow_process_env)
    _set_int(settings.context, "max_context_chars", "DESKTOP_ASSISTANT_MAX_CONTEXT_CHARS", values, allow_process_env)
    _set_int(settings.context, "visible_window_limit", "DESKTOP_ASSISTANT_VISIBLE_WINDOW_LIMIT", values, allow_process_env)

    _set_bool(settings.privacy, "send_screenshots", "DESKTOP_ASSISTANT_SEND_SCREENSHOTS", values, allow_process_env)

    _set_str(settings.permissions, "desktop_context", "DESKTOP_ASSISTANT_PERMISSION_DESKTOP_CONTEXT", values, allow_process_env)
    _set_str(settings.permissions, "ocr", "DESKTOP_ASSISTANT_PERMISSION_OCR", values, allow_process_env)
    _set_str(settings.permissions, "open_path", "DESKTOP_ASSISTANT_PERMISSION_OPEN_PATH", values, allow_process_env)
    _set_str(settings.permissions, "reveal_path", "DESKTOP_ASSISTANT_PERMISSION_REVEAL_PATH", values, allow_process_env)
    _set_str(settings.permissions, "open_url", "DESKTOP_ASSISTANT_PERMISSION_OPEN_URL", values, allow_process_env)
    _set_str(settings.permissions, "web_search", "DESKTOP_ASSISTANT_PERMISSION_WEB_SEARCH", values, allow_process_env)
    _set_str(settings.permissions, "launch_app", "DESKTOP_ASSISTANT_PERMISSION_LAUNCH_APP", values, allow_process_env)
    _set_str(settings.permissions, "save_memory", "DESKTOP_ASSISTANT_PERMISSION_SAVE_MEMORY", values, allow_process_env)
    _set_str(settings.permissions, "list_memories", "DESKTOP_ASSISTANT_PERMISSION_LIST_MEMORIES", values, allow_process_env)
    _set_str(settings.permissions, "update_memory", "DESKTOP_ASSISTANT_PERMISSION_UPDATE_MEMORY", values, allow_process_env)
    _set_str(settings.permissions, "delete_memory", "DESKTOP_ASSISTANT_PERMISSION_DELETE_MEMORY", values, allow_process_env)

    _set_list(settings.models, "search_dirs", "DESKTOP_ASSISTANT_MODEL_SEARCH_DIRS", values, allow_process_env)
    _set_str(settings.models, "sources_file", "DESKTOP_ASSISTANT_MODEL_SOURCES_FILE", values, allow_process_env)
    _set_str(settings.models, "env_var", "DESKTOP_ASSISTANT_MODEL_DIRS_ENV_VAR", values, allow_process_env)
    _set_str(settings.models, "default_id", "DESKTOP_ASSISTANT_DEFAULT_MODEL_ID", values, allow_process_env)

    _set_str(settings.persona, "path", "DESKTOP_ASSISTANT_PERSONA_PATH", values, allow_process_env)
    _set_bool(settings.memory, "enabled", "DESKTOP_ASSISTANT_MEMORY_ENABLED", values, allow_process_env)
    _set_str(settings.memory, "path", "DESKTOP_ASSISTANT_MEMORY_PATH", values, allow_process_env)
    _set_int(settings.memory, "max_prompt_entries", "DESKTOP_ASSISTANT_MEMORY_MAX_PROMPT_ENTRIES", values, allow_process_env)
    _set_int(settings.memory, "max_prompt_chars", "DESKTOP_ASSISTANT_MEMORY_MAX_PROMPT_CHARS", values, allow_process_env)
    _set_bool(settings.memory, "auto_extract_enabled", "DESKTOP_ASSISTANT_MEMORY_AUTO_EXTRACT_ENABLED", values, allow_process_env)
    _set_int(settings.memory, "auto_extract_max_entries", "DESKTOP_ASSISTANT_MEMORY_AUTO_EXTRACT_MAX_ENTRIES", values, allow_process_env)

    _set_bool(settings.autonomy, "enabled", "DESKTOP_ASSISTANT_AUTONOMY_ENABLED", values, allow_process_env)
    _set_int(settings.autonomy, "interval_seconds", "DESKTOP_ASSISTANT_AUTONOMY_INTERVAL_SECONDS", values, allow_process_env)
    _set_int(settings.autonomy, "cooldown_seconds", "DESKTOP_ASSISTANT_AUTONOMY_COOLDOWN_SECONDS", values, allow_process_env)
    _set_int(settings.autonomy, "window_seconds", "DESKTOP_ASSISTANT_AUTONOMY_WINDOW_SECONDS", values, allow_process_env)
    _set_int(
        settings.autonomy,
        "max_messages_per_window",
        "DESKTOP_ASSISTANT_AUTONOMY_MAX_MESSAGES_PER_WINDOW",
        values,
        allow_process_env,
    )
    _set_int(
        settings.autonomy,
        "min_interval_seconds",
        "DESKTOP_ASSISTANT_AUTONOMY_MIN_INTERVAL_SECONDS",
        values,
        allow_process_env,
    )
    _set_int(
        settings.autonomy,
        "max_interval_seconds",
        "DESKTOP_ASSISTANT_AUTONOMY_MAX_INTERVAL_SECONDS",
        values,
        allow_process_env,
    )

    _set_str(settings.paths, "audit_log", "DESKTOP_ASSISTANT_AUDIT_LOG", values, allow_process_env)
    _set_str(settings.ui, "language", "DESKTOP_ASSISTANT_UI_LANGUAGE", values, allow_process_env)
    _set_int(settings.ui, "width", "DESKTOP_ASSISTANT_UI_WIDTH", values, allow_process_env)
    _set_int(settings.ui, "height", "DESKTOP_ASSISTANT_UI_HEIGHT", values, allow_process_env)
    _set_int(settings.ui, "avatar_x", "DESKTOP_ASSISTANT_AVATAR_X", values, allow_process_env)
    _set_int(settings.ui, "avatar_y", "DESKTOP_ASSISTANT_AVATAR_Y", values, allow_process_env)
    _set_float(settings.ui, "avatar_scale", "DESKTOP_ASSISTANT_AVATAR_SCALE", values, allow_process_env)
    _set_bool(settings.ui, "avatar_always_on_top", "DESKTOP_ASSISTANT_AVATAR_ALWAYS_ON_TOP", values, allow_process_env)
    _set_int(settings.ui, "main_x", "DESKTOP_ASSISTANT_MAIN_X", values, allow_process_env)
    _set_int(settings.ui, "main_y", "DESKTOP_ASSISTANT_MAIN_Y", values, allow_process_env)
    _set_int(settings.ui, "main_width", "DESKTOP_ASSISTANT_MAIN_WIDTH", values, allow_process_env)
    _set_int(settings.ui, "main_height", "DESKTOP_ASSISTANT_MAIN_HEIGHT", values, allow_process_env)


def _apply_toml_overrides(settings: AppSettings, raw: dict[str, Any]) -> None:
    sections = {
        "llm": settings.llm,
        "context": settings.context,
        "privacy": settings.privacy,
        "permissions": settings.permissions,
        "models": settings.models,
        "persona": settings.persona,
        "memory": settings.memory,
        "autonomy": settings.autonomy,
        "paths": settings.paths,
        "ui": settings.ui,
    }
    for section_name, target in sections.items():
        values = raw.get(section_name, {})
        if not isinstance(values, dict):
            continue
        allowed = set(target.__dataclass_fields__)  # type: ignore[attr-defined]
        for key, value in values.items():
            if key in allowed:
                setattr(target, key, value)


def _section_dict(raw: dict[str, Any], section: str) -> dict[str, Any]:
    values = raw.get(section)
    if not isinstance(values, dict):
        values = {}
        raw[section] = values
    return values


def _without_sensitive_keys(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if _is_sensitive_key(str(key)):
                continue
            cleaned[key] = _without_sensitive_keys(item)
        return cleaned
    if isinstance(value, list):
        return [_without_sensitive_keys(item) for item in value]
    return value


def _is_sensitive_key(key: str) -> bool:
    lowered = key.casefold()
    return any(marker in lowered for marker in ("api_key", "apikey", "password", "token", "secret", "私钥", "密码"))


def _to_toml(data: dict[str, Any]) -> str:
    lines: list[str] = []
    for key, value in data.items():
        if isinstance(value, dict):
            continue
        lines.append(f"{key} = {_toml_value(value)}")
    if lines:
        lines.append("")

    for section, values in data.items():
        if not isinstance(values, dict):
            continue
        lines.append(f"[{section}]")
        for key, value in values.items():
            if isinstance(value, dict):
                continue
            lines.append(f"{key} = {_toml_value(value)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    return f'"{_toml_escape(str(value))}"'


def _toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _value(values: dict[str, str], name: str, allow_process_env: bool) -> str | None:
    if name in values:
        return values[name]
    return os.environ.get(name) if allow_process_env else None


def _set_str(target: Any, attr: str, env_name: str, values: dict[str, str], allow_process_env: bool) -> None:
    value = _value(values, env_name, allow_process_env)
    if value is not None:
        setattr(target, attr, value)


def _set_bool(target: Any, attr: str, env_name: str, values: dict[str, str], allow_process_env: bool) -> None:
    value = _value(values, env_name, allow_process_env)
    if value is not None:
        setattr(target, attr, value.strip().lower() in {"1", "true", "yes", "on"})


def _set_int(target: Any, attr: str, env_name: str, values: dict[str, str], allow_process_env: bool) -> None:
    value = _value(values, env_name, allow_process_env)
    if value is not None and value.strip():
        setattr(target, attr, int(value))


def _set_float(target: Any, attr: str, env_name: str, values: dict[str, str], allow_process_env: bool) -> None:
    value = _value(values, env_name, allow_process_env)
    if value is not None and value.strip():
        setattr(target, attr, float(value))


def _set_list(target: Any, attr: str, env_name: str, values: dict[str, str], allow_process_env: bool) -> None:
    value = _value(values, env_name, allow_process_env)
    if value is not None:
        setattr(target, attr, [item.strip() for item in value.split(os.pathsep) if item.strip()])
