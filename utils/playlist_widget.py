import os
import subprocess
import sys
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QComboBox, QLineEdit,
    QListWidget, QListWidgetItem, QMenu, QMessageBox, QDialog
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QFont
from .config import ASSETS_PATH
from .helpers import create_icon, get_icon_path
from .dialogs import PlaylistManagerDialog


class CollapsiblePlaylist(QWidget):
    play_signal = pyqtSignal(str)
    performance_mode_toggled = pyqtSignal(bool)
    add_music_requested = pyqtSignal()
    add_to_next_play_requested = pyqtSignal(str)  # 添加到下一首播放信号
    locate_current_song_requested = pyqtSignal()  # 定位当前歌曲信号
    
    def __init__(self, parent=None, playlist_manager=None):
        super().__init__(parent)
        self.playlist_manager = playlist_manager
        self.setup_ui()
        self.refresh_playlist_display()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        
        # 播放列表选择下拉框和功能按钮在同一行
        top_row_layout = QHBoxLayout()
        top_row_layout.setSpacing(8)
        
        # 播放列表选择下拉框
        self.playlist_combo = QComboBox()
        self.playlist_combo.setObjectName("PlaylistCombo")
        self.playlist_combo.currentTextChanged.connect(self.on_playlist_changed)
        top_row_layout.addWidget(self.playlist_combo)
        
        # 添加音乐按钮
        self.add_music_btn = QPushButton()
        self.add_music_btn.setIcon(create_icon(get_icon_path("add.svg")))
        self.add_music_btn.setObjectName("AddMusicButton")
        self.add_music_btn.setToolTip("添加音乐")
        self.add_music_btn.setFixedSize(32, 32)
        self.add_music_btn.clicked.connect(self.add_music_requested.emit)
        top_row_layout.addWidget(self.add_music_btn)
        
        # 定位当前歌曲按钮
        self.locate_btn = QPushButton()
        self.locate_btn.setIcon(create_icon(get_icon_path("locate.svg")))
        self.locate_btn.setObjectName("LocateButton")
        self.locate_btn.setToolTip("定位当前歌曲")
        self.locate_btn.setFixedSize(32, 32)
        self.locate_btn.clicked.connect(self.locate_current_song_requested.emit)
        top_row_layout.addWidget(self.locate_btn)
        
        # 性能模式按钮（改为图标）
        self.performance_mode_btn = QPushButton()
        self.performance_mode_btn.setIcon(create_icon(get_icon_path("performance.svg")))
        self.performance_mode_btn.setCheckable(True)
        self.performance_mode_btn.setObjectName("PerformanceModeButton")
        self.performance_mode_btn.setToolTip("性能模式")
        self.performance_mode_btn.setFixedSize(32, 32)
        self.performance_mode_btn.toggled.connect(self.performance_mode_toggled.emit)
        top_row_layout.addWidget(self.performance_mode_btn)
        
        # 设置按钮
        self.settings_btn = QPushButton()
        self.settings_btn.setIcon(create_icon(get_icon_path("settings.svg")))
        self.settings_btn.setObjectName("SettingsButton")
        self.settings_btn.setToolTip("设置")
        self.settings_btn.setFixedSize(32, 32)
        top_row_layout.addWidget(self.settings_btn)

        # 统一设置按钮字体为粗体和图标尺寸
        bold_font = QFont()
        bold_font.setBold(True)
        for i in range(top_row_layout.count()):
            widget = top_row_layout.itemAt(i).widget()
            if isinstance(widget, QPushButton):
                widget.setFont(bold_font)
                # 为图标按钮设置图标尺寸
                widget.setIconSize(QSize(20, 20))
                
        layout.addLayout(top_row_layout)
        
        # 创建搜索框
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("搜索播放列表...")
        self.search_box.setObjectName("SearchBox")
        self.search_box.textChanged.connect(self.filter_playlist)
        layout.addWidget(self.search_box)

        # 创建播放列表
        self.playlist_widget = QListWidget()
        self.playlist_widget.setAlternatingRowColors(False)  # 移除交替颜色
        self.playlist_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.playlist_widget.customContextMenuRequested.connect(self.show_context_menu)
        self.playlist_widget.setStyleSheet('''
            QListWidget {
                background: transparent;
                border: none;
                color: white;
                font-size: 13px;
                font-weight: bold; /* 字体加粗 */
                padding-right: 5px; /* 为滚动条留出空间 */
            }
            QListWidget::item {
                padding: 8px 12px;
                border-bottom: 1px solid rgba(255,255,255,0.1);
            }
            QListWidget::item:selected {
                background: rgba(33,150,243,0.25);
                border-radius: 8px;
                color: #BBBBBB; /* 将选中项文字颜色改为灰色 */
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
        # 启用拖放
        self.playlist_widget.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.playlist_widget.model().rowsMoved.connect(self.on_item_moved)
        layout.addWidget(self.playlist_widget)
        
        # 播放列表管理按钮，移到播放列表下方
        manage_button_layout = QHBoxLayout()
        manage_button_layout.setSpacing(8)
        
        # 播放列表管理按钮
        self.manage_playlist_btn = QPushButton("管理播放列表")
        self.manage_playlist_btn.setObjectName("ManagePlaylistButton") 
        self.manage_playlist_btn.setToolTip("创建、删除和管理播放列表")
        self.manage_playlist_btn.clicked.connect(self.manage_playlists)
        manage_button_layout.addWidget(self.manage_playlist_btn)
        
        # 设置管理按钮的字体
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
        """添加文件到当前播放列表"""
        if self.playlist_manager:
            current_playlist = self.playlist_manager.current_playlist
            if self.playlist_manager.add_to_playlist(current_playlist, file_path):
                self.refresh_playlist_display()

    def show_context_menu(self, position):
        """显示右键菜单"""
        if not self.playlist_widget.itemAt(position):
            return
            
        menu = QMenu(self)
        menu.setObjectName("ContextMenu")
        
        # 播放
        play_action = menu.addAction("播放")
        play_action.triggered.connect(lambda: self.on_item_double_clicked(self.playlist_widget.itemAt(position)))
        
        # 下一首播放
        next_play_action = menu.addAction("下一首播放")
        next_play_action.triggered.connect(lambda: self.add_to_next_play(position))
        
        # 打开文件位置
        open_location_action = menu.addAction("打开文件位置")
        open_location_action.triggered.connect(lambda: self.open_file_location(position))
        
        # 分隔线
        menu.addSeparator()
        
        # 从播放列表移除
        remove_action = menu.addAction("从播放列表移除")
        remove_action.triggered.connect(lambda: self.remove_from_playlist(position))
        
        # 删除文件（永久删除）
        delete_file_action = menu.addAction("删除文件（永久删除）")
        delete_file_action.triggered.connect(lambda: self.delete_file_permanently(position))
        
        menu.exec(self.playlist_widget.mapToGlobal(position))
    
    def add_to_next_play(self, position):
        """添加到下一首播放队列"""
        item = self.playlist_widget.itemAt(position)
        if item:
            file_path = item.data(Qt.ItemDataRole.UserRole)
            self.add_to_next_play_requested.emit(file_path)
    
    def open_file_location(self, position):
        """打开文件位置"""
        item = self.playlist_widget.itemAt(position)
        if not item:
            return
            
        file_path = item.data(Qt.ItemDataRole.UserRole)
        if not os.path.exists(file_path):
            QMessageBox.warning(self, "文件不存在", f"文件 '{os.path.basename(file_path)}' 不存在")
            return
        
        try:
            if sys.platform == "win32":
                # Windows: 使用 explorer 打开并选中文件
                subprocess.run(['explorer', '/select,', os.path.normpath(file_path)], check=False)
            elif sys.platform == "darwin":
                # macOS: 使用 open -R 打开并选中文件
                subprocess.run(['open', '-R', file_path], check=False)
            else:
                # Linux: 尝试使用不同的文件管理器
                file_dir = os.path.dirname(file_path)
                # 尝试常见的文件管理器
                file_managers = ['nautilus', 'dolphin', 'thunar', 'pcmanfm', 'caja']
                for fm in file_managers:
                    try:
                        subprocess.run([fm, file_dir], check=True)
                        break
                    except (subprocess.CalledProcessError, FileNotFoundError):
                        continue
                else:
                    # 如果所有文件管理器都失败，尝试使用 xdg-open
                    subprocess.run(['xdg-open', file_dir], check=False)
                    
        except Exception as e:
            QMessageBox.critical(self, "打开失败", f"无法打开文件位置：{str(e)}")
    
    def remove_from_playlist(self, position):
        """从播放列表移除项目"""
        item = self.playlist_widget.itemAt(position)
        if item and self.playlist_manager:
            file_path = item.data(Qt.ItemDataRole.UserRole)
            current_playlist = self.playlist_manager.current_playlist
            if self.playlist_manager.remove_from_playlist(current_playlist, file_path):
                self.refresh_playlist_content_only()
    
    def delete_file_permanently(self, position):
        """永久删除文件"""
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
                # 从所有播放列表中移除
                if self.playlist_manager:
                    for playlist_name in self.playlist_manager.get_playlist_names():
                        self.playlist_manager.remove_from_playlist(playlist_name, file_path)
                
                # 删除文件
                if os.path.exists(file_path):
                    os.remove(file_path)
                    QMessageBox.information(self, "删除成功", f"文件 '{file_name}' 已被删除")
                else:
                    QMessageBox.warning(self, "文件不存在", f"文件 '{file_name}' 不存在")
                
                # 刷新显示
                self.refresh_playlist_content_only()
                
            except Exception as e:
                QMessageBox.critical(self, "删除失败", f"无法删除文件：{str(e)}")
    
    def on_playlist_changed(self, playlist_name):
        """播放列表切换"""
        if self.playlist_manager and playlist_name and playlist_name != self.playlist_manager.current_playlist:
            self.playlist_manager.set_current_playlist(playlist_name)
            # 不调用 refresh_playlist_display，因为它会重新设置combo导致循环
            self.refresh_playlist_content_only()
    
    def manage_playlists(self):
        """管理播放列表"""
        dialog = PlaylistManagerDialog(self, self.playlist_manager)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh_playlist_combo()
            self.refresh_playlist_display()
    
    def refresh_playlist_combo(self):
        """刷新播放列表下拉框"""
        if not self.playlist_manager:
            return
        
        # 暂时断开信号连接，防止循环调用
        self.playlist_combo.currentTextChanged.disconnect()
        
        try:
            current_text = self.playlist_combo.currentText()
            self.playlist_combo.clear()
            
            # 添加播放列表
            playlist_names = self.playlist_manager.get_playlist_names()
            self.playlist_combo.addItems(playlist_names)
            
            # 恢复选择
            target_playlist = self.playlist_manager.current_playlist
            if target_playlist in playlist_names:
                self.playlist_combo.setCurrentText(target_playlist)
            elif playlist_names:
                self.playlist_combo.setCurrentText(playlist_names[0])
                
        finally:
            # 重新连接信号
            self.playlist_combo.currentTextChanged.connect(self.on_playlist_changed)
    
    def refresh_playlist_display(self):
        """刷新播放列表显示"""
        if not self.playlist_manager:
            return
        
        # 刷新下拉框
        self.refresh_playlist_combo()
        # 刷新内容
        self.refresh_playlist_content_only()
    
    def refresh_playlist_content_only(self):
        """只刷新播放列表内容，不影响下拉框"""
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
        """处理项目移动"""
        if self.playlist_manager:
            current_playlist = self.playlist_manager.current_playlist
            self.playlist_manager.move_in_playlist(current_playlist, start, row)
    
    def locate_current_song(self, current_file_path):
        """定位当前播放的歌曲"""
        if not current_file_path:
            return
            
        # 查找当前播放歌曲在播放列表中的位置
        for i in range(self.playlist_widget.count()):
            item = self.playlist_widget.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == current_file_path:
                # 选中并滚动到当前歌曲
                self.playlist_widget.setCurrentRow(i)
                self.playlist_widget.scrollToItem(item, QListWidget.ScrollHint.PositionAtCenter)
                return
        
        # 如果没有找到，显示提示
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.information(self, "提示", "当前播放的歌曲不在播放列表中") 