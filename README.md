# MuseSplit

MuseSplit is a desktop app for splitting songs into stems (vocals, drums, bass, other) with Demucs, previewing mixes in-app, and exporting selected stems to a single WAV file.

## Highlights
- Input from YouTube URL or local audio file
- Demucs model selector (multiple model options)
- Stem caching so repeated remixing skips separation reruns
- In-app stem preview with:
  - play/pause transport
  - seek bar
  - global volume
  - live include/exclude toggles while previewing
- Export selected stems to WAV
- Activity panel with collapsible view
- Structured logs written to disk

## Requirements
- Python 3.10+
- ffmpeg installed and available on PATH

### Linux
```bash
sudo apt install ffmpeg
```

## Installation
```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

## Run
```bash
python -m musesplit.main
```

## How to Use
1. Enter a YouTube URL or choose a local audio file.
2. Pick the Demucs model from the model dropdown.
3. Click Split Track.
4. After stems are ready, use checkboxes to include/exclude tracks.
5. Preview in real time using play/pause, seek, and volume.
6. Click Mix Selected and Save WAV to export.

## Caching Behavior
- Stems are cached by source hash and selected model.
- Reprocessing the same source with the same model uses cached stems.
- App data directory:
  - `~/.musesplit/cache` for cached stems/downloads
  - `~/.musesplit/output` for default exports
  - `~/.musesplit/logs/musesplit.log` for logs

## Troubleshooting

### `Unable to import demucs: No module named 'demucs.api'`
```bash
pip install -U demucs torch
```
MuseSplit automatically falls back to `python -m demucs.separate` when `demucs.api` is unavailable.

### `TorchCodec is required for save_with_torchcodec`
```bash
pip install -U torchcodec
```

### Qt multimedia pipewire warnings on Linux
Messages like `Couldn't load pipewire-0.3 library` can appear depending on your runtime environment. They are often backend warnings and may be non-fatal.

### Wayland maximize/protocol issues
Recent UI safeguards avoid maximize-driven resize mismatches. If issues persist, run in normal windowed mode.

## Packaging Notes
- Building a native Windows `.exe` is best done on Windows (local machine, VM, or CI Windows runner).
- PyInstaller is not a reliable cross-compiler from Linux/WSL for this stack.
