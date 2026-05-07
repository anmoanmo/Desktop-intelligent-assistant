from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4
import json
import shutil
import tomllib

from .memory import MemoryStore, Persona, PersonaStore
from .settings import AppSettings, apply_runtime_settings, save_runtime_settings


@dataclass(slots=True)
class ProfileRecord:
    id: str
    name: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(slots=True)
class ProfilePaths:
    directory: Path
    settings: Path
    persona: Path
    memory: Path
    conversations: Path


class ConversationStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, role: str, content: str, source: str = "chat") -> None:
        cleaned = content.strip()
        if not cleaned:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "role": role,
            "content": cleaned,
            "source": source,
            "created_at": _now(),
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False))
            handle.write("\n")

    def append_pair(self, user_text: str, assistant_text: str) -> None:
        self.append("user", user_text, source="chat")
        self.append("assistant", assistant_text, source="chat")

    def recent_messages(self, limit: int = 12) -> list[dict[str, str]]:
        messages = [
            {"role": item["role"], "content": item["content"]}
            for item in self._read_all()
            if item.get("role") in {"user", "assistant"} and item.get("content")
        ]
        return messages[-limit:]

    def count(self) -> int:
        return len(self._read_all())

    def _read_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    rows.append(item)
        return rows


class ProfileStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.base_dir = root / "data" / "assistants"
        self.index_path = self.base_dir / "index.toml"

    def ensure(self, settings: AppSettings) -> ProfileRecord:
        if not self.index_path.exists():
            self._create_initial_default(settings)
        data = self._read_index()
        profiles = self._profiles_from_data(data)
        if not profiles:
            self._create_initial_default(settings)
            data = self._read_index()
            profiles = self._profiles_from_data(data)
        active_id = str(data.get("active_id") or profiles[0].id)
        active = next((profile for profile in profiles if profile.id == active_id), profiles[0])
        if active.id != active_id:
            self._write_index(active.id, profiles)
        self.ensure_profile_files(active, settings)
        return active

    def list(self) -> list[ProfileRecord]:
        self.ensure_index_exists()
        return self._profiles_from_data(self._read_index())

    def active(self) -> ProfileRecord:
        self.ensure_index_exists()
        data = self._read_index()
        profiles = self._profiles_from_data(data)
        active_id = str(data.get("active_id") or profiles[0].id)
        return next((profile for profile in profiles if profile.id == active_id), profiles[0])

    def active_id(self) -> str:
        return self.active().id

    def paths(self, profile_id: str) -> ProfilePaths:
        directory = self.base_dir / _safe_id(profile_id)
        return ProfilePaths(
            directory=directory,
            settings=directory / "settings.toml",
            persona=directory / "persona.toml",
            memory=directory / "memory.json",
            conversations=directory / "conversations.jsonl",
        )

    def apply_active_to_settings(self, settings: AppSettings) -> ProfileRecord:
        profile = self.ensure(settings)
        paths = self.paths(profile.id)
        if paths.settings.exists():
            apply_runtime_settings(settings, _read_toml(paths.settings))
        settings.persona.path = str(paths.persona)
        settings.memory.path = str(paths.memory)
        return profile

    def save_active_settings(self, settings: AppSettings) -> Path:
        paths = self.paths(self.active_id())
        return save_runtime_settings(settings, config_path=paths.settings, update_config_path=False)

    def ensure_profile_files(self, profile: ProfileRecord, settings: AppSettings) -> None:
        paths = self.paths(profile.id)
        paths.directory.mkdir(parents=True, exist_ok=True)
        if not paths.settings.exists():
            save_runtime_settings(settings, config_path=paths.settings, update_config_path=False)
        if not paths.persona.exists():
            PersonaStore(paths.persona).save(
                Persona(
                    name=profile.name,
                    role="用户的智能桌面助理",
                    personality="冷静、直接、可靠，优先给出可执行建议。",
                    speaking_style="默认中文，简洁自然；不夸张，不刷存在感。",
                )
            )
        if not paths.memory.exists():
            MemoryStore(paths.memory).ensure_exists()
        if not paths.conversations.exists():
            paths.conversations.touch()

    def create(self, name: str, settings: AppSettings, persona: Persona | None = None) -> ProfileRecord:
        cleaned = _clean_name(name)
        profiles = self.list()
        profile_id = _unique_profile_id(cleaned, {profile.id for profile in profiles})
        now = _now()
        profile = ProfileRecord(id=profile_id, name=cleaned, created_at=now, updated_at=now)
        profiles.append(profile)
        self._write_index(self.active_id(), profiles)

        paths = self.paths(profile.id)
        paths.directory.mkdir(parents=True, exist_ok=True)
        save_runtime_settings(settings, config_path=paths.settings, update_config_path=False)
        base_persona = persona or Persona()
        PersonaStore(paths.persona).save(
            Persona(
                name=cleaned,
                role=base_persona.role,
                personality=base_persona.personality,
                speaking_style=base_persona.speaking_style,
                instructions=list(base_persona.instructions),
            )
        )
        MemoryStore(paths.memory).ensure_exists()
        paths.conversations.touch()
        return profile

    def switch(self, profile_id: str) -> ProfileRecord:
        profiles = self.list()
        profile = self._find(profiles, profile_id)
        self._write_index(profile.id, profiles)
        return profile

    def rename(self, profile_id: str, name: str) -> ProfileRecord:
        profiles = self.list()
        profile = self._find(profiles, profile_id)
        profile.name = _clean_name(name)
        profile.updated_at = _now()
        self._write_index(self.active_id(), profiles)
        return profile

    def delete(self, profile_id: str) -> ProfileRecord:
        profiles = self.list()
        if len(profiles) <= 1:
            raise ValueError("至少需要保留一个小人存档。")
        profile = self._find(profiles, profile_id)
        next_profiles = [item for item in profiles if item.id != profile.id]
        active_id = self.active_id()
        if active_id == profile.id:
            active_id = next_profiles[0].id
        self._write_index(active_id, next_profiles)
        shutil.rmtree(self.paths(profile.id).directory, ignore_errors=True)
        return self.active()

    def ensure_index_exists(self) -> None:
        if self.index_path.exists():
            return
        now = _now()
        self._write_index("default", [ProfileRecord(id="default", name="桌面助理", created_at=now, updated_at=now)])

    def _create_initial_default(self, settings: AppSettings) -> None:
        now = _now()
        profile = ProfileRecord(id="default", name="桌面助理", created_at=now, updated_at=now)
        paths = self.paths(profile.id)
        paths.directory.mkdir(parents=True, exist_ok=True)
        save_runtime_settings(settings, config_path=paths.settings, update_config_path=False)

        legacy_persona = _rooted_path(settings.root, settings.persona.path)
        if legacy_persona.exists() and legacy_persona != paths.persona:
            shutil.copy2(legacy_persona, paths.persona)
        else:
            PersonaStore(paths.persona).load()

        legacy_memory = _rooted_path(settings.root, settings.memory.path)
        if legacy_memory.exists() and legacy_memory != paths.memory:
            shutil.copy2(legacy_memory, paths.memory)
        else:
            MemoryStore(paths.memory).ensure_exists()

        paths.conversations.touch(exist_ok=True)
        self._write_index(profile.id, [profile])

    def _read_index(self) -> dict[str, Any]:
        if not self.index_path.exists():
            return {}
        return _read_toml(self.index_path)

    def _profiles_from_data(self, data: dict[str, Any]) -> list[ProfileRecord]:
        rows = data.get("profiles", [])
        if not isinstance(rows, list):
            return []
        profiles: list[ProfileRecord] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            profile_id = _safe_id(str(row.get("id") or ""))
            if not profile_id:
                continue
            now = _now()
            profiles.append(
                ProfileRecord(
                    id=profile_id,
                    name=str(row.get("name") or profile_id),
                    created_at=str(row.get("created_at") or now),
                    updated_at=str(row.get("updated_at") or now),
                )
            )
        return profiles

    def _write_index(self, active_id: str, profiles: list[ProfileRecord]) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [f'active_id = "{_toml_escape(active_id)}"', ""]
        for profile in profiles:
            lines.append("[[profiles]]")
            lines.append(f'id = "{_toml_escape(profile.id)}"')
            lines.append(f'name = "{_toml_escape(profile.name)}"')
            lines.append(f'created_at = "{_toml_escape(profile.created_at)}"')
            lines.append(f'updated_at = "{_toml_escape(profile.updated_at)}"')
            lines.append("")
        self.index_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    def _find(self, profiles: list[ProfileRecord], profile_id: str) -> ProfileRecord:
        cleaned = _safe_id(profile_id)
        for profile in profiles:
            if profile.id == cleaned:
                return profile
        raise ValueError(f"未知小人存档：{profile_id}")


def _read_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _rooted_path(root: Path, path_value: str) -> Path:
    path = Path(path_value).expanduser()
    return path if path.is_absolute() else root / path


def _clean_name(value: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        raise ValueError("小人存档名称不能为空。")
    if len(cleaned) > 80:
        raise ValueError("小人存档名称不能超过 80 字。")
    return cleaned


def _safe_id(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in value.strip())[:80].strip("-_")


def _unique_profile_id(name: str, used: set[str]) -> str:
    base = _safe_id(name.lower()) or "assistant"
    if base not in used:
        return base
    return f"{base}-{uuid4().hex[:8]}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
