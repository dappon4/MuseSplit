"""YouTube download helpers."""

from __future__ import annotations

from pathlib import Path

from yt_dlp import YoutubeDL


class DownloadError(Exception):
    """Raised when media download fails."""


class Downloader:
    def __init__(self, download_dir: Path) -> None:
        self.download_dir = download_dir
        self.download_dir.mkdir(parents=True, exist_ok=True)

    def download_youtube_audio(self, url: str) -> Path:
        output_template = str(self.download_dir / "%(title)s.%(ext)s")
        options = {
            "format": "bestaudio/best",
            "outtmpl": output_template,
            "noplaylist": True,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "wav",
                    "preferredquality": "0",
                }
            ],
            "quiet": True,
            "no_warnings": True,
        }

        try:
            with YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=True)
                requested = info.get("requested_downloads") or []
                if requested:
                    filename = requested[0].get("filepath")
                    if filename:
                        return Path(filename).with_suffix(".wav")

                fallback = ydl.prepare_filename(info)
                return Path(fallback).with_suffix(".wav")
        except Exception as exc:
            raise DownloadError(str(exc)) from exc
