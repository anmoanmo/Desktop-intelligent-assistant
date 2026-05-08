from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

_SENSITIVE_KEY_MARKERS = ("api_key", "apikey", "password", "token", "secret", "私钥", "密码", "验证码")
_PRIVATE_TEXT_KEYS = {
    "content",
    "prompt_text",
    "ocr_text",
    "focused_element_text",
    "focused_window_title",
    "title",
    "path",
    "opened",
    "revealed",
    "url",
    "query",
    "user_text",
    "assistant_text",
    "arguments",
    "error",
}


class AuditLog:
    def __init__(self, path: Path) -> None:
        self.path = path

    def record(self, event: str, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "payload": _redact_for_audit(payload),
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _redact_for_audit(value: Any, key: str = "") -> Any:
    if _is_sensitive_key(key):
        return "[redacted:sensitive]"
    if isinstance(value, dict):
        return {str(item_key): _redact_for_audit(item, str(item_key)) for item_key, item in value.items()}
    if isinstance(value, list):
        return [_redact_for_audit(item, key) for item in value]
    if isinstance(value, str) and _is_private_text_key(key):
        return _redacted_string(value)
    return value


def _is_sensitive_key(key: str) -> bool:
    lowered = key.casefold()
    return any(marker in lowered for marker in _SENSITIVE_KEY_MARKERS)


def _is_private_text_key(key: str) -> bool:
    return key.casefold() in _PRIVATE_TEXT_KEYS


def _redacted_string(value: str) -> str:
    return f"[redacted:str len={len(value)}]"
