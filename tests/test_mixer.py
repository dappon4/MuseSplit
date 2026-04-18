from pathlib import Path

import numpy as np

from musesplit.core.audio_io import write_audio
from musesplit.core.mixer import mix_selected_stems


def test_mix_selected_stems(tmp_path: Path) -> None:
    stem_paths = {}
    for idx, name in enumerate(["vocals", "drums"]):
        audio = np.ones((1000, 2), dtype=np.float32) * (0.2 + idx * 0.1)
        path = tmp_path / f"{name}.wav"
        write_audio(path, audio, 44100)
        stem_paths[name] = path

    mixed, sr = mix_selected_stems(stem_paths, ["vocals", "drums"])

    assert sr == 44100
    assert mixed.shape == (1000, 2)
    assert np.max(np.abs(mixed)) <= 0.98
