import sounddevice as sd
import numpy as np
import ffmpeg
import threading
import queue
import subprocess
import sys
import os
from PyQt6.QtCore import QObject, pyqtSignal

class AudioPlayer(QObject):
    """
    任意格式音频文件播放，底层用ffmpeg解码，sounddevice播放
    """
    # 定义信号
    playback_finished = pyqtSignal()  # 播放结束信号

    def __init__(self, filename, blocksize=1024, device=None):
        super().__init__()
        self.filename = filename
        self.blocksize = blocksize
        self.device = device
        self._thread = None
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._stream = None
        self._samplerate = 44100
        self._channels = 2
        self._data_queue = queue.Queue(maxsize=10)  # 用于存储音频数据
        self._duration = 0
        self._position = 0
        self._seek_time = -1 # 用于记录跳转时间
        self._is_finished = False  # 添加播放完成标志
        self._volume = 1.0  # 音量, 0.0 到 1.0

    def _probe(self):
        try:
            # 针对Windows平台，隐藏ffmpeg.probe的终端窗口
            if sys.platform == "win32":
                # 临时设置环境变量来隐藏probe的子进程窗口
                original_startupinfo = getattr(subprocess, '_original_startupinfo', None)
                if not original_startupinfo:
                    subprocess._original_startupinfo = subprocess.STARTUPINFO
                    
                class HiddenStartupInfo(subprocess.STARTUPINFO):
                    def __init__(self):
                        super().__init__()
                        self.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                        self.wShowWindow = subprocess.SW_HIDE
                
                # 临时替换STARTUPINFO
                original_popen = subprocess.Popen
                def hidden_popen(*args, **kwargs):
                    if 'startupinfo' not in kwargs:
                        kwargs['startupinfo'] = HiddenStartupInfo()
                    if 'creationflags' not in kwargs:
                        kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
                    return original_popen(*args, **kwargs)
                
                subprocess.Popen = hidden_popen
                
                try:
                    probe = ffmpeg.probe(self.filename)
                finally:
                    # 恢复原始的Popen
                    subprocess.Popen = original_popen
            else:
                probe = ffmpeg.probe(self.filename)
                
            for stream in probe['streams']:
                if stream['codec_type'] == 'audio':
                    self._samplerate = int(stream['sample_rate'])
                    self._channels = int(stream['channels'])
                    self._duration = float(stream['duration'])
                    return
        except Exception as e:
            print(f"探测音频文件失败: {e}", file=sys.stderr)
            raise

    def _play_thread(self):
        try:
            self._probe()
            
            # 根据是否有跳转需求，构建ffmpeg输入
            input_stream = ffmpeg.input(self.filename)
            if self._seek_time > 0:
                input_stream = ffmpeg.input(self.filename, ss=self._seek_time)
                self._position = self._seek_time # 更新当前播放位置
                self._seek_time = -1 # 重置跳转标记

            # 构建 ffmpeg 命令
            args = (
                ffmpeg
                .output(input_stream, 'pipe:', format='f32le', acodec='pcm_f32le', ac=self._channels, ar=self._samplerate)
                .compile()
            )

            # 针对Windows平台，使用STARTUPINFO和creationflags彻底隐藏FFmpeg终端窗口
            startupinfo = None
            creation_flags = 0
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                creation_flags = subprocess.CREATE_NO_WINDOW

            # 使用 subprocess.Popen 手动执行命令
            process = subprocess.Popen(
                args, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.DEVNULL,
                startupinfo=startupinfo,
                creationflags=creation_flags
            )

            def callback(outdata, frames, time, status):
                if not self._pause_event.is_set():
                    outdata[:] = np.zeros(outdata.shape, dtype=np.float32)
                    return
                try:
                    data = process.stdout.read(frames * self._channels * 4)
                    if len(data) < frames * self._channels * 4:
                        outdata[:len(data)//(4*self._channels)] = np.frombuffer(data, dtype=np.float32).reshape(-1, self._channels)
                        self._is_finished = True
                        self.playback_finished.emit()  # 发送播放结束信号
                        raise sd.CallbackStop()
                    audio_data = np.frombuffer(data, dtype=np.float32).reshape(-1, self._channels)
                    outdata[:] = audio_data * self._volume  # 应用音量
                    self._position = self._position + len(audio_data) / self._samplerate
                    # 将音频数据放入队列
                    if self._data_queue.full():
                        try:
                            self._data_queue.get_nowait()
                        except queue.Empty:
                            pass
                    self._data_queue.put_nowait(audio_data)
                except Exception as e:
                    print(f"播放回调错误: {e}", file=sys.stderr)
                    raise sd.CallbackStop()

            with sd.OutputStream(
                samplerate=self._samplerate,
                channels=self._channels,
                dtype='float32',
                blocksize=self.blocksize,
                device=self.device,
                callback=callback
            ) as stream:
                self._stream = stream
                while stream.active and not self._stop_event.is_set():
                    sd.sleep(100)
        except Exception as e:
            print(f"播放线程错误: {e}", file=sys.stderr)
        finally:
            if 'process' in locals():
                process.terminate()
            self._stream = None

    def play(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._pause_event.set()
        self._is_finished = False  # 重置播放完成标志
        self._thread = threading.Thread(target=self._play_thread, daemon=True)
        self._thread.start()

    def pause(self):
        self._pause_event.clear()

    def resume(self):
        self._pause_event.set()

    def stop(self):
        self._stop_event.set()
        if self._stream:
            try:
                self._stream.abort()
            except Exception:
                pass
        if self._thread:
            self.resume() # 确保线程不是卡在pause上
            self._thread.join(timeout=1.0)
        self._is_finished = False  # 重置播放完成标志
        self._position = 0 # 停止后位置归零

    def seek(self, position_seconds):
        """跳转到指定时间点"""
        if self._thread and self._thread.is_alive():
            self._seek_time = max(0, position_seconds)
            
            # 停止当前播放线程，以便用新的seek时间重启
            self.stop()
            # 重新开始播放
            self.play()

    def set_volume(self, volume):
        """设置音量 (0.0 to 1.0)"""
        self._volume = np.clip(volume, 0.0, 1.0)

    def get_audio_data(self):
        """获取最新的音频数据用于频谱显示"""
        try:
            return self._data_queue.get_nowait()
        except queue.Empty:
            return None
        
    def get_duration(self):
        return self._duration
    
    def get_position(self):
        return self._position
        
    def is_finished(self):
        """检查是否播放完成"""
        return self._is_finished

class AudioRecorder:
    def __init__(self, samplerate=44100, channels=1, blocksize=1024, device=None, loopback=False):
        self.samplerate = samplerate
        self.channels = channels
        self.blocksize = blocksize
        self.device = device
        self.loopback = loopback
        self._thread = None
        self._queue = queue.Queue(maxsize=10)
        self._stop_event = threading.Event()

    def _find_loopback_device(self):
        try:
            wasapi_idx = None
            for i, api in enumerate(sd.query_hostapis()):
                if api['name'] == 'Windows WASAPI':
                    wasapi_idx = i
                    break
            if wasapi_idx is None:
                return None

            for idx, dev in enumerate(sd.query_devices()):
                if dev['hostapi'] == wasapi_idx and dev['max_input_channels'] > 0:
                    if dev['name'].endswith(' (loopback)') or '回放' in dev['name'] or 'Loopback' in dev['name']:
                        return idx
            return None
        except Exception as e:
            print(f"查找回环设备时出错: {e}", file=sys.stderr)
            return None

    def _record_thread(self):
        try:
            if self.loopback and self.device is None:
                dev_idx = self._find_loopback_device()
                if dev_idx is not None:
                    self.device = dev_idx
                    print(f"使用回环设备: {sd.query_devices(dev_idx)['name']}")
                else:
                    print('未找到回环设备，使用默认输入设备', file=sys.stderr)

            def callback(indata, frames, time, status):
                if status:
                    print(f"录音状态: {status}", file=sys.stderr)
                try:
                    if self._queue.full():
                        self._queue.get_nowait()
                    self._queue.put_nowait(indata.copy())
                except queue.Full:
                    pass

            with sd.InputStream(
                samplerate=self.samplerate,
                channels=self.channels,
                blocksize=self.blocksize,
                device=self.device,
                dtype='float32',
                callback=callback,
                latency='low',
                extra_settings=sd.WasapiSettings(loopback=self.loopback) if self.loopback else None
            ) as stream:
                while not self._stop_event.is_set():
                    sd.sleep(50)
        except Exception as e:
            print(f"录音线程错误: {e}", file=sys.stderr)

    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._record_thread, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=1.0)

    def get_data_queue(self):
        return self._queue 
