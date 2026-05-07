from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1
from pathlib import Path
from typing import Any
import json


@dataclass(frozen=True, slots=True)
class ModelManifest:
    id: str
    name: str
    kind: str
    entry_path: Path
    asset_root: Path
    default_motion: str | None = None
    metadata: dict[str, Any] | None = None

    def to_frontend(self) -> dict[str, Any]:
        entry = self.entry_path.resolve()
        root = self.asset_root.resolve()
        metadata = self.metadata or {}
        atlas = _metadata_path(metadata.get("atlas"))
        png = _metadata_path(metadata.get("png"))
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "entry_path": str(entry),
            "entry_url": entry.as_uri(),
            "asset_root": str(root),
            "asset_root_url": root.as_uri() + "/",
            "default_motion": self.default_motion,
            "metadata": metadata,
            "assets": {
                "skel": str(entry),
                "skel_url": entry.as_uri(),
                "atlas": str(atlas) if atlas else None,
                "atlas_url": atlas.as_uri() if atlas else None,
                "png": str(png) if png else None,
                "png_url": png.as_uri() if png else None,
            },
        }


def _stable_id(kind: str, path: Path) -> str:
    digest = sha1(str(path.resolve()).encode("utf-8")).hexdigest()[:12]
    return f"{kind}:{digest}"


def _display_name(path: Path) -> str:
    return path.parent.name or path.stem


def _metadata_path(value: Any) -> Path | None:
    if not value:
        return None
    try:
        return Path(str(value)).expanduser().resolve()
    except OSError:
        return None


def _resolve_search_dirs(search_dirs: list[str], root: Path) -> list[Path]:
    resolved: list[Path] = []
    for value in search_dirs:
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = root / path
        if path.exists():
            resolved.append(path.resolve())
    return resolved


def _discover_live2d(directory: Path) -> list[ModelManifest]:
    manifests: list[ModelManifest] = []
    for model_json in sorted(directory.rglob("*.model3.json")):
        metadata = _live2d_metadata(model_json)
        manifests.append(
            ModelManifest(
                id=_stable_id("live2d", model_json),
                name=_display_name(model_json),
                kind="live2d",
                entry_path=model_json,
                asset_root=model_json.parent,
                metadata=metadata,
            )
        )
    return manifests


def _live2d_metadata(model_json: Path) -> dict[str, Any]:
    try:
        payload = json.loads(model_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}

    references = payload.get("FileReferences", {}) if isinstance(payload, dict) else {}
    if not isinstance(references, dict):
        references = {}

    missing_assets: list[str] = []
    for value in _live2d_referenced_files(references):
        if not (model_json.parent / value).exists():
            missing_assets.append(value)

    expressions = []
    referenced_expressions = references.get("Expressions", [])
    if isinstance(referenced_expressions, list):
        for item in referenced_expressions:
            if not isinstance(item, dict):
                continue
            file_name = str(item.get("File") or item.get("file") or "").strip()
            if file_name:
                expressions.append(
                    {
                        "name": str(item.get("Name") or item.get("name") or _expression_name(file_name)),
                        "file": file_name,
                    }
                )

    known_files = {str(item.get("file") or "") for item in expressions}
    for expression_path in sorted(model_json.parent.glob("*.exp3.json")):
        if expression_path.name in known_files:
            continue
        expressions.append({"name": _expression_name(expression_path.name), "file": expression_path.name})

    texture_count = len(references.get("Textures", [])) if isinstance(references.get("Textures"), list) else 0
    return {
        "source": "live2d-directory-scan",
        "live2d": {
            "expressions": expressions,
            "missing_assets": missing_assets,
            "texture_count": texture_count,
            "has_physics": bool(references.get("Physics")),
            "recommended": "PUMK" in model_json.parent.name,
        },
    }


def _live2d_referenced_files(references: dict[str, Any]) -> list[str]:
    files: list[str] = []
    for key in ("Moc", "Physics", "DisplayInfo", "Pose"):
        value = references.get(key)
        if isinstance(value, str) and value.strip():
            files.append(value)

    textures = references.get("Textures", [])
    if isinstance(textures, list):
        files.extend(item for item in textures if isinstance(item, str) and item.strip())

    expressions = references.get("Expressions", [])
    if isinstance(expressions, list):
        for item in expressions:
            if not isinstance(item, dict):
                continue
            value = item.get("File") or item.get("file")
            if isinstance(value, str) and value.strip():
                files.append(value)
    return files


def _expression_name(file_name: str) -> str:
    return file_name.removesuffix(".exp3.json").removesuffix(".json")


def _ark_metadata_manifests(directory: Path) -> list[ModelManifest]:
    metadata_path = directory / "models_data.json"
    if not metadata_path.exists():
        return []

    with metadata_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    storage = payload.get("storageDirectory", {})
    data = payload.get("data", {})
    manifests: list[ModelManifest] = []
    for key, item in sorted(data.items()):
        model_type = item.get("type")
        storage_dir = storage.get(model_type)
        assets = item.get("assetList", {})
        if not storage_dir:
            continue
        asset_root = directory / storage_dir / key
        skel_path = _first_existing_asset(asset_root, assets.get(".skel"))
        atlas_path = _first_existing_asset(asset_root, assets.get(".atlas"))
        png_path = _first_existing_asset(asset_root, assets.get(".png"))
        if skel_path is None or atlas_path is None or png_path is None:
            continue
        display = item.get("name") or item.get("appellation") or key
        skin = item.get("skinGroupName")
        name = f"{display} / {skin}" if skin and skin != "默认服装" else display
        manifests.append(
            ModelManifest(
                id=_stable_id("spine38", skel_path),
                name=name,
                kind="spine38",
                entry_path=skel_path,
                asset_root=asset_root,
                metadata={
                    "atlas": str(atlas_path.resolve()),
                    "png": str(png_path.resolve()),
                    "source": "ark-models",
                    "type": model_type,
                    "style": item.get("style"),
                    "sort_tags": item.get("sortTags", []),
                },
            )
        )
    return manifests


def _first_existing_asset(asset_root: Path, value: Any) -> Path | None:
    if isinstance(value, str):
        path = asset_root / value
        return path if path.exists() else None
    if isinstance(value, list):
        for item in value:
            if not isinstance(item, str):
                continue
            path = asset_root / item
            if path.exists():
                return path
    return None


def _discover_spine(directory: Path) -> list[ModelManifest]:
    from_metadata = _ark_metadata_manifests(directory)
    if from_metadata:
        return from_metadata

    manifests: list[ModelManifest] = []
    for skel_path in sorted(directory.rglob("*.skel")):
        asset_root = skel_path.parent
        atlas_path = next(asset_root.glob("*.atlas"), None)
        png_path = next(asset_root.glob("*.png"), None)
        if atlas_path is None or png_path is None:
            continue
        manifests.append(
            ModelManifest(
                id=_stable_id("spine38", skel_path),
                name=_display_name(skel_path),
                kind="spine38",
                entry_path=skel_path,
                asset_root=asset_root,
                metadata={
                    "atlas": str(atlas_path.resolve()),
                    "png": str(png_path.resolve()),
                    "source": "directory-scan",
                },
            )
        )
    return manifests


def discover_models(search_dirs: list[str], root: Path) -> list[ModelManifest]:
    seen: set[Path] = set()
    manifests: list[ModelManifest] = []
    for directory in _resolve_search_dirs(search_dirs, root=root):
        manifests.extend(_discover_live2d(directory))
        manifests.extend(_discover_spine(directory))

    unique: list[ModelManifest] = []
    for manifest in manifests:
        key = manifest.entry_path.resolve()
        if key in seen:
            continue
        seen.add(key)
        unique.append(manifest)
    return unique
