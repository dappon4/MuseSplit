"""Stem cache logic."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from ..constants import STEM_NAMES


@dataclass
class CacheEntry:
    key: str
    directory: Path
    manifest_path: Path
    stems: Dict[str, Path]


class CacheManager:
    def __init__(self, splits_root: Path, model_name: str) -> None:
        self.splits_root = splits_root
        self.model_name = model_name

    def source_hash(self, source_file: Path) -> str:
        digest = hashlib.sha256()
        with source_file.open("rb") as f:
            while True:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    def cache_key(self, source_file: Path) -> str:
        return f"{self.source_hash(source_file)}_{self.model_name}"

    def cache_dir(self, key: str) -> Path:
        return self.splits_root / key

    def get(self, source_file: Path) -> Optional[CacheEntry]:
        key = self.cache_key(source_file)
        entry_dir = self.cache_dir(key)
        manifest = entry_dir / "manifest.json"
        if not manifest.exists():
            return None

        try:
            content = json.loads(manifest.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

        stems: Dict[str, Path] = {}
        for name in STEM_NAMES:
            rel_path = content.get("stems", {}).get(name)
            if not rel_path:
                return None
            stem_path = entry_dir / rel_path
            if not stem_path.exists():
                return None
            stems[name] = stem_path

        return CacheEntry(key=key, directory=entry_dir, manifest_path=manifest, stems=stems)

    def save_manifest(self, key: str, source_file: Path, sample_rate: int, duration_s: float, stems: Dict[str, Path]) -> Path:
        entry_dir = self.cache_dir(key)
        entry_dir.mkdir(parents=True, exist_ok=True)
        manifest = entry_dir / "manifest.json"
        payload = {
            "key": key,
            "source_file": str(source_file),
            "model": self.model_name,
            "sample_rate": sample_rate,
            "duration_s": duration_s,
            "stems": {name: path.name for name, path in stems.items()},
        }
        manifest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return manifest
