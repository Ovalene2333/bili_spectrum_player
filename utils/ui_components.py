import numpy as np
import time
from PySide6.QtWidgets import QWidget, QSlider
from PySide6.QtCore import Qt, Signal, QSize, QPoint, QPointF
from PySide6.QtGui import QPainter, QLinearGradient, QColor, QPen, QPalette
from .config import Config


class EventLoggingWidget(QWidget):
    def mousePressEvent(self, event):
        super().mousePressEvent(event)


class SpectrumGLWidget(QWidget):
    VIRTUAL_SIZE = 500

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self._config = config
        self._heights = np.zeros(config.NUM_BARS, dtype=np.float32)
        self._start_time = time.time()

        self._base_angles = (np.pi / 2 + np.linspace(
            0, 2 * np.pi, config.NUM_BARS, endpoint=False, dtype=np.float32
        ))

        self._color_map = np.array(config.COLOR_MAP_COLORS, dtype=np.float32) / 255.0
        self._color_positions = np.array(config.COLOR_POSITIONS, dtype=np.float32)

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)

        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, Qt.GlobalColor.transparent)
        self.setPalette(palette)

    def minimumSizeHint(self):
        return QSize(280, 280)

    def update_spectrum(self, heights, start_time):
        self._heights = np.asarray(heights, dtype=np.float32)
        self._start_time = start_time
        self.update()

    def _scale_factor(self):
        w = self.width()
        h = self.height()
        if w <= 0 or h <= 0:
            return 0.0
        return max(0.65, min(2.0, min(w, h) / self.VIRTUAL_SIZE))

    def paintEvent(self, event):
        scale = self._scale_factor()
        if scale <= 0.0:
            return

        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

            config = self._config
            heights = self._heights
            num_bars = config.NUM_BARS
            bar_width_scaled = max(1.0, config.BAR_WIDTH * scale)

            elapsed = max(0.0, time.time() - self._start_time)
            rotation = elapsed * config.ROTATION_SPEED_RAD_PER_SEC

            cx = self.width() / 2.0
            cy = self.height() / 2.0

            norm_heights = np.clip(heights / config.MAX_DB_VALUE, 0.0, 1.0)
            colors = np.zeros((num_bars, 4), dtype=np.float32)
            colors[:, 0] = np.interp(norm_heights, self._color_positions, self._color_map[:, 0])
            colors[:, 1] = np.interp(norm_heights, self._color_positions, self._color_map[:, 1])
            colors[:, 2] = np.interp(norm_heights, self._color_positions, self._color_map[:, 2])
            colors[:, 3] = np.interp(norm_heights, self._color_positions, self._color_map[:, 3])

            inner_r = config.INNER_RADIUS * scale
            max_amp = config.MAX_AMPLITUDE_RADIUS * scale

            for i in range(num_bars):
                angle = self._base_angles[i] + rotation
                cos_a = np.cos(angle)
                sin_a = np.sin(angle)

                outer_r = inner_r + norm_heights[i] * max_amp
                if outer_r <= inner_r:
                    outer_r = inner_r + 1.0

                x1 = cx + cos_a * inner_r
                y1 = cy + sin_a * inner_r
                x2 = cx + cos_a * outer_r
                y2 = cy + sin_a * outer_r

                r = int(colors[i, 0] * 255)
                g = int(colors[i, 1] * 255)
                b = int(colors[i, 2] * 255)
                a = int(colors[i, 3] * 255)

                pen = QPen(QColor(r, g, b, a))
                pen.setWidthF(bar_width_scaled)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(pen)
                painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        finally:
            painter.end()


SpectrumWidget = SpectrumGLWidget


class GradientWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._bg_phase = 0
        self.setAutoFillBackground(True)
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
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        grad = QLinearGradient(0, 0, self.width(), self.height())
        c1 = QColor.fromHsvF((0.6 + 0.2 * np.sin(self._bg_phase)) % 1, 0.5, 1, 1)
        c2 = QColor.fromHsvF((0.9 + 0.2 * np.cos(self._bg_phase)) % 1, 0.5, 1, 1)
        grad.setColorAt(0, c1)
        grad.setColorAt(1, c2)
        painter.fillRect(self.rect(), grad)


class CircularProgressBar(QWidget):
    seek_requested = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.progress = 0
        self.setMinimumSize(150, 150)

    def sizeHint(self):
        return QSize(Config.PROGRESS_BAR_RADIUS * 2, Config.PROGRESS_BAR_RADIUS * 2)

    def set_progress(self, value):
        self.progress = value
        self.update()

    def mousePressEvent(self, event):
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        center = self.rect().center()
        vec = event.pos() - center
        angle_rad = np.arctan2(-vec.y(), vec.x())
        progress_angle = (angle_rad - np.pi / 2 + 2 * np.pi) % (2 * np.pi)
        progress = 1.0 - (progress_angle / (2 * np.pi))
        self.set_progress(progress)
        self.seek_requested.emit(progress)
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            base_size = Config.PROGRESS_BAR_RADIUS * 2
            scale = min(self.width(), self.height()) / base_size if base_size else 1
            pen_width = max(4, int(Config.PROGRESS_BAR_WIDTH * scale))

            margin = (pen_width // 2) + 1
            paint_rect = self.rect().adjusted(margin, margin, -margin, -margin)

            bg_pen = QPen(Config.PROGRESS_BAR_BG_COLOR, pen_width, Qt.PenStyle.SolidLine)
            painter.setPen(bg_pen)
            painter.drawEllipse(paint_rect)

            progress_pen = QPen(Config.PROGRESS_BAR_COLOR, pen_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            painter.setPen(progress_pen)

            start_angle = 90 * 16
            span_angle = int(-self.progress * 360 * 16)

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
        self.setFixedSize(48, 48)

    def set_playing(self, playing):
        self.is_playing = playing
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            pen = QPen(QColor(255, 255, 255))
            pen.setWidth(3)
            painter.setPen(pen)

            if self.is_playing:
                bar_width = 8
                gap = 8
                left = (self.width() - (bar_width * 2 + gap)) / 2
                top = (self.height() - 32) / 2
                painter.drawRect(int(left), int(top), bar_width, 32)
                painter.drawRect(int(left + bar_width + gap), int(top), bar_width, 32)
            else:
                points = [
                    (self.width() * 0.3, self.height() * 0.2),
                    (self.width() * 0.3, self.height() * 0.8),
                    (self.width() * 0.8, self.height() * 0.5),
                ]
                painter.drawPolygon([QPoint(int(x), int(y)) for x, y in points])
        finally:
            painter.end()
