from pathlib import Path

import numpy as np

from musesplit.core.audio_io import write_audio
from musesplit.core.cache import CacheManager


def test_cache_roundtrip(tmp_path: Path) -> None:
    source = tmp_path / "source.wav"
    audio = np.zeros((44100, 2), dtype=np.float32)
    write_audio(source, audio, 44100)

    manager = CacheManager(tmp_path / "splits", "htdemucs_ft")
    key = manager.cache_key(source)
    cache_dir = manager.cache_dir(key)
    cache_dir.mkdir(parents=True, exist_ok=True)

    stems = {}
    for stem_name in ["vocals", "drums", "bass", "other"]:
        stem_path = cache_dir / f"{stem_name}.wav"
        write_audio(stem_path, audio, 44100)
        stems[stem_name] = stem_path

    manager.save_manifest(key, source, sample_rate=44100, duration_s=1.0, stems=stems)
    entry = manager.get(source)

    assert entry is not None
    assert entry.key == key
    assert set(entry.stems.keys()) == {"vocals", "drums", "bass", "other"}
