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
    QLineEdit, QMessageBox, QGraphicsDropShadowEffect, QSlider
)
from PyQt6.QtCore import QTimer, Qt, QPropertyAnimation, QEasingCurve, QSize, pyqtSignal, QPoint
from PyQt6.QtGui import QPalette, QBrush, QLinearGradient, QColor, QPainter, QIcon, QPen, QFont
from backends.sd_ffmpeg_provider import AudioPlayer
from backends.bilibili_downloader import BilibiliDownloader
from backends.spectrum_processor import SpectrumProcessor
import time


def get_resource_path(relative_path):
    """获取资源文件的绝对路径，支持开发环境和打包环境"""
    try:
        # PyInstaller会创建临时文件夹，并将路径存储在_MEIPASS中
        base_path = sys._MEIPASS
    except AttributeError:
        # 如果不是通过PyInstaller运行，使用脚本所在目录
        base_path = os.path.dirname(os.path.abspath(__file__))
    
    return os.path.join(base_path, relative_path)


class Config:
    SAMPLE_RATE = 44100
    CHUNK_SIZE = 1024
    MAX_FREQ = 8000
    NUM_BARS = 100
    MAX_DB_VALUE = 90.0
    
    # --- 频谱和进度条尺寸 ---
    # 下面的半径值与 setup_ui 中固定的容器尺寸相关联
    # 频谱内圈半径，决定了频谱条的起始位置
    INNER_RADIUS = 120
    # 频谱条的最大振幅，INNER_RADIUS + MAX_AMPLITUDE_RADIUS 构成了频谱的总体外部大小
    MAX_AMPLITUDE_RADIUS = 100
    MIN_RADIUS_OFFSET = 2.
    BAR_WIDTH = 3.0
    # --- 频谱和进度条尺寸 ---

    ROTATION_SPEED_RAD_PER_SEC = -np.pi / 40.0
    WINDOW_TITLE = "Bili音乐播放助手"
    WINDOW_SIZE = (900, 600)
    UI_UPDATE_INTERVAL_MS = 15
    COLOR_POSITIONS = [0.0, 0.2, 0.4, 0.8]
    COLOR_MAP_COLORS = [
        (40, 0, 60, 180),
        (100, 0, 180, 255),
        (255, 0, 150, 255),
        (255, 180, 255, 255),
    ]
    PLAYLIST_FILE = "playlist.json"

    # --- 频谱渐变色 ---
    SPECTRUM_INNER_COLOR = QColor("#43e97b")
    SPECTRUM_OUTER_COLOR = QColor("#38f9d7")

    # 进度条半径，建议略小于频谱内圈半径 INNER_RADIUS
    PROGRESS_BAR_RADIUS = 115
    PROGRESS_BAR_WIDTH = 12
    PROGRESS_BAR_COLOR = QColor(255, 255, 255, 100)  # 半透明白
    PROGRESS_BAR_BG_COLOR = QColor(255, 255, 255, 50)   # 更透明的白

    # --- 按钮尺寸 ---
    CONTROL_BUTTON_SIZE = 40
    CONTROL_BUTTON_ICON_SIZE = 32

    # --- 低频波浪配置 ---
    # 用于低频波浪的频段数量
    NUM_LOW_FREQ_BARS = 5
    # 低频波浪曲线的点数，越多越平滑
    LOW_FREQ_WAVE_NUM_POINTS = 360
    # 低频波浪的基础半径
    LOW_FREQ_WAVE_BASE_RADIUS = 125
    # 低频波浪的最大振幅
    LOW_FREQ_WAVE_AMPLITUDE = 30
    # 低频波浪的线条宽度
    LOW_FREQ_WAVE_WIDTH = 2.5
    # 低频波浪的颜色
    LOW_FREQ_WAVE_COLOR = QColor(100, 200, 255, 220)

class EventLoggingWidget(QWidget):
    """一个简单的QWidget子类，用于打印鼠标事件以进行调试"""
    def mousePressEvent(self, event):
        # print(f"LOG: EventLoggingWidget received mouse press event at {event.pos()}")
        super().mousePressEvent(event)

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

        # 低频波浪线
        # self.low_freq_wave_item = pg.PlotDataItem(
        #     pen=pg.mkPen(
        #         color=self.config.LOW_FREQ_WAVE_COLOR, 
        #         width=self.config.LOW_FREQ_WAVE_WIDTH
        #     )
        # )
        # self.plot_item.addItem(self.low_freq_wave_item)
        
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
        
        # --- 更新主频谱条 (现有逻辑) ---
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

        # --- 更新低频波浪 (新逻辑) ---
        # self.update_low_freq_wave(heights_clipped, rotation_offset)

    def update_low_freq_wave(self, heights, rotation_offset):
        """根据低频数据更新内部波浪曲线"""
        config = self.config
        
        # 1. 提取低频数据
        low_freq_heights = heights[:config.NUM_LOW_FREQ_BARS]

        # 2. 创建用于插值的原始数据点
        #    为了使曲线闭合，将第一个点附加到末尾
        wave_data = np.append(low_freq_heights, low_freq_heights[0])
        original_indices = np.linspace(0, 1, len(wave_data))

        # 3. 创建更密集的索引以生成平滑曲线
        finer_indices = np.linspace(0, 1, config.LOW_FREQ_WAVE_NUM_POINTS)

        # 4. 插值计算平滑后的高度
        smoothed_heights = np.interp(finer_indices, original_indices, wave_data)

        # 5. 计算每个点的半径
        normalized_wave_heights = smoothed_heights / config.MAX_DB_VALUE
        radii = (
            config.LOW_FREQ_WAVE_BASE_RADIUS + 
            normalized_wave_heights * config.LOW_FREQ_WAVE_AMPLITUDE
        )

        # 6. 计算波浪上每个点的x, y坐标
        #    加上 rotation_offset 使其与主频谱同步旋转
        #    额外加上 pi/2 是为了让起始点对齐到12点钟方向
        wave_angles = np.linspace(0, 2 * np.pi, config.LOW_FREQ_WAVE_NUM_POINTS) + rotation_offset + np.pi/2
        x = radii * np.cos(wave_angles)
        y = radii * np.sin(wave_angles)

        # 7. 更新曲线数据
        self.low_freq_wave_item.setData(x, y)

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
    seek_requested = pyqtSignal(float)  # 信号：传递0-1的进度

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

    def mousePressEvent(self, event):
        """添加日志以进行调试"""
        # print(f"LOG: CircularProgressBar received mouse press event at {event.pos()}")
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        """处理鼠标点击事件以实现跳转"""
        center = self.rect().center()
        # 计算从中心点到鼠标点击位置的向量
        vec = event.pos() - center
        
        # 使用arctan2计算角度，y坐标取反以匹配数学坐标系
        # (Qt的y轴向下为正)
        angle_rad = np.arctan2(-vec.y(), vec.x())
        
        # 将角度从 (-pi, pi] 转换为 [0, 2*pi)
        # 再将起始点从3点钟方向移到12点钟方向
        progress_angle = (angle_rad - np.pi / 2 + 2 * np.pi) % (2 * np.pi)
        
        # 转换为0-1的进度值 (顺时针)
        progress = 1.0 - (progress_angle / (2 * np.pi))
        
        self.set_progress(progress)
        self.seek_requested.emit(progress)
        super().mouseReleaseEvent(event)

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
    performance_mode_toggled = pyqtSignal(bool)
    
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
        
        # 性能模式按钮
        self.performance_mode_btn = QPushButton("性能模式")
        self.performance_mode_btn.setCheckable(True)
        self.performance_mode_btn.setStyleSheet('''
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
            QPushButton:checked {
                background: rgba(33,150,243,0.25);
                border: 1px solid rgba(33,150,243,0.4);
            }
        ''')
        self.performance_mode_btn.toggled.connect(self.performance_mode_toggled.emit)

        # 添加按钮到布局
        button_row.addWidget(self.download_btn)
        button_row.addWidget(self.select_file_btn)
        button_row.addWidget(self.delete_btn)
        button_row.addWidget(self.performance_mode_btn)
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
        self.playlist_widget.setAlternatingRowColors(False)  # 移除交替颜色
        self.playlist_widget.setStyleSheet('''
            QListWidget {
                background: transparent;
                border: none;
                color: white;
                font-size: 13px;
                padding-right: 5px; /* 为滚动条留出空间 */
            }
            QListWidget::item {
                padding: 8px 12px;
                border-bottom: 1px solid rgba(255,255,255,0.1);
            }
            QListWidget::item:selected {
                background: rgba(33,150,243,0.15);
                border-radius: 8px;
                color: #AACCFF;
            }

            /* --- 滚动条美化 --- */
            QScrollBar:vertical {
                border: none;
                background: rgba(0,0,0,0.1);
                width: 8px;
                margin: 0px 0 0px 0;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255,255,255,0.25);
                min-height: 20px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(255,255,255,0.35);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                border: none;
                background: none;
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }

            /* --- 水平滚动条美化 --- */
            QScrollBar:horizontal {
                border: none;
                background: rgba(0,0,0,0.1);
                height: 8px;
                margin: 0px 0 0px 0;
                border-radius: 4px;
            }
            QScrollBar::handle:horizontal {
                background: rgba(255,255,255,0.25);
                min-width: 20px;
                border-radius: 4px;
            }
            QScrollBar::handle:horizontal:hover {
                background: rgba(255,255,255,0.35);
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                border: none;
                background: none;
                width: 0px;
            }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: none;
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

class VolumeSlider(QSlider):
    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setRange(0, 100)
        self.setValue(100)
        self.setFixedWidth(120)
        self.setStyleSheet('''
            QSlider {
                background: transparent;
            }
            QSlider::groove:horizontal {
                background: rgba(255, 255, 255, 0.3);
                height: 4px;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: white;
                width: 14px;
                height: 14px;
                margin: -5px 0; 
                border-radius: 7px;
            }
            QSlider::sub-page:horizontal {
                background: rgba(33, 150, 243, 0.7);
                height: 4px;
                border-radius: 2px;
            }
        ''')
        
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
        self.setFixedSize(*self.config.WINDOW_SIZE)
        
        # 添加播放模式相关属性
        self.play_modes = ["sequence", "random", "single"]
        self.play_mode_icons = [
            get_resource_path("assets/icons/repeat.svg"),
            get_resource_path("assets/icons/shuffle.svg"),
            get_resource_path("assets/icons/repeat-one.svg")
        ]
        self.current_play_mode_index = 0
        self.play_mode = self.play_modes[self.current_play_mode_index]
        self.playlist_history = []  # 用于随机播放时记录历史
        self.current_index = -1  # 当前播放的索引
        
        self.setup_ui()
        self.setup_audio()
        self.bilibili_downloader = BilibiliDownloader()
        
        # 创建音频数据队列和频谱处理器
        self.audio_queue = queue.Queue(maxsize=10)
        self.spectrum_processor = SpectrumProcessor(self.config, self.audio_queue)
        self.spectrum_processor.start()
        self.is_downloading = False
        self.performance_mode_enabled = False

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
        control_panel.setStyleSheet('''
            background: rgba(255,255,255,0.18);
            border-radius: 18px;
            border: 1px solid rgba(255,255,255,0.3);
            font-family: '微软雅黑', 'Segoe UI', 'Arial', 'sans-serif';
        ''')
        self.playlist = CollapsiblePlaylist(self)
        self.playlist.play_signal.connect(self.play_file)
        self.playlist.performance_mode_toggled.connect(self.toggle_performance_mode)
        control_layout.addWidget(self.playlist)

        # 添加音量滑块
        self.volume_slider = VolumeSlider()
        self.volume_slider.valueChanged.connect(self.set_volume)
        self.volume_slider.setVisible(False)  # 默认隐藏
        
        volume_layout = QHBoxLayout()
        volume_layout.addStretch()
        volume_layout.addWidget(self.volume_slider)
        volume_layout.addStretch()
        control_layout.addLayout(volume_layout)
        
        control_panel.installEventFilter(self) # 安装事件过滤器
        
        content_layout.addWidget(control_panel)
        
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
        # **关键修复**: 移除下面的属性，允许进度条接收鼠标事件
        # progress_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        progress_overlay.setStyleSheet("background: transparent;")
        progress_layout = QVBoxLayout(progress_overlay)
        progress_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        progress_layout.addWidget(self.progress_bar)
        spectrum_main_layout.addWidget(progress_overlay, 0, 0)
        
        # --- 按钮 ---
        self.play_pause_btn = QPushButton(icon=QIcon(get_resource_path("assets/icons/play.svg")))
        self.play_pause_btn.clicked.connect(self.toggle_play)

        self.prev_btn = QPushButton(icon=QIcon(get_resource_path("assets/icons/prev.svg")))
        self.prev_btn.clicked.connect(self.play_previous)

        self.next_btn = QPushButton(icon=QIcon(get_resource_path("assets/icons/next.svg")))
        self.next_btn.clicked.connect(self.play_next)

        self.stop_btn = QPushButton(icon=QIcon(get_resource_path("assets/icons/stop.svg")))
        self.stop_btn.clicked.connect(self.stop)

        self.play_mode_btn = QPushButton(icon=QIcon(self.play_mode_icons[self.current_play_mode_index]))
        self.play_mode_btn.clicked.connect(self.toggle_play_mode)

        # **关键修复**: 统一所有按钮的尺寸和样式
        buttons = [self.play_pause_btn, self.prev_btn, self.next_btn, self.stop_btn, self.play_mode_btn]
        for btn in buttons:
            self.set_button_style(btn, size=self.config.CONTROL_BUTTON_SIZE)
            btn.setIconSize(QSize(self.config.CONTROL_BUTTON_ICON_SIZE, self.config.CONTROL_BUTTON_ICON_SIZE))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)

        # --- 按钮布局 (十字形) ---
        buttons_overlay = QWidget()
        buttons_overlay.setStyleSheet("background: transparent;")
        
        # **关键修复**: 网格布局直接作用在overlay上, 它的大小会自适应内容
        grid_layout = QGridLayout(buttons_overlay)
        grid_layout.setSpacing(15) # 设置按钮间的间距

        # 第0行: (空白), 播放模式, (空白)
        grid_layout.addWidget(self.play_mode_btn, 0, 1, Qt.AlignmentFlag.AlignCenter)
        
        # 第1行: 上一首, 播放/暂停, 下一首
        grid_layout.addWidget(self.prev_btn, 1, 0, Qt.AlignmentFlag.AlignCenter)
        grid_layout.addWidget(self.play_pause_btn, 1, 1, Qt.AlignmentFlag.AlignCenter)
        grid_layout.addWidget(self.next_btn, 1, 2, Qt.AlignmentFlag.AlignCenter)

        # 第2行: (空白), 停止, (空白)
        grid_layout.addWidget(self.stop_btn, 2, 1, Qt.AlignmentFlag.AlignCenter)
        
        # **关键修复**: 将只包含按钮的、尺寸自适应的overlay居中放置在顶层
        # 这样它就不会拦截到旁边进度条的点击事件
        spectrum_main_layout.addWidget(buttons_overlay, 0, 0, Qt.AlignmentFlag.AlignCenter)

        content_layout.addWidget(spectrum_main_container)
        
        self.bg_widget.setLayout(content_layout)

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_spectrum)
        self.timer.start(self.config.UI_UPDATE_INTERVAL_MS)

        self.bg_timer = QTimer()
        self.bg_timer.timeout.connect(self.update_background)
        self.bg_phase = 0
        self.bg_timer.start(50)

        self.stop_btn.setEnabled(False)
        
        self.playlist.download_btn.clicked.connect(self.download_bilibili_audio)

        # 连接进度条跳转信号
        self.progress_bar.seek_requested.connect(self.seek_playback)

    def set_button_style(self, btn, size=40):
        btn.setFixedSize(size, size)
        btn.setStyleSheet(f'''
            QPushButton {{
                background: rgba(255,255,255,0.25);
                border: none;
                border-radius: {size // 2}px;
            }}
            QPushButton:hover {{
                background: rgba(33,150,243,0.12);
            }}
            QPushButton:pressed {{
                background: rgba(33,150,243,0.18);
            }}
        ''')

    def update_background(self):
        self.bg_phase = (self.bg_phase + 0.01) % (2 * np.pi)
        self.bg_widget.bg_phase = self.bg_phase

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
        self.play_pause_btn.setIcon(QIcon(get_resource_path("assets/icons/pause.svg")))
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
            self.play_pause_btn.setIcon(QIcon(get_resource_path("assets/icons/play.svg")))
            # 清空频谱
            self.spectrum.update_spectrum(np.zeros(self.config.NUM_BARS), self.start_time)
        else:
            self.player.resume()
            self.is_playing = True
            self.play_pause_btn.setIcon(QIcon(get_resource_path("assets/icons/pause.svg")))

    def stop(self):
        if self.player:
            self.player.stop()
            self.is_playing = False
            self.play_pause_btn.setIcon(QIcon(get_resource_path("assets/icons/play.svg")))
            # 清空频谱
            self.spectrum.update_spectrum(np.zeros(self.config.NUM_BARS), self.start_time)

    def update_spectrum(self):
        if self.player:
            # --- 进度条更新 (始终执行) ---
            try:
                pos = self.player.get_position()
                dur = self.player.get_duration()
                progress = pos / dur if dur > 0 else 0
                self.progress_bar.set_progress(progress)
            except Exception:
                self.progress_bar.set_progress(0)

            # --- 频谱更新 (如果性能模式关闭) ---
            if not self.performance_mode_enabled:
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
        else:
            # --- 没有播放器时，将所有内容归零 ---
            self.progress_bar.set_progress(0)
            if not self.performance_mode_enabled:
                heights = np.zeros(self.config.NUM_BARS)
                self.spectrum.update_spectrum(heights, self.start_time)

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
        if self.is_downloading:
            return
        
        self.is_downloading = True
        try:
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
        finally:
            self.is_downloading = False

    def toggle_play_mode(self):
        """切换播放模式"""
        self.current_play_mode_index = (self.current_play_mode_index + 1) % len(self.play_modes)
        self.play_mode = self.play_modes[self.current_play_mode_index]
        self.play_mode_btn.setIcon(QIcon(self.play_mode_icons[self.current_play_mode_index]))

    def set_play_mode(self, mode):
        """设置播放模式"""
        try:
            idx = self.play_modes.index(mode)
            self.current_play_mode_index = idx
            self.play_mode = mode
            self.play_mode_btn.setIcon(QIcon(self.play_mode_icons[idx]))
        except ValueError:
            print(f"警告: 未知的播放模式 '{mode}'")

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
            self.play_pause_btn.setIcon(QIcon(get_resource_path("assets/icons/pause.svg"))) 

    def toggle_performance_mode(self, checked):
        """切换性能模式"""
        self.performance_mode_enabled = checked
        self.spectrum.setVisible(not checked)

    def eventFilter(self, source, event):
        """事件过滤器，用于处理音量条的显示和隐藏"""
        if source.isWidgetType() and source.styleSheet(): # 确保是我们的带样式的面板
            if event.type() == event.Type.Enter:
                self.volume_slider.setVisible(True)
            elif event.type() == event.Type.Leave:
                self.volume_slider.setVisible(False)
        return super().eventFilter(source, event)

    def set_volume(self, value):
        """设置音量"""
        if self.player:
            self.player.set_volume(value / 100.0)

def main():
    # 开启全局抗锯齿，使频谱更平滑
    pg.setConfigOptions(antialias=True)
    app = QApplication(sys.argv)
    window = PlayerWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
