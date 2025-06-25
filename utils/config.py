import sys
import os
import numpy as np
from PyQt6.QtGui import QColor

# --- 路径定义 ---
# 无论从何处运行，都能找到正确的资源路径
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    # 如果应用被 PyInstaller 打包
    application_path = sys._MEIPASS
else:
    application_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ASSETS_PATH = os.path.join(application_path, 'assets')
CONFIG_PATH = os.path.join(application_path, 'config')

# 确保config目录存在
if not os.path.exists(CONFIG_PATH):
    os.makedirs(CONFIG_PATH)


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
    UI_UPDATE_INTERVAL_MS = 25
    COLOR_POSITIONS = [0.0, 0.2, 0.4, 0.8]
    COLOR_MAP_COLORS = [
        (40, 0, 60, 180),
        (100, 0, 180, 255),
        (255, 0, 150, 255),
        (255, 180, 255, 255),
    ]
    PLAYLIST_FILE = os.path.join(CONFIG_PATH, "playlist.json")
    SETTINGS_FILE = os.path.join(CONFIG_PATH, "settings.json")
    
    # --- 项目信息 ---
    GITHUB_URL = "https://github.com/Ovalene2333/bili_spectrum_player"  # 请替换
    DEFAULT_DOWNLOAD_PATH = os.path.join(application_path, 'downloads')

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