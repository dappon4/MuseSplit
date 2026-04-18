"""Configuration and app paths."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .constants import DEFAULT_MODEL


@dataclass(frozen=True)
class AppPaths:
    base_dir: Path
    cache_dir: Path
    splits_dir: Path
    downloads_dir: Path
    outputs_dir: Path
    logs_dir: Path
    config_file: Path


@dataclass
class AppSettings:
    demucs_model: str = DEFAULT_MODEL


def resolve_app_paths() -> AppPaths:
    base_dir = Path.home() / ".musesplit"
    cache_dir = base_dir / "cache"
    splits_dir = cache_dir / "splits"
    downloads_dir = cache_dir / "downloads"
    outputs_dir = base_dir / "output"
    logs_dir = base_dir / "logs"
    config_file = base_dir / "config.json"

    for directory in [base_dir, cache_dir, splits_dir, downloads_dir, outputs_dir, logs_dir]:
        directory.mkdir(parents=True, exist_ok=True)

    return AppPaths(
        base_dir=base_dir,
        cache_dir=cache_dir,
        splits_dir=splits_dir,
        downloads_dir=downloads_dir,
        outputs_dir=outputs_dir,
        logs_dir=logs_dir,
        config_file=config_file,
    )
