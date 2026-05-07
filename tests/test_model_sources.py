from pathlib import Path

from desktop_assistant.model_sources import ModelSourceResolver


def test_model_source_resolver_file_and_extra_dirs(tmp_path: Path) -> None:
    sources_file = tmp_path / "sources.toml"
    sources_file.write_text(
        """
[[sources]]
name = "one"
path = "./one"
enabled = true

[[sources]]
name = "off"
path = "./off"
enabled = false
""",
        encoding="utf-8",
    )

    resolver = ModelSourceResolver(tmp_path, str(sources_file), "UNSET_MODEL_DIRS_FOR_TEST")

    assert resolver.resolve(["./configured"], ["./extra"]) == ["./configured", "./one", "./extra"]


def test_model_source_resolver_ignores_missing_file(tmp_path: Path) -> None:
    resolver = ModelSourceResolver(tmp_path, "missing.toml", "UNSET_MODEL_DIRS_FOR_TEST")

    assert resolver.resolve([], []) == []


def test_model_source_resolver_prefers_root_env_values(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MODEL_DIRS_TEST", "./from-process")
    resolver = ModelSourceResolver(tmp_path, "", "MODEL_DIRS_TEST", env_values={"MODEL_DIRS_TEST": "./from-root"})

    assert resolver.resolve([], []) == ["./from-root"]
