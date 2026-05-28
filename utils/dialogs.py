import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, QListWidget,
    QFormLayout, QFileDialog, QMessageBox, QInputDialog, QSlider, QLabel,
    QComboBox, QGroupBox, QGridLayout, QFrame
)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QFont
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


class EqualizerDialog(QDialog):
    """均衡器对话框"""
    equalizer_changed = pyqtSignal(list)  # 发出均衡器值变化信号
    
    def __init__(self, parent=None, settings=None):
        super().__init__(parent)
        self.settings = settings or {}
        self.setObjectName("EqualizerDialog")
        
        # 10频段均衡器的频率（Hz）
        self.frequencies = [31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]
        # 存储滑块控件
        self.eq_sliders = []
        # 存储当前均衡器值（-12dB 到 +12dB）
        self.eq_values = [0.0] * len(self.frequencies)
        
        # 预设配置
        self.presets = {
            "平衡": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            "流行": [1, 3, 5, 3, 0, -1, -1, 1, 2, 3],
            "摇滚": [4, 3, 2, 1, -1, -2, 0, 2, 3, 4],
            "古典": [3, 2, -1, -2, -2, -1, 1, 2, 3, 4],
            "爵士": [2, 1, 0, 1, 3, 2, 0, 1, 2, 3],
            "电子": [3, 2, 0, -1, 2, 0, 1, 3, 4, 5],
            "人声": [-2, -1, 1, 3, 4, 4, 3, 1, 0, -1],
            "低音增强": [6, 4, 2, 0, -1, -2, -1, 0, 1, 2],
            "高音增强": [-1, 0, 1, 2, 1, 0, 2, 4, 6, 8],
            "舞曲": [4, 3, 1, 0, 0, -1, 0, 2, 3, 4]
        }
        
        self.setup_ui()
        self.load_equalizer_settings()
    
    def setup_ui(self):
        self.setWindowTitle("均衡器")
        self.setFixedSize(700, 500)
        self.setModal(True)
        
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(20)
        
        # 预设选择区域
        preset_group = QGroupBox("预设")
        preset_layout = QHBoxLayout(preset_group)
        
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(["自定义"] + list(self.presets.keys()))
        self.preset_combo.currentTextChanged.connect(self.apply_preset)
        preset_layout.addWidget(QLabel("选择预设:"))
        preset_layout.addWidget(self.preset_combo)
        preset_layout.addStretch()
        
        main_layout.addWidget(preset_group)
        
        # 均衡器控制区域
        eq_group = QGroupBox("频段调节")
        eq_layout = QGridLayout(eq_group)
        eq_layout.setSpacing(15)
        
        # 创建滑块和标签
        for i, freq in enumerate(self.frequencies):
            # 频率标签
            freq_label = QLabel(self.format_frequency(freq))
            freq_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            freq_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
            freq_label.setObjectName(f"FreqLabel_{i}")
            freq_label.setStyleSheet("color: #000; background-color: rgba(255, 255, 255, 0.9); padding: 2px 6px; border-radius: 3px;")
            
            # 滑块（垂直）
            slider = QSlider(Qt.Orientation.Vertical)
            slider.setRange(-120, 120)  # -12dB 到 +12dB，乘以10为了精度
            slider.setValue(0)
            slider.setMinimumHeight(200)
            slider.setTickPosition(QSlider.TickPosition.TicksBothSides)
            slider.setTickInterval(60)  # 每6dB一个刻度
            slider.valueChanged.connect(self.on_slider_changed)
            self.eq_sliders.append(slider)
            
            # 数值标签
            value_label = QLabel("0 dB")
            value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            value_label.setFont(QFont("Arial", 9))
            value_label.setObjectName(f"ValueLabel_{i}")
            value_label.setStyleSheet("color: #000; background-color: rgba(255, 255, 255, 0.9); padding: 2px 4px; border-radius: 3px;")
            
            # 布局：频率标签在顶部，滑块在中间，数值在底部
            eq_layout.addWidget(freq_label, 0, i, Qt.AlignmentFlag.AlignCenter)
            eq_layout.addWidget(slider, 1, i, Qt.AlignmentFlag.AlignCenter)
            eq_layout.addWidget(value_label, 2, i, Qt.AlignmentFlag.AlignCenter)
        
        main_layout.addWidget(eq_group)
        
        # 功能按钮区域
        button_layout = QHBoxLayout()
        
        self.enable_checkbox = QPushButton("启用均衡器")
        self.enable_checkbox.setCheckable(True)
        self.enable_checkbox.setChecked(True)
        self.enable_checkbox.clicked.connect(self.on_enable_changed)
        
        self.reset_btn = QPushButton("重置")
        self.reset_btn.clicked.connect(self.reset_equalizer)
        
        self.apply_btn = QPushButton("应用")
        self.apply_btn.clicked.connect(self.apply_equalizer)
        
        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self.accept)
        
        button_layout.addWidget(self.enable_checkbox)
        button_layout.addStretch()
        button_layout.addWidget(self.reset_btn)
        button_layout.addWidget(self.apply_btn)
        button_layout.addWidget(self.close_btn)
        
        main_layout.addLayout(button_layout)
    
    def format_frequency(self, freq):
        """格式化频率显示"""
        if freq >= 1000:
            return f"{freq // 1000}k"
        else:
            return str(freq)
    
    def on_slider_changed(self):
        """滑块值改变时的处理"""
        sender = self.sender()
        if sender in self.eq_sliders:
            index = self.eq_sliders.index(sender)
            value = sender.value() / 10.0  # 转换回dB值
            self.eq_values[index] = value
            
            # 更新数值标签
            value_label = self.findChild(QLabel, f"ValueLabel_{index}")
            if value_label:
                if value >= 0:
                    value_label.setText(f"+{value:.1f} dB")
                else:
                    value_label.setText(f"{value:.1f} dB")
            
            # 设置为自定义预设
            self.preset_combo.setCurrentText("自定义")
            
            # 立即应用均衡器
            self.apply_equalizer()
    
    def apply_preset(self, preset_name):
        """应用预设"""
        if preset_name in self.presets:
            values = self.presets[preset_name]
            for i, value in enumerate(values):
                self.eq_sliders[i].setValue(int(value * 10))
                self.eq_values[i] = value
                
                # 更新数值标签
                value_label = self.findChild(QLabel, f"ValueLabel_{i}")
                if value_label:
                    if value >= 0:
                        value_label.setText(f"+{value:.1f} dB")
                    else:
                        value_label.setText(f"{value:.1f} dB")
            
            # 应用均衡器
            self.apply_equalizer()
    
    def reset_equalizer(self):
        """重置均衡器到平衡状态"""
        self.preset_combo.setCurrentText("平衡")
        self.apply_preset("平衡")
    
    def on_enable_changed(self):
        """启用/禁用均衡器"""
        enabled = self.enable_checkbox.isChecked()
        self.enable_checkbox.setText("启用均衡器" if enabled else "禁用均衡器")
        
        # 启用/禁用所有滑块
        for slider in self.eq_sliders:
            slider.setEnabled(enabled)
        
        self.reset_btn.setEnabled(enabled)
        self.preset_combo.setEnabled(enabled)
        
        # 应用设置
        self.apply_equalizer()
    
    def apply_equalizer(self):
        """应用均衡器设置"""
        if self.enable_checkbox.isChecked():
            self.equalizer_changed.emit(self.eq_values[:])  # 发送当前均衡器值
        else:
            self.equalizer_changed.emit([0.0] * len(self.frequencies))  # 发送零值（禁用状态）
        
        # 保存设置
        self.save_equalizer_settings()
    
    def load_equalizer_settings(self):
        """加载均衡器设置"""
        eq_settings = self.settings.get("equalizer", {})
        
        # 加载均衡器值
        saved_values = eq_settings.get("values", [0.0] * len(self.frequencies))
        if len(saved_values) == len(self.frequencies):
            for i, value in enumerate(saved_values):
                self.eq_sliders[i].setValue(int(value * 10))
                self.eq_values[i] = value
                
                # 更新数值标签
                value_label = self.findChild(QLabel, f"ValueLabel_{i}")
                if value_label:
                    if value >= 0:
                        value_label.setText(f"+{value:.1f} dB")
                    else:
                        value_label.setText(f"{value:.1f} dB")
        
        # 加载启用状态
        enabled = eq_settings.get("enabled", True)
        self.enable_checkbox.setChecked(enabled)
        self.on_enable_changed()
        
        # 加载预设
        preset = eq_settings.get("preset", "自定义")
        if preset in (self.preset_combo.itemText(i) for i in range(self.preset_combo.count())):
            self.preset_combo.setCurrentText(preset)
    
    def save_equalizer_settings(self):
        """保存均衡器设置"""
        eq_settings = {
            "values": self.eq_values[:],
            "enabled": self.enable_checkbox.isChecked(),
            "preset": self.preset_combo.currentText()
        }
        self.settings["equalizer"] = eq_settings
    
    def get_settings(self):
        """获取设置"""
        return self.settings 