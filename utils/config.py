import sys
import os
import numpy as np
from PySide6.QtGui import QColor


if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    application_path = sys._MEIPASS
else:
    application_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ASSETS_PATH = os.path.join(application_path, 'assets')
CONFIG_PATH = os.path.join(application_path, 'config')

if not os.path.exists(CONFIG_PATH):
    os.makedirs(CONFIG_PATH)


class Config:
    SAMPLE_RATE = 44100
    CHUNK_SIZE = 1024
    MAX_FREQ = 8000
    NUM_BARS = 100
    MAX_DB_VALUE = 90.0

    INNER_RADIUS = 120
    MAX_AMPLITUDE_RADIUS = 100
    MIN_RADIUS_OFFSET = 2.
    BAR_WIDTH = 3.0

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

    GITHUB_URL = "https://github.com/Ovalene2333/bili_spectrum_player"
    DEFAULT_DOWNLOAD_PATH = os.path.join(application_path, 'downloads')

    SPECTRUM_INNER_COLOR = QColor("#43e97b")
    SPECTRUM_OUTER_COLOR = QColor("#38f9d7")

    PROGRESS_BAR_RADIUS = 115
    PROGRESS_BAR_WIDTH = 12
    PROGRESS_BAR_COLOR = QColor(255, 255, 255, 100)
    PROGRESS_BAR_BG_COLOR = QColor(255, 255, 255, 50)

    CONTROL_BUTTON_SIZE = 40
    CONTROL_BUTTON_ICON_SIZE = 32

    NUM_LOW_FREQ_BARS = 5
    LOW_FREQ_WAVE_NUM_POINTS = 360
    LOW_FREQ_WAVE_BASE_RADIUS = 125
    LOW_FREQ_WAVE_AMPLITUDE = 30
    LOW_FREQ_WAVE_WIDTH = 2.5
    LOW_FREQ_WAVE_COLOR = QColor(100, 200, 255, 220)
