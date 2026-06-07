import os
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor
from PySide6.QtCore import Qt
from PySide6.QtSvg import QSvgRenderer
from .config import ASSETS_PATH


def create_icon(path, color="white"):
    renderer = QSvgRenderer(path)
    pixmap = QPixmap(renderer.defaultSize())
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(pixmap.rect(), QColor(color))
    painter.end()
    return QIcon(pixmap)


def format_time(seconds):
    if seconds is None or seconds < 0:
        return "00:00"
    minutes = int(seconds // 60)
    seconds = int(seconds % 60)
    return f"{minutes:02d}:{seconds:02d}"


def ensure_directory_exists(path):
    if not os.path.exists(path):
        try:
            os.makedirs(path)
            return True
        except OSError as e:
            print(f"无法创建目录 {path}: {e}")
            return False
    return True


def get_icon_path(icon_name):
    return os.path.join(ASSETS_PATH, "icons", icon_name)
