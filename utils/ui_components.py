import numpy as np
import pyqtgraph as pg
import time
from PyQt6.QtWidgets import QWidget, QSlider, QListWidget
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QPoint
from PyQt6.QtGui import QPainter, QLinearGradient, QColor, QPen
from .config import Config


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
        
        # 优化：预创建所有 PlotDataItem 并缓存画笔
        self.bar_items = []
        self._cached_pens = {}  # 缓存画笔对象以避免重复创建
        for _ in range(self.config.NUM_BARS):
            item = pg.PlotDataItem()
            self.plot_item.addItem(item)
            self.bar_items.append(item)

        self.angles_rad_base = np.pi / 2 + np.linspace(0, 2 * np.pi, self.config.NUM_BARS, endpoint=False)
        self._last_display_heights = np.zeros(self.config.NUM_BARS)
        self.start_time = 0
        self.setBackground(None)
        self.setStyleSheet("background: transparent;")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def resizeEvent(self, event):
        # 尺寸调整时不再需要特殊处理，因为画笔宽度在update_spectrum中设置
        super().resizeEvent(event)

    def update_spectrum(self, heights, start_time):
        config = self.config
        # heights_clipped = np.clip(heights, 0, config.MAX_DB_VALUE)
        
        radii_outer = (
            config.INNER_RADIUS
            + config.MIN_RADIUS_OFFSET
            + (config.MAX_AMPLITUDE_RADIUS / config.MAX_DB_VALUE) * heights
        )
        if config.NUM_BARS > 1:
            avg_radius_edge = (radii_outer[0] + radii_outer[-1]) / 2.0
            radii_outer[-1] = avg_radius_edge
            
        elapsed_time = time.time() - start_time
        rotation_offset = elapsed_time * config.ROTATION_SPEED_RAD_PER_SEC
        current_angles = self.angles_rad_base + rotation_offset
        current_cos = np.cos(current_angles)
        current_sin = np.sin(current_angles)
        
        normalized_heights = heights / config.MAX_DB_VALUE
        bar_q_colors = self.color_map.mapToQColor(normalized_heights)
        
        # 优化：批量计算所有坐标
        inner_x = config.INNER_RADIUS * current_cos
        inner_y = config.INNER_RADIUS * current_sin
        outer_x = radii_outer * current_cos
        outer_y = radii_outer * current_sin
        
        # 优化：只更新数据，使用缓存的画笔避免重复创建
        for i in range(config.NUM_BARS):
            # 获取或创建缓存的画笔
            color_key = (bar_q_colors[i].red(), bar_q_colors[i].green(), 
                        bar_q_colors[i].blue(), bar_q_colors[i].alpha())
            if color_key not in self._cached_pens:
                self._cached_pens[color_key] = pg.mkPen(color=bar_q_colors[i], width=self.config.BAR_WIDTH)
            
            # 一次性设置所有数据
            x_data = [inner_x[i], outer_x[i]]
            y_data = [inner_y[i], outer_y[i]]
            self.bar_items[i].setData(x=x_data, y=y_data, pen=self._cached_pens[color_key])


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


class VolumeSlider(QSlider):
    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setRange(0, 100)
        self.setValue(100)
        self.setFixedWidth(120)


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