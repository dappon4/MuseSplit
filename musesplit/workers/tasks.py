"""Background worker threads."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict

from PyQt6.QtCore import QThread, pyqtSignal

from ..core.cache import CacheManager
from ..core.downloader import Downloader
from ..core.separation import SeparationError, StemSeparator

LOGGER = logging.getLogger(__name__)


class ProcessingWorker(QThread):
    progress = pyqtSignal(str, float)
    done = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(
        self,
        source_kind: str,
        source_value: str,
        cache: CacheManager,
        downloader: Downloader,
        separator: StemSeparator,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.source_kind = source_kind
        self.source_value = source_value
        self.cache = cache
        self.downloader = downloader
        self.separator = separator

    def run(self) -> None:
        try:
            LOGGER.info("Processing started source_kind=%s source_value=%s", self.source_kind, self.source_value)
            self.progress.emit("Preparing source", 0.02)
            source_file = self._resolve_source()
            LOGGER.info("Resolved source_file=%s", source_file)

            cached = self.cache.get(source_file)
            if cached is not None:
                LOGGER.info("Cache hit key=%s source_file=%s", cached.key, source_file)
                self.progress.emit("Loaded from cache", 1.0)
                self.done.emit(
                    {
                        "source_file": str(source_file),
                        "cache_key": cached.key,
                        "stems": {k: str(v) for k, v in cached.stems.items()},
                        "from_cache": True,
                    }
                )
                return

            key = self.cache.cache_key(source_file)
            destination = self.cache.cache_dir(key)
            LOGGER.info("Cache miss key=%s destination=%s", key, destination)

            stems = self.separator.separate_to_directory(
                source_file,
                destination,
                progress_callback=lambda msg, value: self.progress.emit(msg, value),
            )
            LOGGER.info("Separation complete key=%s stems=%s", key, list(stems.keys()))

            # Read a stem to infer properties for manifest.
            import soundfile as sf

            example = next(iter(stems.values()))
            data, sample_rate = sf.read(example, always_2d=True)
            duration_s = float(data.shape[0]) / float(sample_rate)

            self.cache.save_manifest(
                key=key,
                source_file=source_file,
                sample_rate=sample_rate,
                duration_s=duration_s,
                stems=stems,
            )
            LOGGER.info(
                "Manifest saved key=%s sample_rate=%s duration_s=%.2f",
                key,
                sample_rate,
                duration_s,
            )

            self.done.emit(
                {
                    "source_file": str(source_file),
                    "cache_key": key,
                    "stems": {k: str(v) for k, v in stems.items()},
                    "from_cache": False,
                }
            )
        except SeparationError as exc:
            LOGGER.exception("SeparationError during processing")
            self.failed.emit(str(exc))
        except Exception as exc:
            LOGGER.exception("Unhandled error during processing")
            self.failed.emit(str(exc))

    def _resolve_source(self) -> Path:
        if self.source_kind == "file":
            path = Path(self.source_value).expanduser().resolve()
            LOGGER.info("Using local file source=%s", path)
            return path
        if self.source_kind == "url":
            self.progress.emit("Downloading from URL", 0.1)
            LOGGER.info("Downloading source from URL=%s", self.source_value)
            downloaded = self.downloader.download_youtube_audio(self.source_value).resolve()
            LOGGER.info("Downloaded audio file=%s", downloaded)
            return downloaded
        raise ValueError("Invalid source kind")
