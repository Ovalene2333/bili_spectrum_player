import threading
import queue
import numpy as np
import time


class SpectrumProcessor:
    """负责频谱数据的处理和计算。"""

    def __init__(self, config, input_queue):
        self.config = config
        self._input_queue = input_queue
        self._output_queue = queue.Queue(maxsize=2)
        self._thread = None
        self.running = False

        self._last_db_heights = None
        self._window = np.hanning(self.config.CHUNK_SIZE)
        self._init_fft_bins()

    def _init_fft_bins(self):
        """预计算FFT频率分箱的索引。"""
        full_xf = np.fft.rfftfreq(self.config.CHUNK_SIZE, 1.0 / self.config.SAMPLE_RATE)

        linear_base = np.linspace(0, 1, self.config.NUM_BARS + 1)
        non_linear_base = linear_base**1.2  # 使用与player.py相同的非线性因子
        max_edge_freq = min(self.config.MAX_FREQ, full_xf[-1])
        bar_edges = max_edge_freq * non_linear_base

        self.bin_indices = np.searchsorted(full_xf, bar_edges)
        self.bin_indices = np.clip(self.bin_indices, 0, len(full_xf) - 1)

    def get_processed_data_queue(self):
        """返回用于获取处理后数据的队列。"""
        return self._output_queue

    def start(self):
        """启动处理线程。"""
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        """停止处理线程。"""
        self.running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _get_latest_data_from_queue(self):
        """从队列中获取最新数据，丢弃旧数据。"""
        latest_data = None
        try:
            while True:
                latest_data = self._input_queue.get_nowait()
        except queue.Empty:
            pass
        return latest_data

    def _run(self):
        """循环处理音频数据。"""
        while self.running:
            raw_data = self._get_latest_data_from_queue()

            if raw_data is None:
                # 没有新数据时，让旧的高度缓慢下降
                if self._last_db_heights is not None:
                    self._last_db_heights *= 0.9
                    try:
                        self._output_queue.put(self._last_db_heights, block=False)
                    except queue.Full:
                        pass
                time.sleep(0.01)
                continue

            # 处理音频数据
            processed_data = raw_data * self._window
            fft = np.fft.rfft(processed_data)
            mag = np.abs(fft) / self.config.CHUNK_SIZE

            # 计算频谱高度
            heights = np.zeros(self.config.NUM_BARS)
            for i in range(self.config.NUM_BARS):
                start_idx = self.bin_indices[i]
                end_idx = self.bin_indices[i + 1]
                if start_idx < end_idx and end_idx <= len(mag):
                    segment = mag[start_idx:end_idx]
                    if segment.size > 0:
                        heights[i] = np.max(segment)

            # 对数缩放
            db_heights = 2.5e2 * np.log(1 + heights**0.35)

            # 平滑处理
            if self._last_db_heights is not None:
                display_heights = db_heights * 0.6 + self._last_db_heights * 0.4
            else:
                display_heights = db_heights

            self._last_db_heights = display_heights.copy()

            # 限幅
            display_heights = np.clip(display_heights, 0, self.config.MAX_DB_VALUE)

            try:
                # 丢弃旧数据，放入新数据
                if self._output_queue.full():
                    self._output_queue.get_nowait()
                self._output_queue.put(display_heights, block=False)
            except queue.Full:
                pass

        print("频谱处理线程已停止。") 