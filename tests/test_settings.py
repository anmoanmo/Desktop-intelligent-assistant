from pathlib import Path
import tomllib

from desktop_assistant.settings import load_settings, save_runtime_settings


def test_load_defaults(tmp_path: Path) -> None:
    settings = load_settings(root=tmp_path)

    assert settings.llm.provider_profile == "deepseek"
    assert settings.llm.base_url == "https://api.deepseek.com"
    assert settings.llm.model == "deepseek-v4-pro"
    assert settings.privacy.send_screenshots is False
    assert settings.permissions.desktop_context == "ask"
    assert settings.permissions.ocr == "deny"
    assert settings.permissions.open_url == "ask"
    assert settings.permissions.web_search == "allow"
    assert settings.permissions.list_memories == "allow"
    assert settings.memory.enabled is True
    assert settings.memory.auto_extract_enabled is False
    assert settings.memory.auto_extract_max_entries == 3
    assert settings.autonomy.enabled is False
    assert settings.autonomy.interval_seconds == 180
    assert settings.autonomy.window_seconds == 600
    assert settings.autonomy.max_messages_per_window == 3
    assert settings.autonomy.min_interval_seconds == 60
    assert settings.autonomy.max_interval_seconds == 180
    assert settings.ui.avatar_always_on_top is True
    assert settings.persona.path == "data/persona.toml"


def test_load_toml_override(tmp_path: Path) -> None:
    config = tmp_path / "settings.toml"
    config.write_text(
        """
[llm]
model = "deepseek-v4-flash"

[models]
search_dirs = ["./custom-models"]

[permissions]
open_url = "deny"
""",
        encoding="utf-8",
    )

    settings = load_settings(config_path=config, root=tmp_path)

    assert settings.llm.model == "deepseek-v4-flash"
    assert settings.models.search_dirs == ["./custom-models"]
    assert settings.permissions.open_url == "deny"


def test_root_config_overrides_env_and_env_sets_api_key(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "settings.toml").write_text(
        """
[llm]
model = "from-toml"

[models]
search_dirs = ["./from-toml"]
""",
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text(
        """
DEEPSEEK_API_KEY=from-root-env
DESKTOP_ASSISTANT_LLM_MODEL=from-root-env
DESKTOP_ASSISTANT_MODEL_SEARCH_DIRS=./one:./two
DESKTOP_ASSISTANT_AUTONOMY_ENABLED=false
DESKTOP_ASSISTANT_AUTONOMY_INTERVAL_SECONDS=90
""",
        encoding="utf-8",
    )

    settings = load_settings(root=tmp_path)

    assert settings.env_file == tmp_path / ".env"
    assert settings.llm.model == "from-toml"
    assert settings.llm.resolve_api_key() == "from-root-env"
    assert settings.models.search_dirs == ["./from-toml"]
    assert settings.autonomy.enabled is False
    assert settings.autonomy.interval_seconds == 90


def test_save_runtime_settings_writes_safe_editable_values(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config = config_dir / "settings.toml"
    config.write_text(
        """
[llm]
model = "from-toml"
api_key = "do-not-keep"

[models]
search_dirs = ["./models"]
""",
        encoding="utf-8",
    )
    settings = load_settings(root=tmp_path)
    settings.models.default_id = "model-1"
    settings.ui.avatar_x = 120
    settings.ui.avatar_y = -80
    settings.ui.avatar_scale = 1.35
    settings.ui.avatar_always_on_top = False
    settings.ui.main_x = 500
    settings.ui.main_y = 160
    settings.ui.main_width = 720
    settings.ui.main_height = 680
    settings.autonomy.enabled = False
    settings.autonomy.interval_seconds = 45
    settings.autonomy.cooldown_seconds = 300
    settings.autonomy.window_seconds = 900
    settings.autonomy.max_messages_per_window = 5
    settings.autonomy.min_interval_seconds = 75
    settings.autonomy.max_interval_seconds = 240
    settings.memory.auto_extract_enabled = False
    settings.memory.auto_extract_max_entries = 2
    settings.permissions.open_url = "deny"
    settings.permissions.ocr = "ask"

    written = save_runtime_settings(settings)

    assert written == config
    raw = tomllib.loads(config.read_text(encoding="utf-8"))
    assert raw["llm"]["model"] == "from-toml"
    assert "api_key" not in raw["llm"]
    assert raw["models"]["search_dirs"] == ["./models"]
    assert raw["models"]["default_id"] == "model-1"
    assert raw["ui"]["avatar_x"] == 120
    assert raw["ui"]["avatar_y"] == -80
    assert raw["ui"]["avatar_scale"] == 1.35
    assert raw["ui"]["avatar_always_on_top"] is False
    assert raw["ui"]["main_x"] == 500
    assert raw["ui"]["main_y"] == 160
    assert raw["ui"]["main_width"] == 720
    assert raw["ui"]["main_height"] == 680
    assert raw["autonomy"]["enabled"] is False
    assert raw["autonomy"]["interval_seconds"] == 45
    assert raw["autonomy"]["cooldown_seconds"] == 300
    assert raw["autonomy"]["window_seconds"] == 900
    assert raw["autonomy"]["max_messages_per_window"] == 5
    assert raw["autonomy"]["min_interval_seconds"] == 75
    assert raw["autonomy"]["max_interval_seconds"] == 240
    assert raw["memory"]["auto_extract_enabled"] is False
    assert raw["memory"]["auto_extract_max_entries"] == 2
    assert raw["permissions"]["open_url"] == "deny"
    assert raw["permissions"]["ocr"] == "ask"
