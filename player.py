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
    QLineEdit, QMessageBox, QGraphicsDropShadowEffect
)
from PyQt6.QtCore import QTimer, Qt, QPropertyAnimation, QEasingCurve, QSize, pyqtSignal, QPoint
from PyQt6.QtGui import QPalette, QBrush, QLinearGradient, QColor, QPainter, QIcon, QPen, QFont
from backends.sd_ffmpeg_provider import AudioPlayer
from backends.bilibili_downloader import BilibiliDownloader
from backends.spectrum_processor import SpectrumProcessor
import time


class Config:
    SAMPLE_RATE = 44100
    CHUNK_SIZE = 1024
    MAX_FREQ = 8000
    NUM_BARS = 100
    MAX_DB_VALUE = 90.0
    INNER_RADIUS = 80
    MAX_AMPLITUDE_RADIUS = 120
    MIN_RADIUS_OFFSET = 1
    BAR_WIDTH = 3.0
    ROTATION_SPEED_RAD_PER_SEC = -np.pi / 40.0
    WINDOW_TITLE = "Bili音乐播放助手"
    WINDOW_SIZE = (800, 600)
    UI_UPDATE_INTERVAL_MS = 15
    COLOR_POSITIONS = [0.0, 0.2, 0.4, 0.8]
    COLOR_MAP_COLORS = [
        (40, 0, 60, 180),
        (100, 0, 180, 255),
        (255, 0, 150, 255),
        (255, 180, 255, 255),
    ]
    PLAYLIST_FILE = "playlist.json"
    PROGRESS_BAR_RADIUS = 78
    PROGRESS_BAR_WIDTH = 12
    PROGRESS_BAR_COLOR = QColor(0, 122, 255)  # 苹果蓝
    PROGRESS_BAR_BG_COLOR = QColor(200, 150, 200, 100)  # 增加背景不透明度

class SpectrumWidget(pg.GraphicsLayoutWidget):
    def __init__(self, config):
        self.config = config
        super().__init__()
        self.setBackground(None)
        self.plot_item = self.addPlot()
        self.plot_item.setAspectLocked(True)
        self.plot_item.hideAxis("left")
        self.plot_item.hideAxis("bottom")
        self.plot_item.setMouseEnabled(x=False, y=False)
        self.plot_item.vb.setMouseEnabled(x=False, y=False)
        self.plot_item.hideButtons()
        plot_range = (self.config.INNER_RADIUS + self.config.MAX_AMPLITUDE_RADIUS) * 1.1
        self.plot_item.setXRange(-plot_range, plot_range, padding=0)
        self.plot_item.setYRange(-plot_range, plot_range, padding=0)
        self.color_map = pg.ColorMap(self.config.COLOR_POSITIONS, np.array(self.config.COLOR_MAP_COLORS))
        # 不再绘制内圈
        self.bar_items = []
        for _ in range(self.config.NUM_BARS):
            item = pg.PlotDataItem(pen=pg.mkPen(width=self.config.BAR_WIDTH))
            self.plot_item.addItem(item)
            self.bar_items.append(item)
        self.angles_rad_base = np.pi / 2 + np.linspace(0, 2 * np.pi, self.config.NUM_BARS, endpoint=False)
        self._last_display_heights = np.zeros(self.config.NUM_BARS)
        self.start_time = 0
        self.setBackground(None)
        self.setStyleSheet("background: transparent;")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def resizeEvent(self, event):
        if not hasattr(self, 'config') or not hasattr(self, 'bar_items'):
            return
        super().resizeEvent(event)
        min_side = min(self.width(), self.height())
        new_width = max(1.0, min(self.config.BAR_WIDTH, min_side / (self.config.NUM_BARS * 2)))
        for item in self.bar_items:
            item.setPen(pg.mkPen(width=new_width))

    def update_spectrum(self, heights, start_time):
        config = self.config
        heights_clipped = np.clip(heights, 0, config.MAX_DB_VALUE)
        radii_outer = (
            config.INNER_RADIUS
            + config.MIN_RADIUS_OFFSET
            + (config.MAX_AMPLITUDE_RADIUS / config.MAX_DB_VALUE) * heights_clipped
        )
        if config.NUM_BARS > 1:
            avg_radius_edge = (radii_outer[0] + radii_outer[-1]) / 2.0
            radii_outer[-1] = avg_radius_edge
        elapsed_time = time.time() - start_time
        rotation_offset = elapsed_time * config.ROTATION_SPEED_RAD_PER_SEC
        current_angles = self.angles_rad_base + rotation_offset
        current_cos = np.cos(current_angles)
        current_sin = np.sin(current_angles)
        normalized_heights = heights_clipped / config.MAX_DB_VALUE
        bar_q_colors = self.color_map.mapToQColor(normalized_heights)
        for i in range(config.NUM_BARS):
            r_outer = radii_outer[i]
            cos_i, sin_i = current_cos[i], current_sin[i]
            x_data = [config.INNER_RADIUS * cos_i, r_outer * cos_i]
            y_data = [config.INNER_RADIUS * sin_i, r_outer * sin_i]
            pen = pg.mkPen(color=bar_q_colors[i], width=self.config.BAR_WIDTH)
            self.bar_items[i].setData(x_data, y_data, pen=pen)

class GradientWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._bg_phase = 0
        # 设置自动填充背景
        self.setAutoFillBackground(True)
        # 初始化时立即更新一次背景
        self.update()

    @property
    def bg_phase(self):
        return self._bg_phase

    @bg_phase.setter
    def bg_phase(self, value):
        self._bg_phase = value
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 大小改变时更新背景
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        # 确保渐变覆盖整个窗口
        grad = QLinearGradient(0, 0, self.width(), self.height())
        c1 = QColor.fromHsvF((0.6 + 0.2 * np.sin(self._bg_phase)) % 1, 0.5, 1, 1)
        c2 = QColor.fromHsvF((0.9 + 0.2 * np.cos(self._bg_phase)) % 1, 0.5, 1, 1)
        grad.setColorAt(0, c1)
        grad.setColorAt(1, c2)
        # 使用渐变填充整个窗口
        painter.fillRect(self.rect(), grad)

class CircularProgressBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.progress = 0
        self.setMinimumSize(Config.PROGRESS_BAR_RADIUS * 2, Config.PROGRESS_BAR_RADIUS * 2)
        self.setMaximumSize(Config.PROGRESS_BAR_RADIUS * 2, Config.PROGRESS_BAR_RADIUS * 2)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def sizeHint(self):
        return QSize(Config.PROGRESS_BAR_RADIUS * 2, Config.PROGRESS_BAR_RADIUS * 2)

    def set_progress(self, value):
        self.progress = value
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            pen_width = Config.PROGRESS_BAR_WIDTH
            
            # 关键修复：
            # 创建一个安全边距，防止因画笔宽度和圆角端点导致的边缘裁剪问题。
            # 边距至少应为画笔宽度的一半，这里我们额外加1个像素作为安全缓冲。
            margin = (pen_width // 2) + 1

            # 根据边距，从原始控件矩形中创建一个内缩的、安全的绘图矩形。
            # 所有的绘图都将在这个矩形内完成。
            paint_rect = self.rect().adjusted(margin, margin, -margin, -margin)

            # 1. 绘制背景环
            # 使用安全的绘图矩形来绘制，确保背景环也不会被裁剪。
            bg_pen = QPen(Config.PROGRESS_BAR_BG_COLOR, pen_width, Qt.PenStyle.SolidLine)
            painter.setPen(bg_pen)
            painter.drawEllipse(paint_rect)

            # 2. 绘制进度弧
            # 同样在安全的绘图矩形内绘制。
            progress_pen = QPen(Config.PROGRESS_BAR_COLOR, pen_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            painter.setPen(progress_pen)

            start_angle = 90 * 16  # 从 0 度 (3点钟方向) 开始
            span_angle = int(-self.progress * 360 * 16)  # 顺时针
            
            # drawArc现在使用调整后的安全矩形，可以确保圆角端点被完整绘制。
            painter.drawArc(paint_rect, start_angle, span_angle)

        finally:
            painter.end()

class CollapsiblePlaylist(QWidget):
    play_signal = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self.load_playlist()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        
        
        

        # 创建B站下载输入框
        self.bilibili_input = QLineEdit()
        self.bilibili_input.setPlaceholderText("输入B站视频链接")
        self.bilibili_input.setStyleSheet('''
            QLineEdit {
                background: rgba(255,255,255,0.15);
                border: 1px solid rgba(255,255,255,0.3);
                border-radius: 12px;
                padding: 6px 12px;
                color: white;
                font-size: 12px;
            }
            QLineEdit:focus {
                background: rgba(255,255,255,0.2);
                border: 1px solid rgba(255,255,255,0.4);
            }
        ''')
        layout.addWidget(self.bilibili_input)
        
        # 创建按钮行
        button_row = QHBoxLayout()
        button_row.setSpacing(8)
        
        # 下载按钮
        self.download_btn = QPushButton("下载")
        self.download_btn.setStyleSheet('''
            QPushButton {
                background: rgba(255,255,255,0.15);
                border: 1px solid rgba(255,255,255,0.3);
                border-radius: 12px;
                padding: 6px;
                color: white;
                font-size: 12px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.2);
            }
        ''')
        self.download_btn.clicked.connect(self.parent().download_bilibili_audio)
        
        # 添加文件按钮
        self.select_file_btn = QPushButton("添加文件")
        self.select_file_btn.setStyleSheet('''
            QPushButton {
                background: rgba(255,255,255,0.15);
                border: 1px solid rgba(255,255,255,0.3);
                border-radius: 12px;
                padding: 6px;
                color: white;
                font-size: 12px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.2);
            }
        ''')
        self.select_file_btn.clicked.connect(self.select_files)
        
        # 删除按钮
        self.delete_btn = QPushButton("删除")
        self.delete_btn.setStyleSheet('''
            QPushButton {
                background: rgba(255,255,255,0.15);
                border: 1px solid rgba(255,255,255,0.3);
                border-radius: 12px;
                padding: 6px;
                color: white;
                font-size: 12px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.2);
            }
        ''')
        self.delete_btn.clicked.connect(self.delete_selected)
        
        # 添加按钮到布局
        button_row.addWidget(self.download_btn)
        button_row.addWidget(self.select_file_btn)
        button_row.addWidget(self.delete_btn)
        layout.addLayout(button_row)
        
        # 创建搜索框
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("搜索播放列表...")
        self.search_box.setStyleSheet('''
            QLineEdit {
                background: rgba(255,255,255,0.15);
                border: 1px solid rgba(255,255,255,0.3);
                border-radius: 12px;
                padding: 6px 12px;
                color: white;
                font-size: 12px;
            }
            QLineEdit:focus {
                background: rgba(255,255,255,0.2);
                border: 1px solid rgba(255,255,255,0.4);
            }
        ''')
        self.search_box.textChanged.connect(self.filter_playlist)
        layout.addWidget(self.search_box)

        # 创建播放列表
        self.playlist_widget = QListWidget()
        self.playlist_widget.setStyleSheet('''
            QListWidget {
                background: rgba(255,255,255,0.1);
                border: 1px solid rgba(255,255,255,0.2);
                border-radius: 12px;
                padding: 4px;
                color: white;
                font-size: 12px;
            }
            QListWidget::item {
                padding: 6px;
                border-radius: 6px;
            }
            QListWidget::item:selected {
                background: rgba(33,150,243,0.2);
            }
            QListWidget::item:hover {
                background: rgba(255,255,255,0.1);
            }
        ''')
        self.playlist_widget.itemDoubleClicked.connect(self.on_item_double_clicked)
        layout.addWidget(self.playlist_widget)
        
    def filter_playlist(self, text):
        for i in range(self.playlist_widget.count()):
            item = self.playlist_widget.item(i)
            file_name = os.path.basename(item.data(Qt.ItemDataRole.UserRole))
            item.setHidden(text.lower() not in file_name.lower())
            
    def on_item_double_clicked(self, item):
        file_path = item.data(Qt.ItemDataRole.UserRole)
        self.play_signal.emit(file_path)
        
    def select_files(self): # 建议将函数名也改为复数形式
        # 调用 getOpenFileNames 来允许多选
        file_names, _ = QFileDialog.getOpenFileNames(
            self, "选择一个或多个音频文件", "", "音频文件 (*.mp3 *.wav *.ogg *.flac *.aac *.m4a)"
        )

        if file_names:
            for file_name in file_names:
                self.add_item(file_name)
            
    def add_item(self, file_path):
        # 禁止重复添加
        for i in range(self.playlist_widget.count()):
            if self.playlist_widget.item(i).data(Qt.ItemDataRole.UserRole) == file_path:
                return
        item = QListWidgetItem(os.path.basename(file_path))
        item.setData(Qt.ItemDataRole.UserRole, file_path)
        self.playlist_widget.addItem(item)
        self.save_playlist()

    def delete_selected(self):
        current_row = self.playlist_widget.currentRow()
        if current_row >= 0:
            self.playlist_widget.takeItem(current_row)
            self.save_playlist()
            
    def save_playlist(self):
        playlist = []
        for i in range(self.playlist_widget.count()):
            item = self.playlist_widget.item(i)
            playlist.append(item.data(Qt.ItemDataRole.UserRole))
        
        with open(Config.PLAYLIST_FILE, 'w', encoding='utf-8') as f:
            json.dump(playlist, f, ensure_ascii=False)

    def load_playlist(self):
        try:
            with open(Config.PLAYLIST_FILE, 'r', encoding='utf-8') as f:
                playlist = json.load(f)
                for file_path in playlist:
                    if os.path.exists(file_path):
                        self.add_item(file_path)
        except FileNotFoundError:
            pass

class PlayPauseIcon(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_playing = False
        self.setFixedSize(48, 48)  # 增大尺寸到48x48
        
    def set_playing(self, playing):
        self.is_playing = playing
        self.update()
        
    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            # 设置白色画笔
            pen = QPen(QColor(255, 255, 255))
            pen.setWidth(3)  # 增加线条宽度
            painter.setPen(pen)
            
            if self.is_playing:
                # 绘制暂停图标（两个竖条）
                bar_width = 8  # 增加宽度
                gap = 8  # 增加间距
                left = (self.width() - (bar_width * 2 + gap)) / 2
                top = (self.height() - 32) / 2  # 增加高度
                painter.drawRect(int(left), int(top), bar_width, 32)
                painter.drawRect(int(left + bar_width + gap), int(top), bar_width, 32)
            else:
                # 绘制播放图标（三角形）
                points = [
                    (self.width() * 0.3, self.height() * 0.2),  # 左上
                    (self.width() * 0.3, self.height() * 0.8),  # 左下
                    (self.width() * 0.8, self.height() * 0.5),  # 右中
                ]
                painter.drawPolygon([QPoint(int(x), int(y)) for x, y in points])
        finally:
            painter.end()

class PlayerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = Config()
        self.progress_bar = CircularProgressBar()  # 必须在setup_ui之前
        self.setWindowTitle(self.config.WINDOW_TITLE)
        self.resize(*self.config.WINDOW_SIZE)
        
        # 添加播放模式相关属性
        self.play_mode = "sequence"  # 可选值: sequence(顺序播放), random(随机播放), single(单曲循环)
        self.playlist_history = []  # 用于随机播放时记录历史
        self.current_index = -1  # 当前播放的索引
        
        self.setup_ui()
        self.setup_audio()
        self.bilibili_downloader = BilibiliDownloader()
        
        # 创建音频数据队列和频谱处理器
        self.audio_queue = queue.Queue(maxsize=10)
        self.spectrum_processor = SpectrumProcessor(self.config, self.audio_queue)
        self.spectrum_processor.start()

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
        self.bg_widget.setMinimumSize(self.width(), self.height())
        main_layout.addWidget(self.bg_widget)
        
        # 创建内容布局
        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(20, 20, 20, 20)
        
        # 创建左侧控制面板
        control_panel = QWidget()
        control_layout = QVBoxLayout(control_panel)
        control_layout.setSpacing(6)  # 减小垂直间距
        control_panel.setStyleSheet('''
            background: rgba(255,255,255,0.18);
            border-radius: 18px;
            border: 1px solid rgba(255,255,255,0.3);
            font-family: '微软雅黑', 'Segoe UI', 'Arial', 'sans-serif';
        ''')
        
        # 先创建播放列表
        self.playlist = CollapsiblePlaylist(self)
        self.playlist.play_signal.connect(self.play_file)
        control_layout.addWidget(self.playlist)
        
        content_layout.addWidget(control_panel)
        
        # 创建频谱显示部件
        self.spectrum = SpectrumWidget(self.config)

        # 创建 overlay 容器
        overlay_container = QWidget()
        overlay_layout = QVBoxLayout(overlay_container)  # 改为垂直布局
        overlay_layout.setContentsMargins(0, 0, 0, 0)
        overlay_layout.setSpacing(20)  # 设置垂直间距

        # 创建频谱和进度条的容器
        spectrum_container = QWidget()
        spectrum_layout = QGridLayout(spectrum_container)
        spectrum_layout.setContentsMargins(0, 0, 0, 0)

        # 将频谱部件添加到布局的底层
        spectrum_layout.addWidget(self.spectrum, 0, 0)

        # 创建进度条的覆盖层
        progress_overlay = QWidget()
        progress_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        progress_overlay.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        progress_overlay.setStyleSheet("background: transparent;")
        
        # 使用垂直和水平布局来将进度条和播放按钮精确定位在中心
        progress_v_layout = QVBoxLayout(progress_overlay)
        progress_v_layout.setContentsMargins(0, 0, 0, 0)
        progress_h_layout = QHBoxLayout()

        progress_v_layout.addStretch(1)
        progress_h_layout.addStretch(1)
        
        # 将进度条添加到布局中
        progress_h_layout.addWidget(self.progress_bar)
        progress_h_layout.addStretch(1)
        progress_v_layout.addLayout(progress_h_layout)
        progress_v_layout.addStretch(1)

        # 将进度条覆盖层添加到同一个单元格
        spectrum_layout.addWidget(progress_overlay, 0, 0)

        # 创建播放按钮的覆盖层
        button_overlay = QWidget()
        button_overlay.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        button_overlay.setStyleSheet("background: transparent;")
        
        # 使用垂直和水平布局来将播放按钮精确定位在中心
        button_v_layout = QVBoxLayout(button_overlay)
        button_v_layout.setContentsMargins(0, 0, 0, 0)
        button_h_layout = QHBoxLayout()

        button_v_layout.addStretch(1)
        button_h_layout.addStretch(1)
        
        # 播放/暂停按钮
        self.play_pause_btn = QPushButton()
        self.play_pause_btn.setIcon(QIcon("assets/icons/play.svg"))
        self.play_pause_btn.setIconSize(QSize(48,48))
        self.play_pause_btn.setStyleSheet('''
            QPushButton {
                background: rgba(255,255,255,0.25);
                border: none;
                border-radius: 24px;
                min-width: 48px;
                min-height: 48px;
            }
            QPushButton:hover {
                background: rgba(33,150,243,0.12);
            }
            QPushButton:pressed {
                background: rgba(33,150,243,0.18);
            }
        ''')
        self.play_pause_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.play_pause_btn.clicked.connect(self.toggle_play)
        
        button_h_layout.addWidget(self.play_pause_btn)
        button_h_layout.addStretch(1)
        button_v_layout.addLayout(button_h_layout)
        button_v_layout.addStretch(1)

        # 将播放按钮覆盖层添加到同一个单元格
        spectrum_layout.addWidget(button_overlay, 0, 0)

        # 将频谱容器添加到主布局
        overlay_layout.addWidget(spectrum_container)

        # 创建播放控制按钮容器
        control_buttons_container = QWidget()
        control_buttons_layout = QVBoxLayout(control_buttons_container)
        control_buttons_layout.setContentsMargins(0, 0, 0, 0)
        control_buttons_layout.setSpacing(10)

        # 创建播放控制按钮组
        playback_buttons = QWidget()
        playback_layout = QHBoxLayout(playback_buttons)
        playback_layout.setContentsMargins(0, 0, 0, 0)
        playback_layout.setSpacing(20)

        # 上一首按钮
        self.prev_btn = QPushButton()
        self.prev_btn.setIcon(QIcon("assets/icons/prev.svg"))
        self.prev_btn.setIconSize(QSize(32,32))
        self.prev_btn.setStyleSheet('''
            QPushButton {
                background: rgba(255,255,255,0.25);
                border: none;
                border-radius: 16px;
                min-width: 40px;
                min-height: 40px;
            }
            QPushButton:hover {
                background: rgba(33,150,243,0.12);
            }
            QPushButton:pressed {
                background: rgba(33,150,243,0.18);
            }
        ''')
        self.prev_btn.clicked.connect(self.play_previous)

        # 停止按钮
        self.stop_btn = QPushButton()
        self.stop_btn.setIcon(QIcon("assets/icons/stop.svg"))
        self.stop_btn.setIconSize(QSize(32,32))
        self.stop_btn.setStyleSheet('''
            QPushButton {
                background: rgba(255,255,255,0.25);
                border: none;
                border-radius: 16px;
                min-width: 40px;
                min-height: 40px;
            }
            QPushButton:hover {
                background: rgba(33,150,243,0.12);
            }
            QPushButton:pressed {
                background: rgba(33,150,243,0.18);
            }
        ''')
        self.stop_btn.clicked.connect(self.stop)

        # 下一首按钮
        self.next_btn = QPushButton()
        self.next_btn.setIcon(QIcon("assets/icons/next.svg"))
        self.next_btn.setIconSize(QSize(32,32))
        self.next_btn.setStyleSheet('''
            QPushButton {
                background: rgba(255,255,255,0.25);
                border: none;
                border-radius: 16px;
                min-width: 40px;
                min-height: 40px;
            }
            QPushButton:hover {
                background: rgba(33,150,243,0.12);
            }
            QPushButton:pressed {
                background: rgba(33,150,243,0.18);
            }
        ''')
        self.next_btn.clicked.connect(self.play_next)

        # 添加播放控制按钮到布局
        playback_layout.addStretch(1)
        playback_layout.addWidget(self.prev_btn)
        playback_layout.addWidget(self.stop_btn)
        playback_layout.addWidget(self.next_btn)
        playback_layout.addStretch(1)

        # 创建播放模式按钮组
        mode_buttons = QWidget()
        mode_layout = QHBoxLayout(mode_buttons)
        mode_layout.setContentsMargins(0, 0, 0, 0)
        mode_layout.setSpacing(20)

        # 顺序播放按钮
        self.sequence_btn = QPushButton()
        self.sequence_btn.setIcon(QIcon("assets/icons/repeat.svg"))
        self.sequence_btn.setIconSize(QSize(28,28))
        self.sequence_btn.setCheckable(True)
        self.sequence_btn.setStyleSheet('''
            QPushButton {
                background: rgba(255,255,255,0.18);
                border: none;
                border-radius: 14px;
                min-width: 36px;
                min-height: 36px;
            }
            QPushButton:checked {
                background: rgba(33,150,243,0.18);
            }
            QPushButton:hover {
                background: rgba(33,150,243,0.12);
            }
        ''')

        # 随机播放按钮
        self.random_btn = QPushButton()
        self.random_btn.setIcon(QIcon("assets/icons/shuffle.svg"))
        self.random_btn.setIconSize(QSize(28,28))
        self.random_btn.setCheckable(True)
        self.random_btn.setStyleSheet('''
            QPushButton {
                background: rgba(255,255,255,0.18);
                border: none;
                border-radius: 14px;
                min-width: 36px;
                min-height: 36px;
            }
            QPushButton:checked {
                background: rgba(33,150,243,0.18);
            }
            QPushButton:hover {
                background: rgba(33,150,243,0.12);
            }
        ''')

        # 单曲循环按钮
        self.single_btn = QPushButton()
        self.single_btn.setIcon(QIcon("assets/icons/repeat-one.svg"))
        self.single_btn.setIconSize(QSize(28,28))
        self.single_btn.setCheckable(True)
        self.single_btn.setStyleSheet('''
            QPushButton {
                background: rgba(255,255,255,0.18);
                border: none;
                border-radius: 14px;
                min-width: 36px;
                min-height: 36px;
            }
            QPushButton:checked {
                background: rgba(33,150,243,0.18);
            }
            QPushButton:hover {
                background: rgba(33,150,243,0.12);
            }
        ''')

        # 添加播放模式按钮到布局
        mode_layout.addStretch(1)
        mode_layout.addWidget(self.sequence_btn)
        mode_layout.addWidget(self.random_btn)
        mode_layout.addWidget(self.single_btn)
        mode_layout.addStretch(1)

        # 连接播放模式按钮信号
        self.sequence_btn.clicked.connect(lambda: self.set_play_mode("sequence"))
        self.random_btn.clicked.connect(lambda: self.set_play_mode("random"))
        self.single_btn.clicked.connect(lambda: self.set_play_mode("single"))

        # 设置默认播放模式
        self.sequence_btn.setChecked(True)

        # 将按钮组添加到控制按钮容器
        control_buttons_layout.addWidget(playback_buttons)
        control_buttons_layout.addWidget(mode_buttons)

        # 将控制按钮容器添加到主布局
        overlay_layout.addWidget(control_buttons_container)

        # 将包含所有叠加内容的容器添加到主内容布局中
        content_layout.addWidget(overlay_container, stretch=1)
        
        # 将内容布局添加到背景部件上
        self.bg_widget.setLayout(content_layout)
        
        # 设置背景动画
        self.bg_animation = QPropertyAnimation(self.bg_widget, b"bg_phase")
        self.bg_animation.setDuration(10000)
        self.bg_animation.setStartValue(0)
        self.bg_animation.setEndValue(2 * np.pi)
        self.bg_animation.setLoopCount(-1)
        self.bg_animation.setEasingCurve(QEasingCurve.Type.Linear)
        self.bg_animation.start()
        
        # 设置频谱更新定时器
        self.spectrum_timer = QTimer()
        self.spectrum_timer.timeout.connect(self.update_spectrum)
        self.spectrum_timer.start(self.config.UI_UPDATE_INTERVAL_MS)

    def set_button_style(self, btn):
        btn.setStyleSheet('''
            QPushButton {
                background: rgba(255, 255, 255, 0.2);
                color: white;
                border: none;
                border-radius: 18px;
                min-width: 36px;
                min-height: 36px;
                font-size: 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.3);
            }
            QPushButton:pressed {
                background: rgba(255, 255, 255, 0.4);
            }
            QPushButton:disabled {
                background: rgba(255, 255, 255, 0.1);
                color: rgba(255, 255, 255, 0.5);
            }
        ''')

    def update_background(self):
        self.bg_phase += 0.01
        self.bg_widget.set_bg_phase(self.bg_phase)

    def setup_audio(self):
        """初始化音频播放器"""
        self.player = None
        self.current_file = None
        self.is_playing = False
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

    def select_file(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self, "选择音频文件", "", "音频文件 (*.mp3 *.wav *.ogg *.flac *.aac *.m4a)"
        )
        if file_name:
            self.load_file(file_name)
            self.playlist.add_item(file_name)

    def play_file(self, file_path):
        """播放指定文件"""
        if self.player:
            self.player.stop()
        self.player = AudioPlayer(file_path)
        self.current_file = file_path
        self.player.play()
        self.is_playing = True
        self.play_pause_btn.setIcon(QIcon("assets/icons/pause.svg"))
        self.stop_btn.setEnabled(True)
        # 清空频谱
        self.spectrum.update_spectrum(np.zeros(self.config.NUM_BARS), self.start_time)
        
        # 更新当前索引
        for i in range(self.playlist.playlist_widget.count()):
            item = self.playlist.playlist_widget.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == file_path:
                self.current_index = i
                break
                
        # 连接播放结束信号
        self.player.playback_finished.connect(self.on_playback_finished)

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
            self.play_pause_btn.setIcon(QIcon("assets/icons/play.svg"))
            # 清空频谱
            self.spectrum.update_spectrum(np.zeros(self.config.NUM_BARS), self.start_time)
        else:
            self.player.resume()
            self.is_playing = True
            self.play_pause_btn.setIcon(QIcon("assets/icons/pause.svg"))

    def stop(self):
        if self.player:
            self.player.stop()
            self.is_playing = False
            self.play_pause_btn.setIcon(QIcon("assets/icons/play.svg"))
            # 清空频谱
            self.spectrum.update_spectrum(np.zeros(self.config.NUM_BARS), self.start_time)

    def update_spectrum(self):
        if self.player:
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
            # 更新进度条
            try:
                pos = self.player.get_position()
                dur = self.player.get_duration()
                progress = pos / dur if dur > 0 else 0
                self.progress_bar.set_progress(progress)
            except Exception:
                self.progress_bar.set_progress(0)
        else:
            # 没有播放器时也归零
            heights = np.zeros(self.config.NUM_BARS)
            self.spectrum.update_spectrum(heights, self.start_time)
            self.progress_bar.set_progress(0)

    def closeEvent(self, event):
        if self.player:
            self.player.stop()
        if hasattr(self, 'spectrum_processor'):
            self.spectrum_processor.stop()
        event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'bg_widget'):
            self.bg_widget.setGeometry(self.rect())

    def download_bilibili_audio(self):
        """下载B站视频音频"""
        url = self.playlist.bilibili_input.text().strip()
        if not url:
            QMessageBox.warning(self, "警告", "请输入B站视频链接")
            return
        try:
            # 下载音频并自动以视频标题命名
            output_path = self.bilibili_downloader.download_from_url(url)
            # 添加到播放列表
            self.playlist.add_item(output_path)
            QMessageBox.information(self, "成功", "音频下载完成")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"下载失败: {str(e)}")

    def set_play_mode(self, mode):
        """设置播放模式"""
        self.play_mode = mode
        # 更新按钮状态
        self.sequence_btn.setChecked(mode == "sequence")
        self.random_btn.setChecked(mode == "random")
        self.single_btn.setChecked(mode == "single")

    def play_next(self):
        """播放下一首"""
        if not self.playlist.playlist_widget.count():
            return
            
        if self.play_mode == "single":
            # 单曲循环模式，重新播放当前歌曲
            if self.current_file:
                self.play_file(self.current_file)
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
            # 顺序播放模式
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
            
        if self.play_mode == "single":
            # 单曲循环模式，重新播放当前歌曲
            if self.current_file:
                self.play_file(self.current_file)
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
            # 顺序播放模式
            self.current_index = (self.current_index - 1) % self.playlist.playlist_widget.count()
            
        # 获取并播放上一首
        item = self.playlist.playlist_widget.item(self.current_index)
        if item:
            file_path = item.data(Qt.ItemDataRole.UserRole)
            self.play_file(file_path)
            self.playlist.playlist_widget.setCurrentRow(self.current_index)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = PlayerWindow()
    window.show()
    sys.exit(app.exec())
