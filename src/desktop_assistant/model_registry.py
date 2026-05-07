from __future__ import annotations

from pathlib import Path

from .model_sources import ModelSourceResolver
from .models import ModelManifest, discover_models
from .settings import ModelSettings


class ModelRegistry:
    def __init__(
        self,
        root: Path,
        settings: ModelSettings,
        extra_dirs: list[str] | None = None,
        env_values: dict[str, str] | None = None,
    ) -> None:
        self.root = root
        self.settings = settings
        self.extra_dirs = extra_dirs or []
        self.resolver = ModelSourceResolver(
            root=root,
            sources_file=settings.sources_file,
            env_var=settings.env_var,
            env_values=env_values,
        )
        self.source_dirs = self.resolver.resolve(settings.search_dirs, self.extra_dirs)
        self.models = discover_models(self.source_dirs, root=root)

    def list(self) -> list[ModelManifest]:
        return list(self.models)

    def exists(self, model_id: str) -> bool:
        return any(model.id == model_id for model in self.models)

    def default_id(self) -> str | None:
        return self.models[0].id if self.models else None

    def to_frontend(self) -> list[dict[str, object]]:
        return [model.to_frontend() for model in self.models]
