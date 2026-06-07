import os
import subprocess
import sys
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QComboBox, QLineEdit,
    QListWidget, QListWidgetItem, QMenu, QMessageBox, QDialog
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QFont
from .config import ASSETS_PATH
from .helpers import create_icon, get_icon_path
from .dialogs import PlaylistManagerDialog


class CollapsiblePlaylist(QWidget):
    play_signal = Signal(str)
    performance_mode_toggled = Signal(bool)
    add_music_requested = Signal()
    add_to_next_play_requested = Signal(str)
    locate_current_song_requested = Signal()

    def __init__(self, parent=None, playlist_manager=None):
        super().__init__(parent)
        self.playlist_manager = playlist_manager
        self.setup_ui()
        self.refresh_playlist_display()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        top_row_layout = QHBoxLayout()
        top_row_layout.setSpacing(8)

        self.playlist_combo = QComboBox()
        self.playlist_combo.setObjectName("PlaylistCombo")
        self.playlist_combo.currentTextChanged.connect(self.on_playlist_changed)
        top_row_layout.addWidget(self.playlist_combo)

        self.add_music_btn = QPushButton()
        self.add_music_btn.setIcon(create_icon(get_icon_path("add.svg")))
        self.add_music_btn.setObjectName("AddMusicButton")
        self.add_music_btn.setToolTip("添加音乐")
        self.add_music_btn.setFixedSize(32, 32)
        self.add_music_btn.clicked.connect(self.add_music_requested.emit)
        top_row_layout.addWidget(self.add_music_btn)

        self.locate_btn = QPushButton()
        self.locate_btn.setIcon(create_icon(get_icon_path("locate.svg")))
        self.locate_btn.setObjectName("LocateButton")
        self.locate_btn.setToolTip("定位当前歌曲")
        self.locate_btn.setFixedSize(32, 32)
        self.locate_btn.clicked.connect(self.locate_current_song_requested.emit)
        top_row_layout.addWidget(self.locate_btn)

        self.performance_mode_btn = QPushButton()
        self.performance_mode_btn.setIcon(create_icon(get_icon_path("performance.svg")))
        self.performance_mode_btn.setCheckable(True)
        self.performance_mode_btn.setObjectName("PerformanceModeButton")
        self.performance_mode_btn.setToolTip("性能模式")
        self.performance_mode_btn.setFixedSize(32, 32)
        self.performance_mode_btn.toggled.connect(self.performance_mode_toggled.emit)
        top_row_layout.addWidget(self.performance_mode_btn)

        self.equalizer_btn = QPushButton()
        self.equalizer_btn.setText("EQ")
        self.equalizer_btn.setObjectName("EqualizerButton")
        self.equalizer_btn.setToolTip("均衡器")
        self.equalizer_btn.setFixedSize(32, 32)
        top_row_layout.addWidget(self.equalizer_btn)

        self.settings_btn = QPushButton()
        self.settings_btn.setIcon(create_icon(get_icon_path("settings.svg")))
        self.settings_btn.setObjectName("SettingsButton")
        self.settings_btn.setToolTip("设置")
        self.settings_btn.setFixedSize(32, 32)
        top_row_layout.addWidget(self.settings_btn)

        bold_font = QFont()
        bold_font.setBold(True)
        for i in range(top_row_layout.count()):
            widget = top_row_layout.itemAt(i).widget()
            if isinstance(widget, QPushButton):
                widget.setFont(bold_font)
                widget.setIconSize(QSize(20, 20))

        layout.addLayout(top_row_layout)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("搜索播放列表...")
        self.search_box.setObjectName("SearchBox")
        self.search_box.textChanged.connect(self.filter_playlist)
        layout.addWidget(self.search_box)

        self.playlist_widget = QListWidget()
        self.playlist_widget.setAlternatingRowColors(False)
        self.playlist_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.playlist_widget.customContextMenuRequested.connect(self.show_context_menu)
        self.playlist_widget.setStyleSheet('''
            QListWidget {
                background: transparent;
                border: none;
                color: white;
                font-size: 13px;
                font-weight: bold;
                padding-right: 5px;
            }
            QListWidget::item {
                padding: 8px 12px;
                border-bottom: 1px solid rgba(255,255,255,0.1);
            }
            QListWidget::item:selected {
                background: rgba(33,150,243,0.45);
                border-radius: 8px;
                color: #FFFFFF;
            }
            QListWidget::item:selected:!active {
                background: rgba(33,150,243,0.38);
                color: #FFFFFF;
            }

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
        self.playlist_widget.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.playlist_widget.model().rowsMoved.connect(self.on_item_moved)
        layout.addWidget(self.playlist_widget)

        manage_button_layout = QHBoxLayout()
        manage_button_layout.setSpacing(8)

        self.manage_playlist_btn = QPushButton("管理播放列表")
        self.manage_playlist_btn.setObjectName("ManagePlaylistButton")
        self.manage_playlist_btn.setToolTip("创建、删除和管理播放列表")
        self.manage_playlist_btn.clicked.connect(self.manage_playlists)
        manage_button_layout.addWidget(self.manage_playlist_btn)

        self.manage_playlist_btn.setFont(bold_font)

        layout.addLayout(manage_button_layout)

    def filter_playlist(self, text):
        for i in range(self.playlist_widget.count()):
            item = self.playlist_widget.item(i)
            file_name = os.path.basename(item.data(Qt.ItemDataRole.UserRole))
            item.setHidden(text.lower() not in file_name.lower())

    def on_item_double_clicked(self, item):
        file_path = item.data(Qt.ItemDataRole.UserRole)
        self.play_signal.emit(file_path)

    def add_item(self, file_path):
        if self.playlist_manager:
            current_playlist = self.playlist_manager.current_playlist
            if self.playlist_manager.add_to_playlist(current_playlist, file_path):
                self.refresh_playlist_display()

    def show_context_menu(self, position):
        if not self.playlist_widget.itemAt(position):
            return

        menu = QMenu(self)
        menu.setObjectName("ContextMenu")

        play_action = menu.addAction("播放")
        play_action.triggered.connect(lambda: self.on_item_double_clicked(self.playlist_widget.itemAt(position)))

        next_play_action = menu.addAction("下一首播放")
        next_play_action.triggered.connect(lambda: self.add_to_next_play(position))

        open_location_action = menu.addAction("打开文件位置")
        open_location_action.triggered.connect(lambda: self.open_file_location(position))

        menu.addSeparator()

        remove_action = menu.addAction("从播放列表移除")
        remove_action.triggered.connect(lambda: self.remove_from_playlist(position))

        delete_file_action = menu.addAction("删除文件（永久删除）")
        delete_file_action.triggered.connect(lambda: self.delete_file_permanently(position))

        menu.exec(self.playlist_widget.mapToGlobal(position))

    def add_to_next_play(self, position):
        item = self.playlist_widget.itemAt(position)
        if item:
            file_path = item.data(Qt.ItemDataRole.UserRole)
            self.add_to_next_play_requested.emit(file_path)

    def open_file_location(self, position):
        item = self.playlist_widget.itemAt(position)
        if not item:
            return

        file_path = item.data(Qt.ItemDataRole.UserRole)
        if not os.path.exists(file_path):
            QMessageBox.warning(self, "文件不存在", f"文件 '{os.path.basename(file_path)}' 不存在")
            return

        try:
            if sys.platform == "win32":
                subprocess.run(['explorer', '/select,', os.path.normpath(file_path)], check=False)
            elif sys.platform == "darwin":
                subprocess.run(['open', '-R', file_path], check=False)
            else:
                file_dir = os.path.dirname(file_path)
                file_managers = ['nautilus', 'dolphin', 'thunar', 'pcmanfm', 'caja']
                for fm in file_managers:
                    try:
                        subprocess.run([fm, file_dir], check=True)
                        break
                    except (subprocess.CalledProcessError, FileNotFoundError):
                        continue
                else:
                    subprocess.run(['xdg-open', file_dir], check=False)

        except Exception as e:
            QMessageBox.critical(self, "打开失败", f"无法打开文件位置：{str(e)}")

    def remove_from_playlist(self, position):
        item = self.playlist_widget.itemAt(position)
        if item and self.playlist_manager:
            file_path = item.data(Qt.ItemDataRole.UserRole)
            current_playlist = self.playlist_manager.current_playlist
            if self.playlist_manager.remove_from_playlist(current_playlist, file_path):
                self.refresh_playlist_content_only()

    def delete_file_permanently(self, position):
        item = self.playlist_widget.itemAt(position)
        if not item:
            return

        file_path = item.data(Qt.ItemDataRole.UserRole)
        file_name = os.path.basename(file_path)

        reply = QMessageBox.question(
            self,
            '确认删除文件',
            f'确定要永久删除文件 "{file_name}" 吗？\n\n警告：此操作不可撤销！',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                if self.playlist_manager:
                    for playlist_name in self.playlist_manager.get_playlist_names():
                        self.playlist_manager.remove_from_playlist(playlist_name, file_path)

                if os.path.exists(file_path):
                    os.remove(file_path)
                    QMessageBox.information(self, "删除成功", f"文件 '{file_name}' 已被删除")
                else:
                    QMessageBox.warning(self, "文件不存在", f"文件 '{file_name}' 不存在")

                self.refresh_playlist_content_only()

            except Exception as e:
                QMessageBox.critical(self, "删除失败", f"无法删除文件：{str(e)}")

    def on_playlist_changed(self, playlist_name):
        if self.playlist_manager and playlist_name and playlist_name != self.playlist_manager.current_playlist:
            self.playlist_manager.set_current_playlist(playlist_name)
            self.refresh_playlist_content_only()

    def manage_playlists(self):
        dialog = PlaylistManagerDialog(self, self.playlist_manager)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh_playlist_combo()
            self.refresh_playlist_display()

    def refresh_playlist_combo(self):
        if not self.playlist_manager:
            return

        self.playlist_combo.currentTextChanged.disconnect()

        try:
            current_text = self.playlist_combo.currentText()
            self.playlist_combo.clear()

            playlist_names = self.playlist_manager.get_playlist_names()
            self.playlist_combo.addItems(playlist_names)

            target_playlist = self.playlist_manager.current_playlist
            if target_playlist in playlist_names:
                self.playlist_combo.setCurrentText(target_playlist)
            elif playlist_names:
                self.playlist_combo.setCurrentText(playlist_names[0])

        finally:
            self.playlist_combo.currentTextChanged.connect(self.on_playlist_changed)

    def refresh_playlist_display(self):
        if not self.playlist_manager:
            return

        self.refresh_playlist_combo()
        self.refresh_playlist_content_only()

    def refresh_playlist_content_only(self):
        if not self.playlist_manager:
            return

        self.playlist_widget.clear()
        current_playlist = self.playlist_manager.current_playlist
        playlist = self.playlist_manager.get_playlist(current_playlist)

        for file_path in playlist:
            if os.path.exists(file_path):
                item = QListWidgetItem(os.path.basename(file_path))
                item.setData(Qt.ItemDataRole.UserRole, file_path)
                self.playlist_widget.addItem(item)

    def on_item_moved(self, parent, start, end, destination, row):
        if self.playlist_manager:
            current_playlist = self.playlist_manager.current_playlist
            self.playlist_manager.move_in_playlist(current_playlist, start, row)

    def locate_current_song(self, current_file_path):
        if not current_file_path:
            return

        for i in range(self.playlist_widget.count()):
            item = self.playlist_widget.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == current_file_path:
                self.playlist_widget.setCurrentRow(i)
                self.playlist_widget.scrollToItem(item, QListWidget.ScrollHint.PositionAtCenter)
                return

        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(self, "提示", "当前播放的歌曲不在播放列表中")
