from __future__ import annotations

from pathlib import Path
import shlex


def load_env_file(root: Path, env_file: Path | None = None) -> tuple[Path | None, dict[str, str]]:
    path = env_file or _default_env_file(root)
    if path is None or not path.exists():
        return None, {}

    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key_value = _parse_env_line(line)
        if key_value is None:
            continue
        key, value = key_value
        values[key] = value
    return path, values


def _default_env_file(root: Path) -> Path | None:
    return root / ".env"


def _parse_env_line(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if stripped.startswith("export "):
        stripped = stripped[7:].strip()
    if "=" not in stripped:
        return None
    key, value = stripped.split("=", 1)
    key = key.strip()
    if not key:
        return None
    value = value.strip()
    if value:
        try:
            value = shlex.split(value, comments=False, posix=True)[0]
        except ValueError:
            value = value.strip("\"'")
    return key, value
