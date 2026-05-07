from __future__ import annotations

import argparse
import json
from pathlib import Path

from .service import AssistantService
from .settings import load_settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="桌面智能体助手")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="设置 TOML 文件路径。默认使用 config/settings.toml（如果存在）。",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="用于解析相对路径的项目根目录。",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="只加载配置并扫描模型，不启动图形界面。",
    )
    parser.add_argument(
        "--model-dir",
        action="append",
        default=[],
        help="额外的模型来源目录，可以重复传入。",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = load_settings(config_path=args.config, root=args.root)

    if args.check:
        service = AssistantService(settings, extra_model_dirs=args.model_dir)
        registry = service.runtime.model_registry
        profile = service.public_state()["settings"]["profile"]
        print(
            json.dumps(
                {
                    "root": str(settings.root),
                    "llm": {
                        "provider_profile": settings.llm.provider_profile,
                        "base_url": settings.llm.base_url,
                        "model": settings.llm.model,
                        "api_key_env": settings.llm.api_key_env,
                    },
                    "active_profile": profile["active_id"],
                    "active_model_id": service.active_model_id,
                    "profile_settings_file": profile["settings_file"],
                    "model_source_dirs": registry.source_dirs,
                    "models_found": len(registry.models),
                    "model_kinds": sorted({model.kind for model in registry.models}),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    from .qt_app import run_app

    return run_app(settings, extra_model_dirs=args.model_dir)


if __name__ == "__main__":
    raise SystemExit(main())
