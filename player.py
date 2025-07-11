import sys
import numpy as np
import pyqtgraph as pg
import json
import os
import queue
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QFileDialog, QLabel, QListWidget, QListWidgetItem,
    QScrollArea, QFrame, QSizePolicy, QStackedLayout, QGridLayout,
    QLineEdit, QMessageBox, QGraphicsDropShadowEffect, QSlider,
    QDialog, QFormLayout, QTextBrowser, QComboBox, QMenu, QInputDialog
)
from PyQt6.QtCore import QTimer, Qt, QPropertyAnimation, QEasingCurve, QSize, pyqtSignal, QUrl
from PyQt6.QtGui import QPalette, QBrush, QLinearGradient, QColor, QPainter, QIcon, QPen, QFont, QPixmap, QCursor, QDesktopServices
from PyQt6.QtSvg import QSvgRenderer
from backends.sd_ffmpeg_provider import AudioPlayer
from backends.bilibili_downloader import BilibiliDownloader
from backends.spectrum_processor import SpectrumProcessor
import time

# 导入拆分的组件
from utils import (
    Config, ASSETS_PATH, CONFIG_PATH,
    PlaylistManager, SpectrumWidget, GradientWidget,
    CircularProgressBar, VolumeSlider, AddMusicDialog,
    SettingsDialog, CollapsiblePlaylist,
    create_icon, format_time, get_icon_path
)


class PlayerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = Config()
        self.progress_bar = CircularProgressBar()  # 必须在setup_ui之前
        self.setWindowTitle(self.config.WINDOW_TITLE)
        self.resize(*self.config.WINDOW_SIZE)
        self.setFixedSize(*self.config.WINDOW_SIZE)
        
        # 添加播放模式相关属性
        self.play_modes = ["sequence", "random", "single"]
        self.play_mode_icons = [
            create_icon(get_icon_path("repeat.svg")), 
            create_icon(get_icon_path("shuffle.svg")), 
            create_icon(get_icon_path("repeat-one.svg"))
        ]
        self.current_play_mode_index = 0
        self.play_mode = self.play_modes[self.current_play_mode_index]
        self.playlist_history = []  # 用于随机播放时记录历史
        self.current_index = -1  # 当前播放的索引
        self.is_playing = False # 在setup_ui之前初始化状态

        # 先只加载设置数据，不应用到UI控件
        self.load_settings_data()
        
        # 初始化播放列表管理器（必须在setup_ui之前）
        self.playlist_manager = PlaylistManager(CONFIG_PATH)

        self.setup_ui()
        self.setup_audio()
        
        # 创建音频数据队列和频谱处理器
        self.audio_queue = queue.Queue(maxsize=10)
        self.spectrum_processor = SpectrumProcessor(self.config, self.audio_queue)
        self.spectrum_processor.start()
        self.performance_mode_enabled = False
        
        # 初始化BilibiliDownloader（在加载设置之后）
        download_path = self.settings.get("download_path", Config.DEFAULT_DOWNLOAD_PATH)
        proxy = self.settings.get("proxy", "")
        self.bilibili_downloader = BilibiliDownloader(download_path, proxy)
        
        # UI创建完成后，应用设置到UI控件
        self.apply_settings_to_ui()
        
        # 根据设置恢复播放列表选中项
        self.restore_last_played_track()

    def setup_ui(self):
        # 全局字体美化
        font = QFont("微软雅黑", 11)
        self.setFont(font)
        # 创建主窗口部件
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        
        # 创建主布局
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 创建背景渐变部件
        self.bg_widget = GradientWidget()
        self.bg_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        main_layout.addWidget(self.bg_widget)
        
        # 创建内容布局
        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(20, 20, 20, 20)
        
        # 创建左侧控制面板 (播放列表)
        control_panel = QWidget()
        control_layout = QVBoxLayout(control_panel)
        control_layout.setSpacing(6)
        control_panel.setObjectName("ControlPanel")
        self.playlist = CollapsiblePlaylist(self, self.playlist_manager)
        self.playlist.play_signal.connect(self.play_file)
        self.playlist.performance_mode_toggled.connect(self.toggle_performance_mode)
        self.playlist.add_music_requested.connect(self.open_add_music_dialog)
        self.playlist.add_to_next_play_requested.connect(self.add_to_next_play)
        # 连接设置按钮信号
        self.playlist.settings_btn.clicked.connect(self.open_settings)
        # 连接播放列表选择变化信号
        self.playlist.playlist_widget.itemSelectionChanged.connect(self.on_playlist_selection_changed)
        # 连接定位当前歌曲信号
        self.playlist.locate_current_song_requested.connect(self.locate_current_song)
        control_layout.addWidget(self.playlist)
        
        content_layout.addWidget(control_panel)
        
        # --- 右侧面板 ---
        right_panel = QWidget()
        right_panel_layout = QVBoxLayout(right_panel)
        right_panel_layout.setContentsMargins(0, 0, 0, 0)
        right_panel_layout.setSpacing(15) # 频谱与时间标签的间距

        # 创建频谱和按钮的容器 (右侧)
        spectrum_main_container = QWidget()
        # **关键修复**: 设置一个固定的尺寸来防止频谱图随窗口缩放
        # 这个尺寸应略大于频谱图的直径 (即 (INNER_RADIUS + MAX_AMPLITUDE_RADIUS) * 2)
        # 以提供一些边距
        spectrum_main_container.setFixedSize(500, 500)
        
        spectrum_main_layout = QGridLayout(spectrum_main_container)
        spectrum_main_layout.setContentsMargins(0, 0, 0, 0)

        # 频谱部件
        self.spectrum = SpectrumWidget(self.config)
        spectrum_main_layout.addWidget(self.spectrum, 0, 0)

        # 进度条覆盖层
        progress_overlay = QWidget()
        progress_overlay.setObjectName("ProgressOverlay")
        progress_layout = QVBoxLayout(progress_overlay)
        progress_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        progress_layout.addWidget(self.progress_bar)
        spectrum_main_layout.addWidget(progress_overlay, 0, 0)
        
        # --- 按钮 ---
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

        # 初始设置播放/暂停按钮图标
        self.update_play_pause_icon()

        # **关键修复**: 统一所有按钮的尺寸和样式
        buttons = [self.play_pause_btn, self.prev_btn, self.next_btn, self.stop_btn, self.play_mode_btn]
        for btn in buttons:
            self.set_button_style(btn, size=self.config.CONTROL_BUTTON_SIZE)
            btn.setIconSize(QSize(self.config.CONTROL_BUTTON_ICON_SIZE, self.config.CONTROL_BUTTON_ICON_SIZE))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)

        # --- 按钮布局 (十字形) ---
        buttons_overlay = QWidget()
        buttons_overlay.setObjectName("ButtonsOverlay")
        grid_layout = QGridLayout(buttons_overlay)
        grid_layout.setSpacing(15) # 设置按钮间的间距

        # 第0行: (空白), 播放模式, (空白)
        grid_layout.addWidget(self.play_mode_btn, 0, 1, Qt.AlignmentFlag.AlignCenter)
        # 第1行: 上一首, 播放/暂停, 下一曲
        grid_layout.addWidget(self.prev_btn, 1, 0, Qt.AlignmentFlag.AlignCenter)
        grid_layout.addWidget(self.play_pause_btn, 1, 1, Qt.AlignmentFlag.AlignCenter)
        grid_layout.addWidget(self.next_btn, 1, 2, Qt.AlignmentFlag.AlignCenter)
        # 第2行: (空白), 停止, (空白)
        grid_layout.addWidget(self.stop_btn, 2, 1, Qt.AlignmentFlag.AlignCenter)

        # **关键修复**: 将只包含按钮的、尺寸自适应的overlay居中放置在顶层
        # 这样它就不会拦截到旁边进度条的点击事件
        spectrum_main_layout.addWidget(buttons_overlay, 0, 0, Qt.AlignmentFlag.AlignCenter)

        right_panel_layout.addWidget(spectrum_main_container)

        # 时间显示标签 - 移到频谱下方
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setObjectName("TimeLabel")
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_panel_layout.addWidget(self.time_label, 0, Qt.AlignmentFlag.AlignCenter)

        # --- 音量条容器 (重构) ---
        # 1. 创建音量条
        self.volume_slider = VolumeSlider()
        self.volume_slider.valueChanged.connect(self.set_volume)
        
        # 2. 创建一个容器来放置音量条，并将其提升为实例变量
        self.volume_container = QWidget()
        volume_container_layout = QHBoxLayout(self.volume_container)
        volume_container_layout.setContentsMargins(0, 0, 0, 5) # 调高位置，减少顶部边距
        volume_container_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        volume_container_layout.addWidget(self.volume_slider)
        # 为容器设置固定大小，创建有效的悬停区域
        self.volume_container.setFixedSize(150, 30)
        
        # 3. 将音量容器添加到右侧面板
        right_panel_layout.addWidget(self.volume_container, 0, Qt.AlignmentFlag.AlignCenter)

        # 恢复悬停显示/隐藏功能
        self.volume_slider.setVisible(False)
        # 仅在容器上安装事件过滤器
        self.volume_container.installEventFilter(self)
        
        content_layout.addWidget(right_panel)
        
        self.bg_widget.setLayout(content_layout)

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_spectrum)
        self.timer.start(self.config.UI_UPDATE_INTERVAL_MS)

        self.bg_timer = QTimer()
        self.bg_timer.timeout.connect(self.update_background)
        self.bg_phase = 0
        self.bg_timer.start(100)

        self.stop_btn.setEnabled(False)

        # 连接进度条跳转信号
        self.progress_bar.seek_requested.connect(self.seek_playback)

    def set_button_style(self, btn, size=40):
        btn.setFixedSize(size, size)
        # 样式现在完全由QSS文件控制

    def update_background(self):
        self.bg_phase = (self.bg_phase + 0.01) % (2 * np.pi)
        self.bg_widget.bg_phase = self.bg_phase

    def setup_audio(self):
        """初始化音频播放器"""
        self.player = None
        self.current_file = None
        self.start_time = time.time()

    def load_file(self, file_path):
        self.current_file = file_path
        # self.status_label.setText(f"已加载: {os.path.basename(file_path)}")
        self.stop_btn.setEnabled(True)
        if self.player:
            self.player.stop()
            self.player = None
        self.player = AudioPlayer(self.current_file)
        self.player.play()
        self.stop_btn.setText("停止")
        self.is_playing = True
        self.update_play_pause_icon()
        # 清空频谱
        self.spectrum.update_spectrum(np.zeros(self.config.NUM_BARS), self.start_time)
        self.time_label.setText("00:00 / 00:00")

    def play_file(self, file_path):
        """播放指定文件，并持久化最后播放曲目"""
        if self.player:
            self.player.stop()
        self.player = AudioPlayer(file_path)
        # 同步音量到新的播放器实例
        self.player.set_volume(self.volume_slider.value() / 100.0)
        self.current_file = file_path
        self.player.play()
        self.is_playing = True
        self.update_play_pause_icon()
        self.stop_btn.setEnabled(True)
        # 清空频谱
        self.spectrum.update_spectrum(np.zeros(self.config.NUM_BARS), self.start_time)
        
        # 更新当前索引并选中对应的播放列表项
        for i in range(self.playlist.playlist_widget.count()):
            item = self.playlist.playlist_widget.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == file_path:
                self.current_index = i
                self.playlist.playlist_widget.setCurrentRow(i)
                break
                
        # 连接播放结束信号
        self.player.playback_finished.connect(self.on_playback_finished)
        # 记录并保存最后播放文件
        self.settings["last_played_file"] = file_path
        self.save_settings()

    def add_to_next_play(self, file_path):
        """添加到下一首播放队列"""
        if self.playlist_manager:
            self.playlist_manager.add_to_next_play(file_path)
            QMessageBox.information(self, "提示", f"已添加到下一首播放队列")

    def on_playback_finished(self):
        """处理播放结束事件"""
        if self.play_mode == "single":
            # 单曲循环模式，重新播放当前歌曲
            if self.current_file:
                self.play_file(self.current_file)
        else:
            # 其他模式，播放下一首
            self.play_next()

    def toggle_play(self):
        # 如果有选中项且不是当前播放曲目，则切换到该曲目并播放
        selected_items = self.playlist.playlist_widget.selectedItems()
        if selected_items:
            file_path = selected_items[0].data(Qt.ItemDataRole.UserRole)
            if file_path != self.current_file:
                self.play_file(file_path)
                return
        # 否则继续/暂停当前曲目
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
        # 不再直接清空频谱，让spectrum_processor自然处理渐变下降

    def update_spectrum(self):
        if self.player:
            # --- 进度条与时间更新 (播放和暂停状态都更新) ---
            try:
                pos = self.player.get_position()
                dur = self.player.get_duration()
                progress = pos / dur if dur > 0 else 0
                self.progress_bar.set_progress(progress)
                
                # 更新时间显示
                self.time_label.setText(f"{format_time(pos)} / {format_time(dur)}")

            except Exception:
                self.progress_bar.set_progress(0)
                self.time_label.setText("00:00 / 00:00")

            # --- 频谱更新 (仅在播放时) ---
            if self.is_playing and not self.performance_mode_enabled:
                audio_data = self.player.get_audio_data()
                if audio_data is not None:
                    data = audio_data[:, 0] if audio_data.ndim > 1 else audio_data
                    try:
                        self.audio_queue.put(data, block=False)
                    except queue.Full:
                        pass
                # 从处理器获取处理后的数据
                try:
                    display_heights = self.spectrum_processor.get_processed_data_queue().get_nowait()
                    self.spectrum.update_spectrum(display_heights, self.start_time)
                except queue.Empty:
                    pass
            elif not self.performance_mode_enabled:
                # 暂停时让频谱自然下降，但不更新进度条
                try:
                    display_heights = self.spectrum_processor.get_processed_data_queue().get_nowait()
                    self.spectrum.update_spectrum(display_heights, self.start_time)
                except queue.Empty:
                    pass
        else:
            # --- 没有播放器时，保持进度条和时间归零，但让频谱自然下降 ---
            self.progress_bar.set_progress(0)
            if not self.performance_mode_enabled:
                # 仍然尝试从处理器获取渐变下降的频谱数据
                try:
                    display_heights = self.spectrum_processor.get_processed_data_queue().get_nowait()
                    self.spectrum.update_spectrum(display_heights, self.start_time)
                except queue.Empty:
                    pass
            self.time_label.setText("00:00 / 00:00")

    def closeEvent(self, event):
        # 关闭窗口前保存设置
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

    def open_add_music_dialog(self):
        """打开添加音乐对话框"""
        dialog = AddMusicDialog(self, self.bilibili_downloader)
        dialog.file_added.connect(self.playlist.add_item)
        dialog.exec()

    def toggle_play_mode(self):
        """切换播放模式并持久化"""
        self.current_play_mode_index = (self.current_play_mode_index + 1) % len(self.play_modes)
        self.play_mode = self.play_modes[self.current_play_mode_index]
        self.play_mode_btn.setIcon(self.play_mode_icons[self.current_play_mode_index])
        # 持久化播放模式
        self.settings["play_mode"] = self.play_mode
        self.save_settings()

    def set_play_mode(self, mode):
        """设置播放模式"""
        try:
            idx = self.play_modes.index(mode)
            self.current_play_mode_index = idx
            self.play_mode = mode
            self.play_mode_btn.setIcon(self.play_mode_icons[idx])
        except ValueError:
            print(f"警告: 未知的播放模式 '{mode}'")

    def play_next(self):
        """播放下一首"""
        # 首先检查下一首播放队列
        if self.playlist_manager:
            next_file = self.playlist_manager.get_next_from_queue()
            if next_file and os.path.exists(next_file):
                self.play_file(next_file)
                return
        
        # 如果队列为空，按播放模式播放
        if not self.playlist.playlist_widget.count():
            return
            
        if self.play_mode == "random":
            # 随机播放模式
            import random
            count = self.playlist.playlist_widget.count()
            if count > 1:
                # 确保不会连续播放同一首歌
                next_index = self.current_index
                while next_index == self.current_index:
                    next_index = random.randint(0, count - 1)
                self.current_index = next_index
            else:
                self.current_index = 0
        else:
            # 顺序播放模式和单曲循环模式都切换到下一首
            self.current_index = (self.current_index + 1) % self.playlist.playlist_widget.count()
            
        # 获取并播放下一首
        item = self.playlist.playlist_widget.item(self.current_index)
        if item:
            file_path = item.data(Qt.ItemDataRole.UserRole)
            self.play_file(file_path)
            self.playlist.playlist_widget.setCurrentRow(self.current_index)

    def play_previous(self):
        """播放上一首"""
        if not self.playlist.playlist_widget.count():
            return
            
        if self.play_mode == "random":
            # 随机播放模式
            import random
            count = self.playlist.playlist_widget.count()
            if count > 1:
                # 确保不会连续播放同一首歌
                prev_index = self.current_index
                while prev_index == self.current_index:
                    prev_index = random.randint(0, count - 1)
                self.current_index = prev_index
            else:
                self.current_index = 0
        else:
            # 顺序播放模式和单曲循环模式都切换到上一首
            self.current_index = (self.current_index - 1) % self.playlist.playlist_widget.count()
            
        # 获取并播放上一首
        item = self.playlist.playlist_widget.item(self.current_index)
        if item:
            file_path = item.data(Qt.ItemDataRole.UserRole)
            self.play_file(file_path)
            self.playlist.playlist_widget.setCurrentRow(self.current_index)

    def seek_playback(self, progress):
        """处理跳转请求"""
        if self.player and self.player.get_duration() > 0:
            duration = self.player.get_duration()
            new_position = duration * progress
            
            # 停止当前播放，然后从新位置开始
            # self.player.seek(new_position) # 这种方式更可靠
            
            # 为了避免seek时UI的短暂停顿，可以先暂停，然后seek
            self.player.pause()
            self.player.seek(new_position)
            self.player.resume()
            self.is_playing = True # 确保状态正确
            self.update_play_pause_icon()

    def toggle_performance_mode(self, checked):
        """切换性能模式"""
        self.performance_mode_enabled = checked
        self.spectrum.setVisible(not checked)

    def eventFilter(self, source, event):
        """事件过滤器，用于处理音量条的显示和隐藏"""
        if source == self.volume_container:
            if event.type() == event.Type.Enter:
                self.volume_slider.setVisible(True)
            elif event.type() == event.Type.Leave:
                # 使用全局光标位置来判断是否真的离开了容器区域
                # 这能避免在鼠标进入子控件(音量条)时错误地触发隐藏
                if not self.volume_container.geometry().contains(self.volume_container.mapFromGlobal(QCursor.pos())):
                    self.volume_slider.setVisible(False)
            return True # 事件已处理
        return super().eventFilter(source, event)

    def set_volume(self, value):
        """设置音量并持久化"""
        if self.player:
            # 改为线性映射，使音量调节更直观
            self.player.set_volume(value / 100.0)
        # 更新并保存设置（确保设置已初始化）
        if hasattr(self, "settings"):
            self.settings["volume"] = value
            self.save_settings()

    def load_settings_data(self):
        """仅加载设置数据，不应用到UI控件"""
        try:
            if os.path.exists(self.config.SETTINGS_FILE):
                with open(self.config.SETTINGS_FILE, 'r') as f:
                    self.settings = json.load(f)
            else:
                # 如果文件不存在，使用默认值
                self.settings = {
                    "volume": 100, 
                    "play_mode": "sequence", 
                    "last_played_file": "",
                    "download_path": Config.DEFAULT_DOWNLOAD_PATH,
                    "proxy": ""
                }
        except (json.JSONDecodeError, FileNotFoundError):
            # 如果文件损坏或无法读取，使用默认值
            self.settings = {
                "volume": 100, 
                "play_mode": "sequence", 
                "last_played_file": "",
                "download_path": Config.DEFAULT_DOWNLOAD_PATH,
                "proxy": ""
            }

        # 确保下载目录存在
        download_path = self.settings.get("download_path", Config.DEFAULT_DOWNLOAD_PATH)
        if not os.path.exists(download_path):
            try:
                os.makedirs(download_path)
            except OSError:
                # 如果创建失败，回退到默认路径
                self.settings["download_path"] = Config.DEFAULT_DOWNLOAD_PATH
                if not os.path.exists(Config.DEFAULT_DOWNLOAD_PATH):
                    os.makedirs(Config.DEFAULT_DOWNLOAD_PATH)

    def apply_settings_to_ui(self):
        """将设置应用到UI控件"""
        # 恢复音量（线性）
        if hasattr(self, 'volume_slider'):
            self.volume_slider.setValue(self.settings.get("volume", 100))
        # 恢复播放模式
        self.set_play_mode(self.settings.get("play_mode", "sequence"))

    def save_settings(self):
        """保存播放器设置"""
        try:
            with open(self.config.SETTINGS_FILE, 'w') as f:
                json.dump(self.settings, f, indent=4)
        except IOError as e:
            print(f"无法保存设置: {e}")

    def restore_last_played_track(self):
        """在播放列表中定位并选中上一次播放的曲目"""
        last_file = self.settings.get("last_played_file")
        if not last_file:
            return

        # 查找文件在当前播放列表中的位置
        for i in range(self.playlist.playlist_widget.count()):
            item = self.playlist.playlist_widget.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == last_file:
                self.current_index = i
                self.playlist.playlist_widget.setCurrentRow(i)
                break

    def on_playlist_selection_changed(self):
        """处理播放列表选择变化"""
        self.update_play_pause_icon()

    def update_play_pause_icon(self):
        """根据播放状态和选中歌曲更新播放/暂停按钮的图标"""
        # 获取当前选中的歌曲
        selected_items = self.playlist.playlist_widget.selectedItems()
        if selected_items:
            selected_file = selected_items[0].data(Qt.ItemDataRole.UserRole)
            # 如果正在播放且选中的是当前播放的歌曲，显示暂停图标
            if self.is_playing and selected_file == self.current_file:
                self.play_pause_btn.setIcon(create_icon(get_icon_path("pause.svg")))
            else:
                # 其他情况显示播放图标
                self.play_pause_btn.setIcon(create_icon(get_icon_path("play.svg")))
        else:
            # 没有选中项时，根据播放状态显示图标
            if self.is_playing:
                self.play_pause_btn.setIcon(create_icon(get_icon_path("pause.svg")))
            else:
                self.play_pause_btn.setIcon(create_icon(get_icon_path("play.svg")))
    
    def open_settings(self):
        """打开设置对话框"""
        dialog = SettingsDialog(self, self.settings.copy())
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # 更新设置
            new_settings = dialog.get_settings()
            self.settings.update(new_settings)
            self.save_settings()
            
            # 确保下载目录存在
            download_path = self.settings.get("download_path", Config.DEFAULT_DOWNLOAD_PATH)
            if not os.path.exists(download_path):
                try:
                    os.makedirs(download_path)
                except OSError as e:
                    QMessageBox.warning(self, "警告", f"无法创建下载目录: {e}")
            
            # 更新下载器的下载路径和代理
            if hasattr(self, 'bilibili_downloader'):
                self.bilibili_downloader.set_download_path(download_path)
                proxy = self.settings.get("proxy", "")
                self.bilibili_downloader.set_proxy(proxy)
    
    def locate_current_song(self):
        """定位当前播放的歌曲"""
        if hasattr(self, 'playlist') and self.current_file:
            self.playlist.locate_current_song(self.current_file)
        else:
            QMessageBox.information(self, "提示", "当前没有播放歌曲")

def main():
    # 开启全局抗锯齿，使频谱更平滑
    pg.setConfigOptions(antialias=True)
    app = QApplication(sys.argv)
    
    # 加载外部样式表
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