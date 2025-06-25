# Bili音乐播放助手
[![Python](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](#许可证) ![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)

## 项目简介
Bili音乐播放助手是一款基于Python和PyQt6开发的桌面音乐播放器，支持本地音频文件播放和B站视频音频下载播放。界面美观，内置动态频谱显示和圆形进度条，支持多种播放模式（顺序、随机、单曲循环），并带有播放列表管理功能。

## 目录
- [主要功能](#主要功能)
- [环境要求](#环境要求)
- [安装方法](#安装方法)
- [使用说明](#使用说明)
- [配置文件说明](#配置文件说明)
- [构建与打包](#构建与打包)
- [代码结构简述](#代码结构简述)
- [贡献指南](#贡献指南)
- [常见问题](#常见问题)
- [许可证](#许可证)

## 主要功能
- 支持多种音频格式播放（MP3、WAV、OGG、FLAC、AAC、M4A等）
- 支持从Bilibili视频链接下载音频并自动添加到播放列表
- 动态频谱可视化，实时显示音频频谱
- 圆形进度条显示当前播放进度
- 播放列表管理：添加、删除音频文件，支持搜索过滤
- 多种播放模式切换：顺序播放、随机播放、单曲循环
- 播放控制：播放、暂停、停止、上一首、下一首
- 界面采用渐变背景和现代化按钮样式，用户体验良好

![image-20250616151609859](./readme_src/normal.png)

<!-- ![image-20250616151654772](./README.assets/image-20250616151654772.png) -->

## 环境要求
- Python 3.8 及以上
- PyQt6
- numpy
- pyqtgraph
- 其他依赖库（详见代码中的import部分）

## 安装方法
1. 克隆或下载本项目代码到本地。
2. 安装依赖库：
   ```bash
   pip install -r requirements.txt
   ```
3. 确保网络环境可访问Bilibili，用于音频下载功能。

## 使用说明
1. 运行主程序：
   ```bash
   python player.py
   ```
2. 主界面左侧为播放列表和B站链接输入框：
   - 输入B站视频链接，点击"下载"按钮，程序将自动下载音频并添加到播放列表。
   - 点击"添加文件"按钮，选择本地音频文件添加到播放列表。
   - 选中播放列表中的音频，双击即可播放。
3. 中间区域为动态频谱显示和圆形进度条，播放时实时更新。
4. 底部控制栏包含播放、暂停、停止、上一首、下一首按钮，以及播放模式切换按钮。
5. 支持播放模式切换，满足不同听歌需求。

## 配置文件说明
本项目支持自定义配置，所有配置均存放于 `config` 目录下：

| 文件 | 说明 |
| ---- | ---- |
| `settings.json` | 全局程序设置，例如频谱刷新率、窗口大小、缓存目录等 |
| `playlists.json` | 播放列表持久化存储，程序退出时会自动写入，启动时读取 |

如需修改请直接编辑相应 JSON 文件或在应用内通过「设置」对话框调整。

## 构建与打包
本项目已提供 Windows 平台的打包脚本 `packing.bat`，使用 [PyInstaller](https://www.pyinstaller.org/) 将项目打包为可执行文件。默认会生成一个包含所有依赖的 **dist/BiliSpectrumPlayer** 目录，双击其中的 `BiliSpectrumPlayer.exe` 即可运行。

### 快速打包
```powershell
# 在 PowerShell / CMD 中执行
./packing.bat
```
脚本等价于：
```bash
pyinstaller --windowed --name BiliSpectrumPlayer \
            --add-data "assets;assets" \
            --add-data "config;config" \
            player.py -y
```
参数说明：
- `--windowed`：生成无控制台窗口的 GUI 程序；
- `--add-data`：将资源与配置目录一起打包；
- `-y`：自动覆盖旧的构建结果。

### 一键生成单文件可执行
若希望得到单文件可使用已注释的命令：
```bash
pyinstaller --onefile --windowed --name BiliSpectrumPlayer \
            --add-data "assets;assets" \
            --add-data "config;config" \
            player.py -y
```
生成的可执行文件位于 `dist/BiliSpectrumPlayer.exe`。

### 跨平台构建

Not support.

## 代码结构简述
- `PlayerWindow`：主窗口类，负责界面布局、事件处理和音频播放控制。
- `CollapsiblePlaylist`：播放列表组件，支持文件管理和搜索过滤。
- `SpectrumWidget`：频谱显示组件，基于pyqtgraph绘制动态频谱。
- `CircularProgressBar`：圆形进度条组件，显示播放进度。
- `BilibiliDownloader`：负责B站音频下载（需实现具体下载逻辑）。
- `AudioPlayer`：音频播放封装类，支持播放、暂停、停止等操作。
- 其他辅助组件包括渐变背景、播放按钮图标绘制等。

## 注意事项
- B站下载功能依赖网络和接口稳定，若下载失败请检查网络或更新相关接口代码。
- 播放列表保存为`playlist.json`，程序启动时自动加载。
- 频谱显示和进度条更新频率可在配置中调整。

## 贡献指南
欢迎各位对本项目提出 Issue 或提交 Pull Request！在贡献代码前请确保：
1. 你的代码通过 `flake8` / `ruff` 等静态检查；
2. 添加了必要的单元测试（若适用）；
3. 文档已同步更新。

## 常见问题
### Q: 为什么下载 B 站音频失败？
A: 请首先确认视频链接有效，且你的网络可以正常访问 B 站。  
如果接口发生变化，请关注仓库 issue 或尝试更新到最新版本。

### Q: 如何在 Linux / macOS 运行？
A: 本项目主要在 Windows 下开发测试，但核心逻辑与平台无关。
但是我并没有尝试在非Windows平台进行本项目的开发和构建(懒)。
你可以尝试：
```bash
python3 -m venv venv
source venv/bin/activate  # macOS / Linux
pip install -r requirements.txt
python player.py
```
如遇到依赖 `PyQt6` 无法安装的问题，请查阅对应平台的安装指南。

## 许可证
本项目采用MIT许可证，欢迎自由使用和修改。