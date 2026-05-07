from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4
import json
import tomllib


DEFAULT_PERSONA_TOML = """name = "桌面助理"
role = "用户的智能桌面助理"
personality = "冷静、直接、可靠，优先给出可执行建议。"
speaking_style = "默认中文，简洁自然；不夸张，不刷存在感。"

instructions = [
  "优先理解用户当前桌面上下文，再回答或执行工具。",
  "遇到高风险操作时先说明风险并要求用户确认。",
  "只有当用户明确表达稳定偏好、长期事实或要求记住时，才保存长期记忆。",
  "不要保存 API key、密码、验证码、身份证号、银行卡号等敏感信息。",
]
"""


@dataclass(slots=True)
class Persona:
    name: str = "桌面助理"
    role: str = "用户的智能桌面助理"
    personality: str = "冷静、直接、可靠，优先给出可执行建议。"
    speaking_style: str = "默认中文，简洁自然；不夸张，不刷存在感。"
    instructions: list[str] = field(
        default_factory=lambda: [
            "优先理解用户当前桌面上下文，再回答或执行工具。",
            "遇到高风险操作时先说明风险并要求用户确认。",
            "只有当用户明确表达稳定偏好、长期事实或要求记住时，才保存长期记忆。",
            "不要保存 API key、密码、验证码、身份证号、银行卡号等敏感信息。",
        ]
    )

    def to_prompt_text(self) -> str:
        lines = [
            "固定人设与行为设定：",
            f"- 名称：{self.name}",
            f"- 角色：{self.role}",
            f"- 性格：{self.personality}",
            f"- 说话风格：{self.speaking_style}",
        ]
        if self.instructions:
            lines.append("- 固定指令：")
            lines.extend(f"  - {item}" for item in self.instructions)
        return "\n".join(lines)


class PersonaStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> Persona:
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(DEFAULT_PERSONA_TOML, encoding="utf-8")
        with self.path.open("rb") as handle:
            data = tomllib.load(handle)
        return Persona(
            name=str(data.get("name") or Persona.name),
            role=str(data.get("role") or "用户的智能桌面助理"),
            personality=str(data.get("personality") or "冷静、直接、可靠，优先给出可执行建议。"),
            speaking_style=str(data.get("speaking_style") or "默认中文，简洁自然；不夸张，不刷存在感。"),
            instructions=[str(item) for item in data.get("instructions", [])],
        )

    def save(self, persona: Persona) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(_persona_to_toml(persona), encoding="utf-8")


@dataclass(slots=True)
class MemoryEntry:
    id: str
    category: str
    content: str
    importance: float = 0.5
    source: str = "assistant"
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MemoryStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def ensure_exists(self) -> None:
        if not self.path.exists():
            self._save({"version": 1, "entries": []})

    def add(self, content: str, category: str = "note", importance: float = 0.5, source: str = "assistant") -> MemoryEntry:
        content = content.strip()
        if not content:
            raise ValueError("记忆内容不能为空。")
        if _looks_sensitive(content):
            raise ValueError("该内容看起来包含敏感信息，已拒绝保存。")

        data = self._load()
        now = datetime.now(timezone.utc).isoformat()
        normalized = content.casefold()
        for raw in data["entries"]:
            if str(raw.get("content", "")).casefold() == normalized:
                raw["category"] = category
                raw["importance"] = float(importance)
                raw["updated_at"] = now
                raw["source"] = source
                self._save(data)
                return MemoryEntry(**raw)

        entry = MemoryEntry(
            id=uuid4().hex[:12],
            category=category,
            content=content,
            importance=max(0.0, min(1.0, float(importance))),
            source=source,
            created_at=now,
            updated_at=now,
        )
        data["entries"].append(entry.to_dict())
        self._save(data)
        return entry

    def list(self, category: str | None = None, query: str | None = None, limit: int = 50) -> list[MemoryEntry]:
        data = self._load()
        entries = [MemoryEntry(**raw) for raw in data["entries"]]
        if category:
            entries = [entry for entry in entries if entry.category == category]
        if query:
            needle = query.casefold()
            entries = [entry for entry in entries if needle in entry.content.casefold()]
        entries.sort(key=lambda item: (item.importance, item.updated_at), reverse=True)
        return entries[:limit]

    def update(
        self,
        memory_id: str,
        content: str | None = None,
        category: str | None = None,
        importance: float | None = None,
    ) -> MemoryEntry:
        data = self._load()
        now = datetime.now(timezone.utc).isoformat()
        for raw in data["entries"]:
            if raw.get("id") != memory_id:
                continue
            if content is not None:
                cleaned = content.strip()
                if not cleaned:
                    raise ValueError("记忆内容不能为空。")
                if _looks_sensitive(cleaned):
                    raise ValueError("该内容看起来包含敏感信息，已拒绝保存。")
                raw["content"] = cleaned
            if category is not None:
                raw["category"] = category
            if importance is not None:
                raw["importance"] = max(0.0, min(1.0, float(importance)))
            raw["updated_at"] = now
            self._save(data)
            return MemoryEntry(**raw)
        raise KeyError(f"未找到记忆：{memory_id}")

    def delete(self, memory_id: str) -> bool:
        data = self._load()
        entries = data["entries"]
        next_entries = [raw for raw in entries if raw.get("id") != memory_id]
        if len(next_entries) == len(entries):
            return False
        data["entries"] = next_entries
        self._save(data)
        return True

    def count(self) -> int:
        return len(self._load()["entries"])

    def to_prompt_text(self, limit: int = 20, max_chars: int = 4000) -> str:
        entries = self.list(limit=limit)
        if not entries:
            return "长期记忆：暂无。"
        lines = ["长期记忆："]
        for entry in entries:
            lines.append(f"- [{entry.category}] {entry.content}")
        return "\n".join(lines)[:max_chars]

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": 1, "entries": []}
        with self.path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        payload.setdefault("version", 1)
        payload.setdefault("entries", [])
        return payload

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")


def _looks_sensitive(content: str) -> bool:
    lowered = content.casefold()
    sensitive_words = ["api_key", "apikey", "password", "密码", "验证码", "token", "secret", "私钥"]
    return any(word in lowered for word in sensitive_words)


def _persona_to_toml(persona: Persona) -> str:
    lines = [
        f'name = "{_toml_escape(persona.name)}"',
        f'role = "{_toml_escape(persona.role)}"',
        f'personality = "{_toml_escape(persona.personality)}"',
        f'speaking_style = "{_toml_escape(persona.speaking_style)}"',
        "",
        "instructions = [",
    ]
    lines.extend(f'  "{_toml_escape(item)}",' for item in persona.instructions)
    lines.append("]")
    lines.append("")
    return "\n".join(lines)


def _toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
