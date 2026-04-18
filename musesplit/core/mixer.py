"""Stem mixing utilities."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, Tuple

import numpy as np

from .audio_io import read_audio, write_audio


class MixError(Exception):
    """Raised when a mix cannot be generated."""


def _normalize(audio: np.ndarray, peak_target: float = 0.98) -> np.ndarray:
    peak = float(np.max(np.abs(audio)))
    if peak <= 1e-9:
        return audio
    if peak > peak_target:
        return audio * (peak_target / peak)
    return audio


def mix_selected_stems(stem_files: Dict[str, Path], selected_names: Iterable[str]) -> Tuple[np.ndarray, int]:
    selected = [name for name in selected_names if name in stem_files]
    if not selected:
        raise MixError("Select at least one stem")

    combined: np.ndarray | None = None
    sample_rate: int | None = None

    for name in selected:
        audio, sr = read_audio(stem_files[name])
        if combined is None:
            combined = np.zeros_like(audio)
            sample_rate = sr
        if sr != sample_rate:
            raise MixError("Stem sample rates do not match")
        if audio.shape != combined.shape:
            raise MixError("Stem shapes do not match")
        combined += audio

    assert combined is not None and sample_rate is not None
    combined /= float(len(selected))
    combined = _normalize(combined)
    return combined, sample_rate


def export_mix(stem_files: Dict[str, Path], selected_names: Iterable[str], output_file: Path) -> Path:
    mixed, sr = mix_selected_stems(stem_files, selected_names)
    write_audio(output_file, mixed, sr)
    return output_file
