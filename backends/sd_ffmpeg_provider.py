import sounddevice as sd
import numpy as np
import ffmpeg
import threading
import queue
import subprocess
import sys
import os
import time
from PySide6.QtCore import QObject, Signal

class AudioPlayer(QObject):
    playback_finished = Signal()

    def __init__(self, filename, blocksize=1024, device=None):
        super().__init__()
        self.filename = filename
        self.blocksize = blocksize
        self.device = device
        self._thread = None
        self._stop_event = threading.Event()
        self._stopping_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._stream = None
        self._samplerate = 44100
        self._channels = 2
        self._data_queue = queue.Queue(maxsize=10)
        self._duration = 0
        self._position = 0
        self._seek_time = -1
        self._is_finished = False
        self._volume = 1.0
        self._fade_frames = 0
        self._fade_in_remaining = 0
        self._fade_out_requested = threading.Event()
        self._fade_out_complete = threading.Event()
        self._stream_stopped = threading.Event()

    def _probe(self):
        try:
            if sys.platform == "win32":
                original_startupinfo = getattr(subprocess, '_original_startupinfo', None)
                if not original_startupinfo:
                    subprocess._original_startupinfo = subprocess.STARTUPINFO

                class HiddenStartupInfo(subprocess.STARTUPINFO):
                    def __init__(self):
                        super().__init__()
                        self.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                        self.wShowWindow = subprocess.SW_HIDE

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
                    subprocess.Popen = original_popen
            else:
                probe = ffmpeg.probe(self.filename)

            for stream in probe['streams']:
                if stream['codec_type'] == 'audio':
                    duration = stream.get('duration', probe.get('format', {}).get('duration', 0))
                    self._duration = float(duration)
                    return
        except Exception as e:
            print(f"探测音频文件失败: {e}", file=sys.stderr)
            raise

    def _play_thread(self):
        try:
            self._probe()
            if self._stop_event.is_set():
                return

            input_stream = ffmpeg.input(self.filename)
            if self._seek_time > 0:
                input_stream = ffmpeg.input(self.filename, ss=self._seek_time)
                self._position = self._seek_time
                self._seek_time = -1

            args = (
                ffmpeg
                .output(input_stream, 'pipe:', format='f32le', acodec='pcm_f32le', ac=self._channels, ar=self._samplerate)
                .compile()
            )

            startupinfo = None
            creation_flags = 0
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                creation_flags = subprocess.CREATE_NO_WINDOW

            process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                startupinfo=startupinfo,
                creationflags=creation_flags
            )
            self._fade_frames = max(1, int(self._samplerate * 0.015))
            self._fade_in_remaining = self._fade_frames
            self._fade_out_requested.clear()
            self._fade_out_complete.clear()
            self._stream_stopped.clear()
            pcm_queue = queue.Queue(maxsize=32)
            decoder_finished = threading.Event()
            bytes_per_block = self.blocksize * self._channels * 4

            def decode_audio():
                try:
                    while not self._stop_event.is_set():
                        data = process.stdout.read(bytes_per_block)
                        if not data:
                            break
                        while not self._stop_event.is_set():
                            try:
                                pcm_queue.put(data, timeout=0.05)
                                break
                            except queue.Full:
                                continue
                finally:
                    decoder_finished.set()

            decoder_thread = threading.Thread(target=decode_audio, daemon=True)
            decoder_thread.start()

            prebuffer_deadline = time.monotonic() + 0.5
            while (
                pcm_queue.qsize() < 4
                and not decoder_finished.is_set()
                and not self._stop_event.is_set()
                and time.monotonic() < prebuffer_deadline
            ):
                time.sleep(0.005)

            def callback(outdata, frames, time, status):
                outdata.fill(0)
                if self._stop_event.is_set():
                    raise sd.CallbackStop()
                if not self._pause_event.is_set():
                    return
                try:
                    try:
                        data = pcm_queue.get_nowait()
                    except queue.Empty:
                        if decoder_finished.is_set():
                            self._is_finished = True
                            if not self._stopping_event.is_set():
                                self.playback_finished.emit()
                            raise sd.CallbackStop()
                        self._fade_in_remaining = self._fade_frames
                        return
                    sample_count = len(data) // (4 * self._channels)
                    audio_data = np.frombuffer(
                        data[:sample_count * self._channels * 4],
                        dtype=np.float32
                    ).reshape(-1, self._channels)

                    gain = np.full(sample_count, self._volume, dtype=np.float32)
                    if self._fade_in_remaining > 0:
                        fade_count = min(sample_count, self._fade_in_remaining)
                        fade_start = self._fade_frames - self._fade_in_remaining
                        gain[:fade_count] *= np.arange(
                            fade_start,
                            fade_start + fade_count,
                            dtype=np.float32
                        ) / self._fade_frames
                        self._fade_in_remaining -= fade_count

                    if self._fade_out_requested.is_set():
                        fade_count = min(sample_count, self._fade_frames)
                        gain[:fade_count] *= np.linspace(
                            1.0,
                            0.0,
                            fade_count,
                            endpoint=True,
                            dtype=np.float32
                        )
                        gain[fade_count:] = 0
                        self._fade_out_complete.set()

                    outdata[:sample_count] = audio_data * gain[:, np.newaxis]
                    self._position = self._position + len(audio_data) / self._samplerate
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
                callback=callback,
                latency='high'
            ) as stream:
                self._stream = stream
                while stream.active and not self._stop_event.is_set():
                    sd.sleep(100)
        except Exception as e:
            print(f"播放线程错误: {e}", file=sys.stderr)
        finally:
            if 'process' in locals():
                try:
                    process.terminate()
                    process.wait(timeout=0.5)
                except (OSError, subprocess.TimeoutExpired):
                    try:
                        process.kill()
                    except OSError:
                        pass
            if 'decoder_thread' in locals():
                decoder_thread.join(timeout=0.5)
            self._stream = None
            self._stream_stopped.set()

    def play(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._stopping_event.clear()
        self._pause_event.set()
        self._is_finished = False
        self._thread = threading.Thread(target=self._play_thread, daemon=True)
        self._thread.start()

    def pause(self):
        self._pause_event.clear()

    def resume(self):
        self._pause_event.set()

    def stop(self):
        self._stopping_event.set()
        if self._stream and self._pause_event.is_set() and self._thread and self._thread.is_alive():
            self._fade_out_requested.set()
            self._fade_out_complete.wait(timeout=0.25)
        self._stop_event.set()
        if self._stream:
            try:
                self._stream.stop()
            except Exception:
                try:
                    self._stream.abort()
                except Exception:
                    pass
        if self._thread:
            self.resume()
            self._thread.join(timeout=2.0)
        self._clear_data_queue()
        self._is_finished = False
        self._position = 0

    def seek(self, position_seconds):
        if self._thread and self._thread.is_alive():
            self._seek_time = max(0, position_seconds)
            self.stop()
            self.play()

    def set_volume(self, volume):
        self._volume = np.clip(volume, 0.0, 1.0)

    def _clear_data_queue(self):
        while True:
            try:
                self._data_queue.get_nowait()
            except queue.Empty:
                return

    def get_audio_data(self):
        try:
            return self._data_queue.get_nowait()
        except queue.Empty:
            return None

    def get_duration(self):
        return self._duration

    def get_position(self):
        return self._position

    def is_finished(self):
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
