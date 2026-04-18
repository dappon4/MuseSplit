"""Demucs separation wrapper."""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict, Optional

import numpy as np

from ..constants import STEM_NAMES
from .audio_io import ensure_stereo, read_audio, write_audio

ProgressCallback = Callable[[str, float], None]

LOGGER = logging.getLogger(__name__)


class SeparationError(Exception):
    """Raised when demucs separation fails."""


class StemSeparator:
    def __init__(self, model_name: str = "htdemucs_ft") -> None:
        self.model_name = model_name

    def _resolve_device(self) -> str:
        try:
            import torch

            if torch.cuda.is_available():
                return "cuda"
        except Exception as exc:
            LOGGER.warning("Could not query CUDA availability, defaulting to CPU: %s", exc)
        return "cpu"

    def separate_to_directory(
        self,
        source_file: Path,
        destination_dir: Path,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> Dict[str, Path]:
        destination_dir.mkdir(parents=True, exist_ok=True)
        LOGGER.info(
            "Starting separation source_file=%s model=%s destination=%s",
            source_file,
            self.model_name,
            destination_dir,
        )
        if progress_callback:
            progress_callback("Loading model", 0.05)

        device = self._resolve_device()
        LOGGER.info("Using separation device=%s", device)

        stems_data: Dict[str, object] | None = None
        import_error: str | None = None

        try:
            from demucs.api import Separator

            separator = Separator(model=self.model_name, device=device)
            LOGGER.info("Using demucs.api Separator on device=%s", device)
            if progress_callback:
                progress_callback("Running separation", 0.2)
            _, stems_data = separator.separate_audio_file(source_file)
        except Exception as exc:
            import_error = str(exc)
            LOGGER.warning("demucs.api path unavailable: %s", import_error)

        if stems_data is None:
            if progress_callback:
                progress_callback("Falling back to Demucs CLI", 0.2)
            LOGGER.info("Falling back to CLI separation path")
            return self._separate_with_cli(source_file, destination_dir, progress_callback, import_error, device)

        if progress_callback:
            progress_callback("Saving stems", 0.8)

        original_audio, sample_rate = read_audio(source_file)
        frame_count = original_audio.shape[0]
        saved: Dict[str, Path] = {}

        for idx, stem_name in enumerate(STEM_NAMES):
            if stem_name not in stems_data:
                continue
            tensor = stems_data[stem_name]
            stem_array = tensor.detach().cpu().numpy().T
            stem_array = ensure_stereo(stem_array)
            if stem_array.shape[0] > frame_count:
                stem_array = stem_array[:frame_count, :]
            elif stem_array.shape[0] < frame_count:
                pad = np.zeros((frame_count - stem_array.shape[0], stem_array.shape[1]), dtype=np.float32)
                stem_array = np.concatenate([stem_array, pad], axis=0)
            out_file = destination_dir / f"{stem_name}.wav"
            write_audio(out_file, stem_array, sample_rate)
            saved[stem_name] = out_file
            LOGGER.info("Saved API stem stem=%s path=%s", stem_name, out_file)
            if progress_callback:
                progress = 0.8 + ((idx + 1) / max(1, len(STEM_NAMES))) * 0.19
                progress_callback(f"Saved {stem_name}", progress)

        if progress_callback:
            progress_callback("Done", 1.0)
        LOGGER.info("Separation finished through API stems=%s", list(saved.keys()))
        return saved

    def _separate_with_cli(
        self,
        source_file: Path,
        destination_dir: Path,
        progress_callback: Optional[ProgressCallback],
        import_error: str | None,
        device: str,
    ) -> Dict[str, Path]:
        command = [
            sys.executable,
            "-m",
            "demucs.separate",
            "-n",
            self.model_name,
            "-d",
            device,
            "-o",
            str(destination_dir),
            str(source_file),
        ]
        LOGGER.info("Running CLI command: %s", " ".join(command))

        if progress_callback:
            progress_callback("Running Demucs CLI", 0.35)

        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except FileNotFoundError as exc:
            LOGGER.exception("Python executable not found for CLI separation")
            raise SeparationError("Python executable was not found while running Demucs CLI.") from exc
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            detail = self._summarize_cli_error(stderr) or str(exc)
            if import_error:
                detail = f"{detail}. Import error: {import_error}"
            LOGGER.error("CLI separation failed summary: %s", detail)
            if stderr:
                LOGGER.debug("CLI separation full stderr:\n%s", stderr)
            raise SeparationError(f"Demucs CLI failed: {detail}") from exc

        if progress_callback:
            progress_callback("Collecting stems", 0.8)

        saved: Dict[str, Path] = {}
        for stem_name in STEM_NAMES:
            matches = list(destination_dir.rglob(f"{stem_name}.wav"))
            if not matches:
                continue
            source_stem = matches[0]
            target_stem = destination_dir / f"{stem_name}.wav"
            if source_stem.resolve() != target_stem.resolve():
                shutil.copy2(source_stem, target_stem)
            saved[stem_name] = target_stem
            LOGGER.info("Saved CLI stem stem=%s path=%s", stem_name, target_stem)

        if not saved:
            extra = f" Import error: {import_error}" if import_error else ""
            LOGGER.error("CLI produced no stems.%s", extra)
            raise SeparationError(f"Demucs did not produce stem files.{extra}")

        if progress_callback:
            progress_callback("Done", 1.0)
        LOGGER.info("Separation finished through CLI stems=%s", list(saved.keys()))
        return saved

    def _summarize_cli_error(self, stderr_text: str) -> str:
        if not stderr_text:
            return "Demucs CLI exited with an error"

        lower_text = stderr_text.lower()
        if "torchcodec is required" in lower_text or "no module named 'torchcodec'" in lower_text:
            return (
                "TorchCodec is required by torchaudio in this environment. "
                "Install it with: pip install torchcodec"
            )

        lines = [line.strip() for line in stderr_text.splitlines() if line.strip()]
        if not lines:
            return "Demucs CLI exited with an error"

        # Keep meaningful error lines and drop tqdm/progress noise.
        meaningful = []
        for line in lines:
            lower = line.lower()
            if "traceback" in lower:
                meaningful.append(line)
                continue
            if "error" in lower or "exception" in lower or "runtimeerror" in lower:
                meaningful.append(line)
                continue
            if "seconds/s" in lower or "%|" in line or "<" in line and ">" not in line:
                continue
            if line.startswith("|"):
                continue

        if meaningful:
            return meaningful[-1]

        # Fallback to last non-empty line if no obvious error token exists.
        return lines[-1]
