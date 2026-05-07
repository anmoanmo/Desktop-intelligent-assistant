from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json


class AuditLog:
    def __init__(self, path: Path) -> None:
        self.path = path

    def record(self, event: str, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "payload": payload,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
