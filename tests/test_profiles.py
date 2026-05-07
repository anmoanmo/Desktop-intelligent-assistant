from pathlib import Path
import tomllib

from desktop_assistant.memory import MemoryStore, PersonaStore
from desktop_assistant.profiles import ConversationStore, ProfileStore
from desktop_assistant.settings import load_settings


def test_profile_store_creates_default_and_copies_legacy_state(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    PersonaStore(data_dir / "persona.toml").load()
    MemoryStore(data_dir / "memory.json").add("用户喜欢简洁回答。", category="preference")
    settings = load_settings(root=tmp_path)
    settings.models.default_id = "model-1"

    store = ProfileStore(tmp_path)
    active = store.apply_active_to_settings(settings)

    profile_dir = tmp_path / "data" / "assistants" / "default"
    raw = tomllib.loads((profile_dir / "settings.toml").read_text(encoding="utf-8"))
    assert active.id == "default"
    assert raw["models"]["default_id"] == "model-1"
    assert (profile_dir / "persona.toml").exists()
    assert MemoryStore(profile_dir / "memory.json").count() == 1
    assert settings.persona.path == str(profile_dir / "persona.toml")


def test_profile_store_create_switch_rename_delete(tmp_path: Path) -> None:
    settings = load_settings(root=tmp_path)
    store = ProfileStore(tmp_path)
    store.ensure(settings)

    created = store.create("测试小人", settings)
    switched = store.switch(created.id)
    renamed = store.rename(created.id, "测试小人二号")
    active = store.delete(created.id)

    assert switched.id == created.id
    assert renamed.name == "测试小人二号"
    assert active.id == "default"
    assert not (tmp_path / "data" / "assistants" / created.id).exists()


def test_conversation_store_persists_recent_messages(tmp_path: Path) -> None:
    store = ConversationStore(tmp_path / "conversations.jsonl")
    store.append_pair("你好", "你好。")
    store.append("assistant", "该休息一下了。", source="proactive")

    assert store.count() == 3
    assert store.recent_messages(limit=2) == [
        {"role": "assistant", "content": "你好。"},
        {"role": "assistant", "content": "该休息一下了。"},
    ]
