import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, QListWidget,
    QFormLayout, QFileDialog, QMessageBox, QInputDialog
)
from PyQt6.QtCore import pyqtSignal
from .config import Config


class AddMusicDialog(QDialog):
    file_added = pyqtSignal(str)
    
    def __init__(self, parent=None, bilibili_downloader=None):
        super().__init__(parent)
        self.bilibili_downloader = bilibili_downloader
        self.setObjectName("AddMusicDialog")
        self.setup_ui()
    
    def setup_ui(self):
        self.setWindowTitle("添加音乐")
        self.setFixedSize(600, 450)
        self.setModal(True)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        
        # B站下载区域
        self.bilibili_input = QLineEdit()
        self.bilibili_input.setPlaceholderText("请输入B站视频链接")
        self.download_btn = QPushButton("下载")
        self.download_btn.clicked.connect(self.download_audio)
        
        bilibili_layout = QHBoxLayout()
        bilibili_layout.addWidget(self.bilibili_input)
        bilibili_layout.addWidget(self.download_btn)
        layout.addLayout(bilibili_layout)
        
        # 本地文件按钮
        self.select_file_btn = QPushButton("选择本地文件")
        self.select_file_btn.clicked.connect(self.select_files)
        layout.addWidget(self.select_file_btn)
        
        # 关闭按钮
        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self.accept)
        layout.addWidget(self.close_btn)
    
    def download_audio(self):
        if self.bilibili_downloader:
            url = self.bilibili_input.text().strip()
            if url:
                try:
                    output_path = self.bilibili_downloader.download_from_url(url)
                    self.file_added.emit(output_path)
                    self.bilibili_input.clear()
                    QMessageBox.information(self, "成功", "音频下载完成！")
                except Exception as e:
                    QMessageBox.critical(self, "错误", f"下载失败：{str(e)}")
    
    def select_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择音频文件", "", "音频文件 (*.mp3 *.wav *.ogg *.flac *.aac *.m4a)"
        )
        for file in files:
            self.file_added.emit(file)


class PlaylistManagerDialog(QDialog):
    def __init__(self, parent=None, playlist_manager=None):
        super().__init__(parent)
        self.playlist_manager = playlist_manager
        self.setObjectName("PlaylistManagerDialog")
        self.setup_ui()
        self.refresh_list()
    
    def setup_ui(self):
        self.setWindowTitle("播放列表管理")
        self.setFixedSize(400, 300)
        self.setModal(True)
        
        layout = QVBoxLayout(self)
        self.playlist_list = QListWidget()
        layout.addWidget(self.playlist_list)
        
        button_layout = QHBoxLayout()
        self.new_btn = QPushButton("新建")
        self.new_btn.clicked.connect(self.create_playlist)
        self.delete_btn = QPushButton("删除")
        self.delete_btn.clicked.connect(self.delete_playlist)
        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self.accept)
        
        button_layout.addWidget(self.new_btn)
        button_layout.addWidget(self.delete_btn)
        button_layout.addWidget(self.close_btn)
        layout.addLayout(button_layout)
    
    def refresh_list(self):
        if self.playlist_manager:
            self.playlist_list.clear()
            for name in self.playlist_manager.get_playlist_names():
                self.playlist_list.addItem(name)
    
    def create_playlist(self):
        text, ok = QInputDialog.getText(self, '新建播放列表', '请输入播放列表名称:')
        if ok and text.strip() and self.playlist_manager:
            if self.playlist_manager.create_playlist(text.strip()):
                self.refresh_list()
    
    def delete_playlist(self):
        current = self.playlist_list.currentItem()
        if current and self.playlist_manager:
            name = current.text().replace(" (默认)", "")
            if name != "默认播放列表":
                if self.playlist_manager.delete_playlist(name):
                    self.refresh_list()


class SettingsDialog(QDialog):
    def __init__(self, parent=None, settings=None):
        super().__init__(parent)
        self.settings = settings or {}
        self.setObjectName("SettingsDialog")
        self.setup_ui()
        self.load_settings()
    
    def setup_ui(self):
        self.setWindowTitle("设置")
        self.setFixedSize(500, 300)
        self.setModal(True)
        
        layout = QVBoxLayout(self)
        
        form_layout = QFormLayout()
        
        # 下载路径
        path_layout = QHBoxLayout()
        self.download_path_edit = QLineEdit()
        self.browse_btn = QPushButton("浏览")
        self.browse_btn.clicked.connect(self.browse_path)
        path_layout.addWidget(self.download_path_edit)
        path_layout.addWidget(self.browse_btn)
        
        form_layout.addRow("下载路径:", path_layout)
        
        # 代理设置
        self.proxy_edit = QLineEdit()
        form_layout.addRow("代理:", self.proxy_edit)
        
        layout.addLayout(form_layout)
        
        # 按钮
        button_layout = QHBoxLayout()
        self.ok_btn = QPushButton("确定")
        self.ok_btn.clicked.connect(self.accept_settings)
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        
        button_layout.addWidget(self.ok_btn)
        button_layout.addWidget(self.cancel_btn)
        layout.addLayout(button_layout)
    
    def browse_path(self):
        folder = QFileDialog.getExistingDirectory(self, "选择下载文件夹")
        if folder:
            self.download_path_edit.setText(folder)
    
    def load_settings(self):
        self.download_path_edit.setText(self.settings.get("download_path", ""))
        self.proxy_edit.setText(self.settings.get("proxy", ""))
    
    def accept_settings(self):
        self.settings["download_path"] = self.download_path_edit.text()
        self.settings["proxy"] = self.proxy_edit.text()
        self.accept()
    
    def get_settings(self):
        return self.settings 