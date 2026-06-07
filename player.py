import sys
import numpy as np
import json
import os
import queue
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QFileDialog, QLabel, QListWidget, QListWidgetItem,
    QScrollArea, QSizePolicy, QStackedLayout, QGridLayout,
    QLineEdit, QMessageBox, QGraphicsDropShadowEffect, QSlider,
    QDialog, QFormLayout, QTextBrowser, QComboBox, QMenu, QInputDialog
)
from PySide6.QtCore import QTimer, Qt, QPropertyAnimation, QEasingCurve, QSize, Signal, QUrl
from PySide6.QtGui import QPalette, QBrush, QLinearGradient, QColor, QPainter, QIcon, QPen, QFont, QPixmap, QCursor, QDesktopServices
from PySide6.QtSvg import QSvgRenderer
from backends.sd_ffmpeg_provider import AudioPlayer
from backends.bilibili_downloader import BilibiliDownloader
from backends.spectrum_processor import SpectrumProcessor
import time

from utils import (
    Config, ASSETS_PATH, CONFIG_PATH,
    PlaylistManager, SpectrumWidget, GradientWidget,
    CircularProgressBar, VolumeSlider, AddMusicDialog,
    SettingsDialog, EqualizerDialog, CollapsiblePlaylist,
    create_icon, format_time, get_icon_path
)


class PlayerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = Config()
        self.progress_bar = CircularProgressBar()
        self.setWindowTitle(self.config.WINDOW_TITLE)
        self._apply_adaptive_window_size()

        self.play_modes = ["sequence", "random", "single"]
        self.play_mode_icons = [
            create_icon(get_icon_path("repeat.svg")),
            create_icon(get_icon_path("shuffle.svg")),
            create_icon(get_icon_path("repeat-one.svg"))
        ]
        self.current_play_mode_index = 0
        self.play_mode = self.play_modes[self.current_play_mode_index]
        self.playlist_history = []
        self.current_index = -1
        self.is_playing = False

        self.load_settings_data()

        self.playlist_manager = PlaylistManager(CONFIG_PATH)

        self.setup_ui()
        self.setup_audio()

        self.audio_queue = queue.Queue(maxsize=10)
        self.spectrum_processor = SpectrumProcessor(self.config, self.audio_queue)
        self.spectrum_processor.start()
        self.performance_mode_enabled = False

        download_path = self.settings.get("download_path", Config.DEFAULT_DOWNLOAD_PATH)
        proxy = self.settings.get("proxy", "")
        self.bilibili_downloader = BilibiliDownloader(download_path, proxy)

        self.apply_settings_to_ui()

        self.restore_last_played_track()

    def _apply_adaptive_window_size(self):
        default_width, default_height = self.config.WINDOW_SIZE
        screen = QApplication.primaryScreen()
        if not screen:
            self.setMinimumSize(720, 480)
            self.resize(default_width, default_height)
            return

        available = screen.availableGeometry()
        max_width = max(1, int(available.width() * 0.9))
        max_height = max(1, int(available.height() * 0.9))
        min_width = min(720, max_width)
        min_height = min(480, max_height)
        initial_width = min(max(default_width, int(available.width() * 0.55)), max_width)
        initial_height = min(max(default_height, int(available.height() * 0.65)), max_height)

        self.setMinimumSize(min_width, min_height)
        self.resize(initial_width, initial_height)

    def setup_ui(self):
        font = QFont("微软雅黑", 11)
        self.setFont(font)
        main_widget = QWidget()
        self.setCentralWidget(main_widget)

        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.bg_widget = GradientWidget()
        self.bg_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        main_layout.addWidget(self.bg_widget)

        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(20, 20, 20, 20)

        control_panel = QWidget()
        control_layout = QVBoxLayout(control_panel)
        control_layout.setSpacing(6)
        control_panel.setObjectName("ControlPanel")
        self.playlist = CollapsiblePlaylist(self, self.playlist_manager)
        self.playlist.play_signal.connect(self.play_file)
        self.playlist.performance_mode_toggled.connect(self.toggle_performance_mode)
        self.playlist.add_music_requested.connect(self.open_add_music_dialog)
        self.playlist.add_to_next_play_requested.connect(self.add_to_next_play)
        self.playlist.settings_btn.clicked.connect(self.open_settings)
        self.playlist.equalizer_btn.clicked.connect(self.open_equalizer)
        self.playlist.playlist_widget.itemSelectionChanged.connect(self.on_playlist_selection_changed)
        self.playlist.locate_current_song_requested.connect(self.locate_current_song)
        control_layout.addWidget(self.playlist)

        content_layout.addWidget(control_panel, 1)

        right_panel = QWidget()
        right_panel_layout = QVBoxLayout(right_panel)
        right_panel_layout.setContentsMargins(0, 0, 0, 0)
        right_panel_layout.setSpacing(15)

        spectrum_main_container = QWidget()
        self.spectrum_main_container = spectrum_main_container
        spectrum_main_container.setMinimumSize(280, 280)
        spectrum_main_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        spectrum_main_layout = QGridLayout(spectrum_main_container)
        spectrum_main_layout.setContentsMargins(0, 0, 0, 0)

        self.spectrum = SpectrumWidget(self.config)
        spectrum_main_layout.addWidget(self.spectrum, 0, 0)

        progress_overlay = QWidget()
        progress_overlay.setObjectName("ProgressOverlay")
        progress_overlay.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        progress_layout = QVBoxLayout(progress_overlay)
        progress_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        progress_layout.addWidget(self.progress_bar)
        spectrum_main_layout.addWidget(progress_overlay, 0, 0)

        self.play_pause_btn = QPushButton()
        self.play_pause_btn.setObjectName("PlayPauseButton")
        self.play_pause_btn.setToolTip("播放/暂停")
        self.play_pause_btn.clicked.connect(self.toggle_play)

        self.prev_btn = QPushButton()
        self.prev_btn.setIcon(create_icon(get_icon_path("prev.svg")))
        self.prev_btn.setObjectName("PrevButton")
        self.prev_btn.setToolTip("上一首")
        self.prev_btn.clicked.connect(self.play_previous)

        self.next_btn = QPushButton()
        self.next_btn.setIcon(create_icon(get_icon_path("next.svg")))
        self.next_btn.setObjectName("NextButton")
        self.next_btn.setToolTip("下一首")
        self.next_btn.clicked.connect(self.play_next)

        self.stop_btn = QPushButton()
        self.stop_btn.setIcon(create_icon(get_icon_path("stop.svg")))
        self.stop_btn.setObjectName("StopButton")
        self.stop_btn.setToolTip("停止")
        self.stop_btn.clicked.connect(self.stop)

        self.play_mode_btn = QPushButton()
        self.play_mode_btn.setIcon(self.play_mode_icons[self.current_play_mode_index])
        self.play_mode_btn.setObjectName("PlayModeButton")
        self.play_mode_btn.setToolTip("切换播放模式（顺序/随机/单曲循环）")
        self.play_mode_btn.clicked.connect(self.toggle_play_mode)

        self.update_play_pause_icon()

        self.control_buttons = [self.play_pause_btn, self.prev_btn, self.next_btn, self.stop_btn, self.play_mode_btn]
        for btn in self.control_buttons:
            self.set_button_style(btn, size=self.config.CONTROL_BUTTON_SIZE)
            btn.setIconSize(QSize(self.config.CONTROL_BUTTON_ICON_SIZE, self.config.CONTROL_BUTTON_ICON_SIZE))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)

        buttons_overlay = QWidget()
        buttons_overlay.setObjectName("ButtonsOverlay")
        buttons_overlay.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        grid_layout = QGridLayout(buttons_overlay)
        self.buttons_grid_layout = grid_layout
        grid_layout.setSpacing(15)

        grid_layout.addWidget(self.play_mode_btn, 0, 1, Qt.AlignmentFlag.AlignCenter)
        grid_layout.addWidget(self.prev_btn, 1, 0, Qt.AlignmentFlag.AlignCenter)
        grid_layout.addWidget(self.play_pause_btn, 1, 1, Qt.AlignmentFlag.AlignCenter)
        grid_layout.addWidget(self.next_btn, 1, 2, Qt.AlignmentFlag.AlignCenter)
        grid_layout.addWidget(self.stop_btn, 2, 1, Qt.AlignmentFlag.AlignCenter)

        spectrum_main_layout.addWidget(buttons_overlay, 0, 0, Qt.AlignmentFlag.AlignCenter)

        right_panel_layout.addWidget(spectrum_main_container, 1)

        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setObjectName("TimeLabel")
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_panel_layout.addWidget(self.time_label, 0, Qt.AlignmentFlag.AlignCenter)

        self.volume_slider = VolumeSlider()
        self.volume_slider.valueChanged.connect(self.set_volume)

        self.volume_container = QWidget()
        volume_container_layout = QHBoxLayout(self.volume_container)
        volume_container_layout.setContentsMargins(0, 0, 0, 5)
        volume_container_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        volume_container_layout.addWidget(self.volume_slider)
        self.volume_container.setFixedSize(150, 30)

        right_panel_layout.addWidget(self.volume_container, 0, Qt.AlignmentFlag.AlignCenter)

        self.volume_slider.setVisible(False)
        self.volume_container.installEventFilter(self)

        content_layout.addWidget(right_panel, 2)

        self.bg_widget.setLayout(content_layout)

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_spectrum)
        self.timer.start(self.config.UI_UPDATE_INTERVAL_MS)

        self.bg_timer = QTimer()
        self.bg_timer.timeout.connect(self.update_background)
        self.bg_phase = 0
        self.bg_timer.start(100)

        self.stop_btn.setEnabled(False)

        self.progress_bar.seek_requested.connect(self.seek_playback)

    def showEvent(self, event):
        super().showEvent(event)
        self._update_responsive_overlay_sizes()

    def set_button_style(self, btn, size=40):
        btn.setFixedSize(size, size)
        self._apply_round_button_style(btn, size)

    def _apply_round_button_style(self, btn, size):
        radius = max(1, size // 2)
        btn.setStyleSheet(f"border-radius: {radius}px;")

    def _update_responsive_overlay_sizes(self):
        if not hasattr(self, 'spectrum_main_container'):
            return

        base_size = 500
        available_size = min(self.spectrum_main_container.width(), self.spectrum_main_container.height())
        if available_size <= 0:
            return

        scale = max(0.65, min(2.0, available_size / base_size))
        progress_size = max(150, int(Config.PROGRESS_BAR_RADIUS * 2 * scale))
        button_size = max(28, int(self.config.CONTROL_BUTTON_SIZE * scale))
        icon_size = max(20, int(self.config.CONTROL_BUTTON_ICON_SIZE * scale))
        spacing = max(8, int(15 * scale))

        self.progress_bar.setFixedSize(progress_size, progress_size)
        for btn in getattr(self, 'control_buttons', []):
            btn.setFixedSize(button_size, button_size)
            btn.setIconSize(QSize(icon_size, icon_size))
            self._apply_round_button_style(btn, button_size)

        if hasattr(self, 'buttons_grid_layout'):
            self.buttons_grid_layout.setSpacing(spacing)

    def update_background(self):
        self.bg_phase = (self.bg_phase + 0.01) % (2 * np.pi)
        self.bg_widget.bg_phase = self.bg_phase

    def setup_audio(self):
        self.player = None
        self.current_file = None
        self.start_time = time.time()

    def load_file(self, file_path):
        self.current_file = file_path
        self.stop_btn.setEnabled(True)
        if self.player:
            self.player.stop()
            self.player = None
        self.player = AudioPlayer(self.current_file)
        self._apply_volume_for_file(self.current_file)
        self.player.play()
        self.stop_btn.setText("停止")
        self.is_playing = True
        self.update_play_pause_icon()
        self.spectrum.update_spectrum(np.zeros(self.config.NUM_BARS), self.start_time)
        self.time_label.setText("00:00 / 00:00")

    def play_file(self, file_path):
        if self.player:
            self.player.stop()
        self.player = AudioPlayer(file_path)
        self.current_file = file_path
        self._apply_volume_for_file(file_path)
        self.player.play()
        self.is_playing = True
        self.update_play_pause_icon()
        self.stop_btn.setEnabled(True)
        self.spectrum.update_spectrum(np.zeros(self.config.NUM_BARS), self.start_time)

        for i in range(self.playlist.playlist_widget.count()):
            item = self.playlist.playlist_widget.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == file_path:
                self.current_index = i
                self.playlist.playlist_widget.setCurrentRow(i)
                break

        self.player.playback_finished.connect(self.on_playback_finished)
        self.settings["last_played_file"] = file_path
        self.save_settings()

    def add_to_next_play(self, file_path):
        if self.playlist_manager:
            self.playlist_manager.add_to_next_play(file_path)
            QMessageBox.information(self, "提示", f"已添加到下一首播放队列")

    def on_playback_finished(self):
        if self.play_mode == "single":
            if self.current_file:
                self.play_file(self.current_file)
        else:
            self.play_next()

    def toggle_play(self):
        selected_items = self.playlist.playlist_widget.selectedItems()
        if selected_items:
            file_path = selected_items[0].data(Qt.ItemDataRole.UserRole)
            if file_path != self.current_file:
                self.play_file(file_path)
                return
        if not self.player:
            return
        if self.is_playing:
            self.player.pause()
            self.is_playing = False
        else:
            self.player.resume()
            self.is_playing = True
        self.update_play_pause_icon()

    def stop(self):
        if self.player:
            self.player.stop()
            self.is_playing = False
        self.update_play_pause_icon()
        self.time_label.setText("00:00 / 00:00")

    def update_spectrum(self):
        if self.player:
            try:
                pos = self.player.get_position()
                dur = self.player.get_duration()
                progress = pos / dur if dur > 0 else 0
                self.progress_bar.set_progress(progress)

                self.time_label.setText(f"{format_time(pos)} / {format_time(dur)}")

            except Exception:
                self.progress_bar.set_progress(0)
                self.time_label.setText("00:00 / 00:00")

            if self.is_playing and not self.performance_mode_enabled:
                audio_data = self.player.get_audio_data()
                if audio_data is not None:
                    data = audio_data[:, 0] if audio_data.ndim > 1 else audio_data
                    try:
                        self.audio_queue.put(data, block=False)
                    except queue.Full:
                        pass
                try:
                    display_heights = self.spectrum_processor.get_processed_data_queue().get_nowait()
                    self.spectrum.update_spectrum(display_heights, self.start_time)
                except queue.Empty:
                    pass
            elif not self.performance_mode_enabled:
                try:
                    display_heights = self.spectrum_processor.get_processed_data_queue().get_nowait()
                    self.spectrum.update_spectrum(display_heights, self.start_time)
                except queue.Empty:
                    pass
        else:
            self.progress_bar.set_progress(0)
            if not self.performance_mode_enabled:
                try:
                    display_heights = self.spectrum_processor.get_processed_data_queue().get_nowait()
                    self.spectrum.update_spectrum(display_heights, self.start_time)
                except queue.Empty:
                    pass
            self.time_label.setText("00:00 / 00:00")

    def closeEvent(self, event):
        self.save_settings()
        if self.player:
            self.player.stop()
        if hasattr(self, 'spectrum_processor'):
            self.spectrum_processor.stop()
        event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'bg_widget'):
            self.bg_widget.setGeometry(self.rect())
        self._update_responsive_overlay_sizes()

    def open_add_music_dialog(self):
        dialog = AddMusicDialog(self, self.bilibili_downloader)
        dialog.file_added.connect(self.playlist.add_item)
        dialog.exec()

    def toggle_play_mode(self):
        self.current_play_mode_index = (self.current_play_mode_index + 1) % len(self.play_modes)
        self.play_mode = self.play_modes[self.current_play_mode_index]
        self.play_mode_btn.setIcon(self.play_mode_icons[self.current_play_mode_index])
        self.settings["play_mode"] = self.play_mode
        self.save_settings()

    def set_play_mode(self, mode):
        try:
            idx = self.play_modes.index(mode)
            self.current_play_mode_index = idx
            self.play_mode = mode
            self.play_mode_btn.setIcon(self.play_mode_icons[idx])
        except ValueError:
            print(f"警告: 未知的播放模式 '{mode}'")

    def play_next(self):
        if self.playlist_manager:
            next_file = self.playlist_manager.get_next_from_queue()
            if next_file and os.path.exists(next_file):
                self.play_file(next_file)
                return

        if not self.playlist.playlist_widget.count():
            return

        if self.play_mode == "random":
            import random
            count = self.playlist.playlist_widget.count()
            if count > 1:
                next_index = self.current_index
                while next_index == self.current_index:
                    next_index = random.randint(0, count - 1)
                self.current_index = next_index
            else:
                self.current_index = 0
        else:
            self.current_index = (self.current_index + 1) % self.playlist.playlist_widget.count()

        item = self.playlist.playlist_widget.item(self.current_index)
        if item:
            file_path = item.data(Qt.ItemDataRole.UserRole)
            self.play_file(file_path)
            self.playlist.playlist_widget.setCurrentRow(self.current_index)

    def play_previous(self):
        if not self.playlist.playlist_widget.count():
            return

        if self.play_mode == "random":
            import random
            count = self.playlist.playlist_widget.count()
            if count > 1:
                prev_index = self.current_index
                while prev_index == self.current_index:
                    prev_index = random.randint(0, count - 1)
                self.current_index = prev_index
            else:
                self.current_index = 0
        else:
            self.current_index = (self.current_index - 1) % self.playlist.playlist_widget.count()

        item = self.playlist.playlist_widget.item(self.current_index)
        if item:
            file_path = item.data(Qt.ItemDataRole.UserRole)
            self.play_file(file_path)
            self.playlist.playlist_widget.setCurrentRow(self.current_index)

    def seek_playback(self, progress):
        if self.player and self.player.get_duration() > 0:
            duration = self.player.get_duration()
            new_position = duration * progress

            self.player.seek(new_position)
            self.is_playing = True
            self.update_play_pause_icon()

    def toggle_performance_mode(self, checked):
        self.performance_mode_enabled = checked
        self.spectrum.setVisible(not checked)

    def eventFilter(self, source, event):
        if source == self.volume_container:
            if event.type() == event.Type.Enter:
                self.volume_slider.setVisible(True)
            elif event.type() == event.Type.Leave:
                if not self.volume_container.geometry().contains(self.volume_container.mapFromGlobal(QCursor.pos())):
                    self.volume_slider.setVisible(False)
            return True
        return super().eventFilter(source, event)

    def set_volume(self, value):
        if self.player:
            self.player.set_volume(value / 100.0)
        if hasattr(self, "settings"):
            if getattr(self, "_applying_remembered_volume", False):
                return

            default_volume = self._get_default_volume()
            if self.current_file:
                track_volumes = self._get_track_volumes()
                if value == default_volume:
                    track_volumes.pop(self.current_file, None)
                else:
                    track_volumes[self.current_file] = value
            else:
                self.settings["volume"] = value
            self.save_settings()

    def _get_default_volume(self):
        volume = self.settings.get("volume", 100)
        if not isinstance(volume, int):
            return 100
        return max(0, min(100, volume))

    def _get_track_volumes(self):
        track_volumes = self.settings.setdefault("track_volumes", {})
        if not isinstance(track_volumes, dict):
            track_volumes = {}
            self.settings["track_volumes"] = track_volumes
        return track_volumes

    def _get_volume_for_file(self, file_path):
        default_volume = self._get_default_volume()
        track_volume = self._get_track_volumes().get(file_path, default_volume)
        if not isinstance(track_volume, int):
            return default_volume
        return max(0, min(100, track_volume))

    def _apply_volume_for_file(self, file_path):
        volume = self._get_volume_for_file(file_path)
        self._applying_remembered_volume = True
        try:
            self.volume_slider.setValue(volume)
        finally:
            self._applying_remembered_volume = False
        if self.player:
            self.player.set_volume(volume / 100.0)

    def load_settings_data(self):
        try:
            if os.path.exists(self.config.SETTINGS_FILE):
                with open(self.config.SETTINGS_FILE, 'r') as f:
                    self.settings = json.load(f)
            else:
                self.settings = {
                    "volume": 100,
                    "play_mode": "sequence",
                    "last_played_file": "",
                    "download_path": Config.DEFAULT_DOWNLOAD_PATH,
                    "proxy": ""
                }
        except (json.JSONDecodeError, FileNotFoundError):
            self.settings = {
                "volume": 100,
                "play_mode": "sequence",
                "last_played_file": "",
                "download_path": Config.DEFAULT_DOWNLOAD_PATH,
                "proxy": ""
            }

        download_path = self.settings.get("download_path", Config.DEFAULT_DOWNLOAD_PATH)
        if not os.path.exists(download_path):
            try:
                os.makedirs(download_path)
            except OSError:
                self.settings["download_path"] = Config.DEFAULT_DOWNLOAD_PATH
                if not os.path.exists(Config.DEFAULT_DOWNLOAD_PATH):
                    os.makedirs(Config.DEFAULT_DOWNLOAD_PATH)

    def apply_settings_to_ui(self):
        if hasattr(self, 'volume_slider'):
            self.volume_slider.setValue(self.settings.get("volume", 100))
        self.set_play_mode(self.settings.get("play_mode", "sequence"))

    def save_settings(self):
        try:
            with open(self.config.SETTINGS_FILE, 'w') as f:
                json.dump(self.settings, f, indent=4)
        except IOError as e:
            print(f"无法保存设置: {e}")

    def restore_last_played_track(self):
        last_file = self.settings.get("last_played_file")
        if not last_file:
            return

        for i in range(self.playlist.playlist_widget.count()):
            item = self.playlist.playlist_widget.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == last_file:
                self.current_index = i
                self.playlist.playlist_widget.setCurrentRow(i)
                break

    def on_playlist_selection_changed(self):
        self.update_play_pause_icon()

    def update_play_pause_icon(self):
        selected_items = self.playlist.playlist_widget.selectedItems()
        if selected_items:
            selected_file = selected_items[0].data(Qt.ItemDataRole.UserRole)
            if self.is_playing and selected_file == self.current_file:
                self.play_pause_btn.setIcon(create_icon(get_icon_path("pause.svg")))
            else:
                self.play_pause_btn.setIcon(create_icon(get_icon_path("play.svg")))
        else:
            if self.is_playing:
                self.play_pause_btn.setIcon(create_icon(get_icon_path("pause.svg")))
            else:
                self.play_pause_btn.setIcon(create_icon(get_icon_path("play.svg")))

    def open_settings(self):
        dialog = SettingsDialog(self, self.settings.copy())
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_settings = dialog.get_settings()
            self.settings.update(new_settings)
            self.save_settings()

            download_path = self.settings.get("download_path", Config.DEFAULT_DOWNLOAD_PATH)
            if not os.path.exists(download_path):
                try:
                    os.makedirs(download_path)
                except OSError as e:
                    QMessageBox.warning(self, "警告", f"无法创建下载目录: {e}")

            if hasattr(self, 'bilibili_downloader'):
                self.bilibili_downloader.set_download_path(download_path)
                proxy = self.settings.get("proxy", "")
                self.bilibili_downloader.set_proxy(proxy)

    def open_equalizer(self):
        dialog = EqualizerDialog(self, self.settings.copy())
        dialog.equalizer_changed.connect(self.on_equalizer_changed)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_settings = dialog.get_settings()
            self.settings.update(new_settings)
            self.save_settings()

    def on_equalizer_changed(self, eq_values):
        print(f"均衡器值更新: {eq_values}")
        if hasattr(self, 'player') and self.player:
            pass

    def locate_current_song(self):
        if hasattr(self, 'playlist') and self.current_file:
            self.playlist.locate_current_song(self.current_file)
        else:
            QMessageBox.information(self, "提示", "当前没有播放歌曲")

def main():
    app = QApplication(sys.argv)

    stylesheet_path = os.path.join(ASSETS_PATH, "stylesheet.qss")
    try:
        with open(stylesheet_path, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())
    except FileNotFoundError:
        print(f"警告: {stylesheet_path} 未找到，将使用默认样式。")

    window = PlayerWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
