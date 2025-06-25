import os
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor
from PyQt6.QtCore import Qt
from PyQt6.QtSvg import QSvgRenderer
from .config import ASSETS_PATH


def create_icon(path, color="white"):
    """从SVG文件创建并着色QIcon"""
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
    """格式化时间显示"""
    if seconds is None or seconds < 0:
        return "00:00"
    minutes = int(seconds // 60)
    seconds = int(seconds % 60)
    return f"{minutes:02d}:{seconds:02d}"


def ensure_directory_exists(path):
    """确保目录存在，如果不存在则创建"""
    if not os.path.exists(path):
        try:
            os.makedirs(path)
            return True
        except OSError as e:
            print(f"无法创建目录 {path}: {e}")
            return False
    return True


def get_icon_path(icon_name):
    """获取图标文件的完整路径"""
    return os.path.join(ASSETS_PATH, "icons", icon_name) 