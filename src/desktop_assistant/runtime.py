from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .audit import AuditLog
from .confirmations import ConfirmationQueue
from .desktop_context import DesktopContextCollector
from .llm import LLMClient
from .memory import MemoryStore, Persona, PersonaStore
from .model_registry import ModelRegistry
from .settings import AppSettings
from .tools import ToolExecutor


@dataclass(slots=True)
class AssistantRuntime:
    collector: DesktopContextCollector
    audit_log: AuditLog
    persona: Persona
    memory_store: MemoryStore | None
    tools: ToolExecutor
    llm: LLMClient
    model_registry: ModelRegistry
    confirmation_queue: ConfirmationQueue


class RuntimeFactory:
    def __init__(self, settings: AppSettings, extra_model_dirs: list[str] | None = None) -> None:
        self.settings = settings
        self.extra_model_dirs = extra_model_dirs or []

    def build(self) -> AssistantRuntime:
        collector = DesktopContextCollector(
            visible_window_limit=self.settings.context.visible_window_limit,
            ocr_languages=self.settings.context.ocr_languages,
        )
        audit_log = AuditLog(_rooted_path(self.settings.root, self.settings.paths.audit_log))
        persona = PersonaStore(_rooted_path(self.settings.root, self.settings.persona.path)).load()
        memory_store = (
            MemoryStore(_rooted_path(self.settings.root, self.settings.memory.path))
            if self.settings.memory.enabled
            else None
        )
        confirmation_queue = ConfirmationQueue()
        tools = ToolExecutor(
            collector=collector,
            audit_log=audit_log,
            max_context_chars=self.settings.context.max_context_chars,
            allow_ocr=self.settings.context.ocr_enabled,
            memory_store=memory_store,
            confirmation_queue=confirmation_queue,
            permission_policy=self.settings.permissions,
        )
        return AssistantRuntime(
            collector=collector,
            audit_log=audit_log,
            persona=persona,
            memory_store=memory_store,
            tools=tools,
            llm=LLMClient(self.settings.llm),
            model_registry=ModelRegistry(
                root=self.settings.root,
                settings=self.settings.models,
                extra_dirs=self.extra_model_dirs,
                env_values=self.settings.root_env,
            ),
            confirmation_queue=confirmation_queue,
        )


def _rooted_path(root: Path, path_value: str) -> Path:
    path = Path(path_value).expanduser()
    return path if path.is_absolute() else root / path
