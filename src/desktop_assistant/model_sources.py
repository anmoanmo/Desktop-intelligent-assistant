from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import tomllib


@dataclass(frozen=True, slots=True)
class ModelSource:
    name: str
    path: str
    enabled: bool = True


class ModelSourceResolver:
    def __init__(self, root: Path, sources_file: str, env_var: str, env_values: dict[str, str] | None = None) -> None:
        self.root = root
        self.sources_file = sources_file
        self.env_var = env_var
        self.env_values = env_values or {}

    def resolve(self, configured_dirs: list[str], extra_dirs: list[str] | None = None) -> list[str]:
        values: list[str] = []
        values.extend(configured_dirs)
        values.extend(source.path for source in self.from_file())
        values.extend(self.from_env())
        if extra_dirs:
            values.extend(extra_dirs)
        return _dedupe(values)

    def from_file(self) -> list[ModelSource]:
        if not self.sources_file:
            return []
        path = Path(self.sources_file).expanduser()
        if not path.is_absolute():
            path = self.root / path
        if not path.exists():
            return []

        with path.open("rb") as handle:
            data = tomllib.load(handle)

        sources: list[ModelSource] = []
        for index, raw in enumerate(data.get("sources", []), start=1):
            if not isinstance(raw, dict) or raw.get("enabled", True) is False:
                continue
            source_path = raw.get("path")
            if not isinstance(source_path, str) or not source_path.strip():
                continue
            sources.append(
                ModelSource(
                    name=str(raw.get("name") or f"source-{index}"),
                    path=source_path,
                    enabled=True,
                )
            )
        return sources

    def from_env(self) -> list[str]:
        if not self.env_var:
            return []
        raw = os.environ.get(self.env_var, "")
        if self.env_var in self.env_values:
            raw = self.env_values[self.env_var]
        if not raw:
            return []
        return [item for item in raw.split(os.pathsep) if item.strip()]


def _dedupe(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        deduped.append(normalized)
        seen.add(normalized)
    return deduped
