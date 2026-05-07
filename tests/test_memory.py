from pathlib import Path

from desktop_assistant.memory import MemoryStore, Persona, PersonaStore


def test_persona_store_creates_default(tmp_path: Path) -> None:
    path = tmp_path / "persona.toml"

    persona = PersonaStore(path).load()

    assert path.exists()
    assert persona.name == "桌面助理"
    assert "固定人设" in persona.to_prompt_text()


def test_persona_store_saves_updates(tmp_path: Path) -> None:
    path = tmp_path / "persona.toml"
    store = PersonaStore(path)
    store.save(
        Persona(
            name="小助理",
            role="桌面助理",
            personality="直接",
            speaking_style="中文短句",
            instructions=["先确认风险。"],
        )
    )

    persona = PersonaStore(path).load()

    assert persona.name == "小助理"
    assert persona.personality == "直接"
    assert persona.speaking_style == "中文短句"
    assert persona.instructions == ["先确认风险。"]


def test_memory_store_persists_entries(tmp_path: Path) -> None:
    path = tmp_path / "memory.json"
    store = MemoryStore(path)

    entry = store.add("用户主要使用 DeepSeek API。", category="preference", importance=0.8)
    reloaded = MemoryStore(path).list()

    assert entry.id == reloaded[0].id
    assert reloaded[0].category == "preference"
    assert "DeepSeek" in reloaded[0].content


def test_memory_store_rejects_sensitive_content(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.json")

    try:
        store.add("我的 password 是 123456")
    except ValueError as exc:
        assert "敏感" in str(exc)
    else:
        raise AssertionError("expected sensitive memory rejection")


def test_memory_store_updates_and_deletes_entries(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.json")
    entry = store.add("用户喜欢简洁回答。", category="preference")

    updated = store.update(entry.id, content="用户喜欢直接、简洁的回答。", importance=0.9)
    deleted = store.delete(entry.id)

    assert updated.importance == 0.9
    assert "直接" in updated.content
    assert deleted is True
    assert store.count() == 0
