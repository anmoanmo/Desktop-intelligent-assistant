from pathlib import Path

from desktop_assistant.models import discover_models


def test_discover_live2d_model(tmp_path: Path) -> None:
    model_dir = tmp_path / "models" / "avatar"
    model_dir.mkdir(parents=True)
    (model_dir / "avatar.model3.json").write_text("{}", encoding="utf-8")

    models = discover_models(["./models"], root=tmp_path)

    assert len(models) == 1
    assert models[0].kind == "live2d"
    assert models[0].name == "avatar"


def test_discover_live2d_metadata_and_missing_assets(tmp_path: Path) -> None:
    model_dir = tmp_path / "models" / "avatar"
    texture_dir = model_dir / "avatar.4096"
    texture_dir.mkdir(parents=True)
    (model_dir / "avatar.moc3").write_bytes(b"MOC3")
    (texture_dir / "texture_00.png").write_bytes(b"png")
    (model_dir / "Happy.exp3.json").write_text("{}", encoding="utf-8")
    (model_dir / "avatar.model3.json").write_text(
        """
{
  "Version": 3,
  "FileReferences": {
    "Moc": "avatar.moc3",
    "Textures": ["avatar.4096/texture_00.png", "avatar.4096/missing.png"],
    "Physics": "avatar.physics3.json"
  }
}
""",
        encoding="utf-8",
    )

    models = discover_models(["./models"], root=tmp_path)

    live2d = models[0].metadata["live2d"]  # type: ignore[index]
    assert live2d["texture_count"] == 2
    assert sorted(live2d["missing_assets"]) == ["avatar.4096/missing.png", "avatar.physics3.json"]
    assert live2d["expressions"] == [{"name": "Happy", "file": "Happy.exp3.json"}]


def test_discover_spine_model_by_directory_scan(tmp_path: Path) -> None:
    model_dir = tmp_path / "models" / "spine-avatar"
    model_dir.mkdir(parents=True)
    (model_dir / "avatar.skel").write_bytes(b"skel")
    (model_dir / "avatar.atlas").write_text("atlas", encoding="utf-8")
    (model_dir / "avatar.png").write_bytes(b"png")

    models = discover_models(["./models"], root=tmp_path)

    assert len(models) == 1
    assert models[0].kind == "spine38"
    assert models[0].name == "spine-avatar"
    frontend = models[0].to_frontend()
    assert frontend["assets"]["atlas_url"].startswith("file://")
    assert frontend["assets"]["png_url"].startswith("file://")


def test_discover_ark_metadata_with_asset_lists(tmp_path: Path) -> None:
    root = tmp_path / "Ark-Models-main"
    model_dir = root / "models_enemies" / "1286_dumcy"
    model_dir.mkdir(parents=True)
    (model_dir / "enemy_1286_dumcy.skel").write_bytes(b"skel")
    (model_dir / "enemy_1286_dumcy.atlas").write_text("atlas", encoding="utf-8")
    (model_dir / "enemy_1286_dumcy.png").write_bytes(b"png")
    (root / "models_data.json").write_text(
        """
{
  "storageDirectory": {"Enemy": "models_enemies"},
  "data": {
    "1286_dumcy": {
      "type": "Enemy",
      "name": "Dumcy",
      "assetList": {
        ".atlas": "enemy_1286_dumcy.atlas",
        ".png": ["enemy_1286_dumcy$0.png", "enemy_1286_dumcy.png"],
        ".skel": ["enemy_1286_dumcy$0.skel", "enemy_1286_dumcy.skel"]
      }
    }
  }
}
""",
        encoding="utf-8",
    )

    models = discover_models(["./Ark-Models-main"], root=tmp_path)

    assert len(models) == 1
    assert models[0].entry_path.name == "enemy_1286_dumcy.skel"
    frontend = models[0].to_frontend()
    assert frontend["assets"]["skel_url"].endswith("enemy_1286_dumcy.skel")
    assert frontend["assets"]["atlas_url"].endswith("enemy_1286_dumcy.atlas")
