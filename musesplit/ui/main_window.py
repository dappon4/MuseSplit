"""Main application window."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Dict

from PyQt6.QtCore import QEvent, QTimer, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QCheckBox,
    QPushButton,
    QSlider,
    QSizePolicy,
    QStyle,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..config import AppPaths
from ..constants import DEFAULT_MODEL, DEMUCS_MODEL_OPTIONS, STEM_NAMES
from ..core.cache import CacheManager
from ..core.downloader import Downloader
from ..core.mixer import MixError, export_mix
from ..core.separation import StemSeparator
from ..workers.tasks import ProcessingWorker

LOGGER = logging.getLogger(__name__)


class ClickSeekSlider(QSlider):
    """A slider that seeks to the clicked position immediately."""

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            if self.orientation() == Qt.Orientation.Horizontal:
                position = int(event.position().x())
                span = max(1, self.width())
            else:
                position = int(event.position().y())
                span = max(1, self.height())

            value = QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), position, span)
            self.setSliderPosition(value)
            self.setValue(value)
        super().mousePressEvent(event)


class ClickableTitleLabel(QLabel):
    """Label styled like a section title but clickable."""

    clicked = pyqtSignal()

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)


class MainWindow(QMainWindow):
    def __init__(self, paths: AppPaths, model_name: str) -> None:
        super().__init__()
        # Disable maximize controls to avoid Wayland maximize/resize protocol issues.
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)
        self.paths = paths
        self.model_name = model_name

        self.cache = CacheManager(paths.splits_dir, model_name)
        self.downloader = Downloader(paths.downloads_dir)
        self.separator = StemSeparator(model_name)

        self.worker: ProcessingWorker | None = None
        self.current_stems: Dict[str, Path] = {}
        self.stem_players: Dict[str, QMediaPlayer] = {}
        self.stem_outputs: Dict[str, QAudioOutput] = {}
        self.master_stem: str | None = None
        self.preview_duration_ms = 0
        self.preview_is_seeking = False
        self.separation_start_time: float | None = None
        self.is_separating = False
        self.activity_expanded = True

        self.elapsed_timer = QTimer(self)
        self.elapsed_timer.setInterval(1000)
        self.elapsed_timer.timeout.connect(self._update_elapsed_label)

        self.setWindowTitle("MuseSplit")
        self.resize(1060, 700)

        self._build_ui()
        self._adjust_window_height_to_content()

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and self.isMaximized():
            self.showNormal()

    def _build_ui(self) -> None:
        root = QWidget()
        main_layout = QVBoxLayout(root)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(16)

        grid = QGridLayout()
        grid.setSpacing(14)

        self.input_card = self._card_frame()
        input_layout = QVBoxLayout(self.input_card)
        input_layout.setSpacing(8)
        input_layout.addWidget(QLabel("YouTube URL"))
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://www.youtube.com/watch?v=...")
        input_layout.addWidget(self.url_edit)

        input_layout.addWidget(QLabel("Local audio file"))
        file_row = QHBoxLayout()
        self.file_edit = QLineEdit()
        self.file_edit.setPlaceholderText("Choose audio file")
        browse = QPushButton("Browse")
        browse.clicked.connect(self._pick_file)
        file_row.addWidget(self.file_edit, 1)
        file_row.addWidget(browse)
        input_layout.addLayout(file_row)

        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("Demucs model"))
        self.model_combo = QComboBox()
        self.model_combo.addItems(DEMUCS_MODEL_OPTIONS)
        initial_model = self.model_name if self.model_name in DEMUCS_MODEL_OPTIONS else DEFAULT_MODEL
        self.model_combo.setCurrentText(initial_model)
        self.model_combo.activated.connect(self._on_model_selected)
        model_row.addWidget(self.model_combo, 1)
        input_layout.addLayout(model_row)

        self.process_button = QPushButton("Split Track")
        self.process_button.clicked.connect(self._start_processing)
        input_layout.addWidget(self.process_button)
        input_layout.addStretch(1)
        self.input_card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        grid.addWidget(self.input_card, 0, 0, 1, 1, Qt.AlignmentFlag.AlignTop)

        self.stems_card = self._card_frame()
        stems_layout = QVBoxLayout(self.stems_card)
        stems_layout.setSpacing(8)
        stems_layout.addWidget(QLabel("Select stems to include"))
        self.stem_checks: Dict[str, QCheckBox] = {}
        for stem in STEM_NAMES:
            cb = QCheckBox(stem.capitalize())
            cb.setEnabled(False)
            cb.setChecked(True)
            cb.stateChanged.connect(lambda _state, s=stem: self._on_stem_toggle(s))
            self.stem_checks[stem] = cb
            stems_layout.addWidget(cb)

        stems_layout.addWidget(QLabel("Preview selected stems"))
        preview_row = QHBoxLayout()
        self.play_pause_button = QPushButton()
        self.play_pause_button.setEnabled(False)
        self.play_pause_button.setToolTip("Play/Pause selected stems")
        self.play_pause_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.play_pause_button.clicked.connect(self._toggle_playback)

        self.preview_seek_slider = ClickSeekSlider(Qt.Orientation.Horizontal)
        self.preview_seek_slider.setRange(0, 0)
        self.preview_seek_slider.setEnabled(False)
        self.preview_seek_slider.sliderPressed.connect(self._on_seek_pressed)
        self.preview_seek_slider.sliderReleased.connect(self._on_seek_released)

        self.preview_time_label = QLabel("0:00 / 0:00")
        self.preview_time_label.setMinimumWidth(90)

        preview_row.addWidget(self.play_pause_button)
        preview_row.addWidget(self.preview_seek_slider, 1)
        preview_row.addWidget(self.preview_time_label)
        stems_layout.addLayout(preview_row)

        volume_row = QHBoxLayout()
        volume_row.addWidget(QLabel("Preview volume"))
        self.preview_volume_slider = ClickSeekSlider(Qt.Orientation.Horizontal)
        self.preview_volume_slider.setRange(0, 100)
        self.preview_volume_slider.setValue(90)
        self.preview_volume_slider.valueChanged.connect(self._on_volume_changed)
        self.preview_volume_label = QLabel("90%")
        self.preview_volume_label.setMinimumWidth(48)
        volume_row.addWidget(self.preview_volume_slider, 1)
        volume_row.addWidget(self.preview_volume_label)
        stems_layout.addLayout(volume_row)

        self.export_button = QPushButton("Mix Selected and Save WAV")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self._export_mix)
        stems_layout.addWidget(self.export_button)
        stems_layout.addStretch(1)
        self.stems_card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        grid.addWidget(self.stems_card, 0, 1, 1, 1, Qt.AlignmentFlag.AlignTop)

        self.status_card = self._card_frame()
        status_layout = QVBoxLayout(self.status_card)
        status_layout.setSpacing(8)
        status_layout.addWidget(QLabel("Progress"))

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFixedHeight(20)
        self.progress_label = QLabel("Idle")
        self.progress_label.setFixedHeight(18)
        self.elapsed_label = QLabel("Separation elapsed: 0s")
        self.elapsed_label.setFixedHeight(18)

        status_layout.addWidget(self.progress)
        status_layout.addWidget(self.progress_label)
        status_layout.addWidget(self.elapsed_label)

        activity_row = QHBoxLayout()
        self.activity_title = ClickableTitleLabel("▼ Activity")
        self.activity_title.clicked.connect(self._toggle_activity_panel)
        activity_row.addWidget(self.activity_title)
        activity_row.addStretch(1)
        status_layout.addLayout(activity_row)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMinimumHeight(220)
        self.log_box.setCursorWidth(1)
        status_layout.addWidget(self.log_box)
        grid.addWidget(self.status_card, 1, 0, 1, 2)

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        main_layout.addLayout(grid)
        self.setCentralWidget(root)
        self._apply_activity_layout_state(expanded=True)

    def _card_frame(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("Card")
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame.setFrameShadow(QFrame.Shadow.Raised)
        return frame

    def _pick_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Audio File",
            str(Path.home()),
            "Audio Files (*.wav *.flac *.mp3 *.m4a *.ogg *.aac)",
        )
        if file_path:
            self.file_edit.setText(file_path)

    def _start_processing(self) -> None:
        url = self.url_edit.text().strip()
        file_path = self.file_edit.text().strip()

        source_kind = ""
        source_value = ""
        if url:
            source_kind, source_value = "url", url
        elif file_path:
            source_kind, source_value = "file", file_path
        else:
            self._show_error("Provide either a YouTube URL or a local file.")
            return

        selected_model = self.model_combo.currentText().strip()
        if selected_model and selected_model != self.model_name:
            self.model_name = selected_model
            self.cache = CacheManager(self.paths.splits_dir, self.model_name)
            self.separator = StemSeparator(self.model_name)
            self._append_log(f"Switched model to: {self.model_name}")
            LOGGER.info("Model switched to %s", self.model_name)

        LOGGER.info("UI start processing source_kind=%s model=%s", source_kind, self.model_name)

        self.current_stems.clear()
        self._stop_preview(reset_controls=True)
        self._set_controls_busy(True)
        self.progress.setValue(0)
        self.progress_label.setText("Starting...")
        self._stop_separation_timer(reset=True)

        self.worker = ProcessingWorker(
            source_kind=source_kind,
            source_value=source_value,
            cache=self.cache,
            downloader=self.downloader,
            separator=self.separator,
            parent=self,
        )
        self.worker.progress.connect(self._on_progress)
        self.worker.done.connect(self._on_done)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _on_progress(self, message: str, fraction: float) -> None:
        value = max(0, min(100, int(fraction * 100)))
        self.progress.setValue(value)
        self.progress_label.setText(message)
        if self._is_separation_message(message) and not self.is_separating:
            self._start_separation_timer()
        self._append_log(f"{message} ({value}%)")

    def _on_done(self, payload: dict) -> None:
        self._set_controls_busy(False)
        self.progress.setValue(100)
        self.progress_label.setText("Ready")
        self._stop_separation_timer(reset=False)

        stems: Dict[str, Path] = {k: Path(v) for k, v in payload["stems"].items()}
        self.current_stems = stems

        for stem_name, checkbox in self.stem_checks.items():
            checkbox.setEnabled(stem_name in stems)
            checkbox.setChecked(stem_name in stems)

        self._configure_preview_players(stems)

        has_any_stem = bool(stems)
        self.play_pause_button.setEnabled(has_any_stem)
        self.preview_seek_slider.setEnabled(has_any_stem)
        self.preview_seek_slider.setRange(0, 0)
        self.preview_seek_slider.setValue(0)
        self.preview_time_label.setText("0:00 / 0:00")

        self.export_button.setEnabled(True)
        source = payload.get("source_file", "")
        if payload.get("from_cache"):
            self._append_log(f"Cache hit for source: {source}")
            LOGGER.info("UI processing completed from cache source=%s", source)
        else:
            self._append_log(f"Separated and cached source: {source}")
            LOGGER.info("UI processing completed with fresh separation source=%s", source)

    def _on_failed(self, message: str) -> None:
        self._stop_preview(reset_controls=False)
        self._set_controls_busy(False)
        self.progress_label.setText("Failed")
        self._stop_separation_timer(reset=False)
        self._show_error(message)
        self._append_log(f"Error: {message}")
        LOGGER.error("UI processing failed: %s", message)

    def _export_mix(self) -> None:
        selected = [name for name, cb in self.stem_checks.items() if cb.isChecked() and cb.isEnabled()]
        if not selected:
            self._show_error("Select at least one stem to export.")
            return

        default_file = self.paths.outputs_dir / "mixed_output.wav"
        output_file, _ = QFileDialog.getSaveFileName(
            self,
            "Save Mixed WAV",
            str(default_file),
            "WAV Files (*.wav)",
        )
        if not output_file:
            return

        out_path = Path(output_file)
        if out_path.suffix.lower() != ".wav":
            out_path = out_path.with_suffix(".wav")

        try:
            export_mix(self.current_stems, selected, out_path)
            self._append_log(f"Saved mix: {out_path}")
            LOGGER.info("Mix exported output=%s selected=%s", out_path, selected)
            QMessageBox.information(self, "Export Complete", f"Saved mixed track to:\n{out_path}")
        except MixError as exc:
            self._show_error(str(exc))
            LOGGER.error("Mix export failed: %s", exc)

    def _append_log(self, text: str) -> None:
        self.log_box.append(text)

    def _show_error(self, message: str) -> None:
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Icon.Critical)
        msg_box.setWindowTitle("MuseSplit")
        msg_box.setTextFormat(Qt.TextFormat.PlainText)
        msg_box.setText(message)
        msg_box.exec()

    def _set_controls_busy(self, busy: bool) -> None:
        self.process_button.setEnabled(not busy)
        self.url_edit.setEnabled(not busy)
        self.file_edit.setEnabled(not busy)
        self.model_combo.setEnabled(not busy)
        self.activity_title.setEnabled(not busy)
        self.preview_volume_slider.setEnabled(not busy)
        if busy:
            self.play_pause_button.setEnabled(False)
            self.preview_seek_slider.setEnabled(False)

    def _on_model_selected(self, _index: int) -> None:
        # Some desktop themes keep the popup open after click; force-close it.
        self.model_combo.hidePopup()
        self.model_combo.clearFocus()

    def _toggle_activity_panel(self) -> None:
        self._apply_activity_layout_state(expanded=not self.activity_expanded)

    def _apply_activity_layout_state(self, expanded: bool) -> None:
        self.activity_expanded = expanded
        self.log_box.setVisible(expanded)
        self.activity_title.setText("▼ Activity" if expanded else "▶ Activity")

        # On Wayland, changing top-level size constraints while maximized can
        # trigger xdg_surface buffer/configure mismatches. In maximized/fullscreen
        # mode, only toggle visibility and avoid height-constraint changes.
        if self.isMaximized() or self.isFullScreen():
            self.status_card.setMaximumHeight(16777215)
            self.input_card.setMaximumHeight(16777215)
            self.stems_card.setMaximumHeight(16777215)
            self.status_card.updateGeometry()
            central = self.centralWidget()
            if central is not None:
                central.updateGeometry()
            return

        if expanded:
            self.status_card.setMaximumHeight(16777215)
            self.input_card.setMaximumHeight(16777215)
            self.stems_card.setMaximumHeight(16777215)
        else:
            # Keep progress and status text visible but compact when activity is collapsed.
            self.status_card.setMaximumHeight(180)
            self.input_card.setMaximumHeight(290)
            self.stems_card.setMaximumHeight(380)

        self._adjust_window_height_to_content()

    def _adjust_window_height_to_content(self) -> None:
        central = self.centralWidget()
        if central is None:
            return

        # On Wayland, manually resizing a maximized/fullscreen surface can cause
        # a fatal protocol error (buffer size mismatch).
        if self.isMaximized() or self.isFullScreen():
            central.updateGeometry()
            return

        central.adjustSize()
        self.adjustSize()

        # Keep current width but fit height to visible content.
        target_height = max(420, self.sizeHint().height())
        self.resize(self.width(), target_height)

    def _configure_preview_players(self, stems: Dict[str, Path]) -> None:
        self._stop_preview(reset_controls=True)
        self.stem_players.clear()
        self.stem_outputs.clear()
        self.master_stem = None

        for stem_name, stem_path in stems.items():
            output = QAudioOutput(self)
            output.setVolume(0.9 if self.stem_checks[stem_name].isChecked() else 0.0)

            player = QMediaPlayer(self)
            player.setAudioOutput(output)
            player.setSource(QUrl.fromLocalFile(str(stem_path)))

            self.stem_outputs[stem_name] = output
            self.stem_players[stem_name] = player

        if self.stem_players:
            self.master_stem = next(iter(self.stem_players.keys()))
            master = self.stem_players[self.master_stem]
            master.positionChanged.connect(self._on_player_position_changed)
            master.durationChanged.connect(self._on_player_duration_changed)
            master.playbackStateChanged.connect(self._on_player_state_changed)
            LOGGER.info("Configured preview players stems=%s master=%s", list(self.stem_players.keys()), self.master_stem)

    def _toggle_playback(self) -> None:
        if not self.master_stem:
            return

        master = self.stem_players[self.master_stem]
        state = master.playbackState()
        if state == QMediaPlayer.PlaybackState.PlayingState:
            for player in self.stem_players.values():
                player.pause()
            LOGGER.info("Preview paused")
            return

        seek_target = int(self.preview_seek_slider.value())
        for player in self.stem_players.values():
            player.setPosition(seek_target)

        self._apply_stem_volumes()
        for player in self.stem_players.values():
            player.play()
        LOGGER.info("Preview playing from position_ms=%s", seek_target)

    def _on_stem_toggle(self, stem_name: str) -> None:
        self._apply_stem_volumes()
        LOGGER.info("Stem toggled stem=%s enabled=%s", stem_name, self.stem_checks[stem_name].isChecked())

    def _on_volume_changed(self, value: int) -> None:
        self.preview_volume_label.setText(f"{value}%")
        self._apply_stem_volumes()
        LOGGER.info("Preview volume changed value=%s", value)

    def _apply_stem_volumes(self) -> None:
        base_volume = float(self.preview_volume_slider.value()) / 100.0
        for stem_name, output in self.stem_outputs.items():
            output.setVolume(base_volume if self.stem_checks[stem_name].isChecked() else 0.0)

    def _on_player_position_changed(self, position_ms: int) -> None:
        if self.preview_is_seeking:
            return
        self.preview_seek_slider.setValue(max(0, position_ms))
        self.preview_time_label.setText(
            f"{self._format_ms(position_ms)} / {self._format_ms(self.preview_duration_ms)}"
        )

    def _on_player_duration_changed(self, duration_ms: int) -> None:
        self.preview_duration_ms = max(0, duration_ms)
        self.preview_seek_slider.setRange(0, self.preview_duration_ms)
        self.preview_time_label.setText(f"0:00 / {self._format_ms(self.preview_duration_ms)}")

    def _on_player_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.play_pause_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause))
        else:
            self.play_pause_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))

    def _on_seek_pressed(self) -> None:
        self.preview_is_seeking = True

    def _on_seek_released(self) -> None:
        self.preview_is_seeking = False
        target_ms = int(self.preview_seek_slider.value())
        for player in self.stem_players.values():
            player.setPosition(target_ms)
        self.preview_time_label.setText(
            f"{self._format_ms(target_ms)} / {self._format_ms(self.preview_duration_ms)}"
        )

    def _stop_preview(self, reset_controls: bool) -> None:
        for player in self.stem_players.values():
            player.stop()
        self.preview_duration_ms = 0
        self.preview_is_seeking = False
        if reset_controls:
            self.preview_seek_slider.setValue(0)
            self.preview_seek_slider.setRange(0, 0)
            self.preview_time_label.setText("0:00 / 0:00")
        self.play_pause_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))

    def _format_ms(self, value_ms: int) -> str:
        total_seconds = max(0, value_ms) // 1000
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes}:{seconds:02d}"

    def _is_separation_message(self, message: str) -> bool:
        lower = message.lower()
        return "running separation" in lower or "running demucs cli" in lower

    def _start_separation_timer(self) -> None:
        self.separation_start_time = time.monotonic()
        self.is_separating = True
        self.elapsed_label.setText("Separation elapsed: 0s")
        self.elapsed_timer.start()
        LOGGER.info("Separation timer started")

    def _stop_separation_timer(self, reset: bool) -> None:
        self.is_separating = False
        self.elapsed_timer.stop()
        if reset:
            self.separation_start_time = None
            self.elapsed_label.setText("Separation elapsed: 0s")
        elif self.separation_start_time is not None:
            elapsed = int(time.monotonic() - self.separation_start_time)
            self.elapsed_label.setText(f"Separation elapsed: {elapsed}s")
        LOGGER.info("Separation timer stopped")

    def _update_elapsed_label(self) -> None:
        if not self.is_separating or self.separation_start_time is None:
            return
        elapsed = int(time.monotonic() - self.separation_start_time)
        self.elapsed_label.setText(f"Separation elapsed: {elapsed}s")
