from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


@dataclass(slots=True)
class ConfirmationRequest:
    id: str
    action: str
    arguments: dict[str, Any]
    reason: str
    created_at: str
    status: str = "pending"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ConfirmationQueue:
    def __init__(self) -> None:
        self._items: dict[str, ConfirmationRequest] = {}

    def add(self, action: str, arguments: dict[str, Any], reason: str) -> ConfirmationRequest:
        request = ConfirmationRequest(
            id=uuid4().hex[:12],
            action=action,
            arguments=arguments,
            reason=reason,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._items[request.id] = request
        return request

    def list(self) -> list[ConfirmationRequest]:
        return [item for item in self._items.values() if item.status == "pending"]

    def resolve(self, request_id: str, approved: bool) -> ConfirmationRequest:
        request = self._items[request_id]
        request.status = "approved" if approved else "rejected"
        return request
