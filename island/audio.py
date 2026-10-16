# SPDX-License-Identifier: GPL-3.0-only
"""Live WASAPI output spectrum. No microphone, PCM files or network traffic."""
from __future__ import annotations

from collections import deque
import ctypes
import math
import threading
import time
import uuid
import numpy as np
import pyaudiowpatch as pa
from PyQt6.QtCore import QThread, pyqtSignal


class Spectrum:
    EDGES = (40, 180, 650, 2200, 6500, 18000)

    def __init__(self, rate=48000, frames=2048):
        self.rate, self.frames = rate, frames
        self.window = np.hanning(frames).astype(np.float32)
        self.scale = 2 / self.window.sum()
        frequency = np.fft.rfftfreq(frames, 1 / rate)
        self.masks = [(frequency >= lo) & (frequency < min(hi, rate / 2))
                      for lo, hi in zip(self.EDGES, self.EDGES[1:])]
        self.levels = np.zeros(5, dtype=np.float64)
        self.history = None

    def process(self, pcm, channels, dt):
        samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768
        samples = samples[:len(samples) // channels * channels].reshape(-1, channels)
        if len(samples) < self.frames:
            if self.history is None or self.history.shape[1] != channels:
                self.history = np.zeros((self.frames, channels), dtype=np.float32)
            samples = np.concatenate((self.history, samples))[-self.frames:]
        samples = samples[-self.frames:]
        self.history = samples.copy()
        samples -= samples.mean(axis=0)
        if np.max(np.abs(samples), initial=0) < 1e-5:
            target = np.zeros(5)
        else:
            # Average powers, not stereo samples: out-of-phase stereo remains audible.
            fourier = np.fft.rfft(samples * self.window[:, None], axis=0) * self.scale
            powers = (np.abs(fourier) ** 2).mean(axis=1)
            energy = np.array([math.sqrt(float(powers[mask].sum())) for mask in self.masks])
            db = 20 * np.log10(np.maximum(energy, 1e-8))
            target = np.clip((db + 66) / 54, 0, 1)
        return self._smooth(target, dt)

    def silence(self, dt):
        if self.history is not None:
            self.history.fill(0)
        return self._smooth(np.zeros(5), dt)

    def _smooth(self, target, dt):
        tau = np.where(target > self.levels, 0.035, 0.18)
        self.levels += (target - self.levels) * (1 - np.exp(-max(0, dt) / tau))
        self.levels[self.levels < 0.001] = 0
        return tuple(float(v) for v in self.levels)


def default_output_id():
    """Cheap endpoint identity for reconnecting when headphones/output change."""
    class GUID(ctypes.Structure):
        _fields_ = [("bytes", ctypes.c_ubyte * 16)]
        def __init__(self, value):
            super().__init__()
            self.bytes[:] = uuid.UUID(value).bytes_le
    def call(pointer, slot, types, *args):
        table = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *types)(table[slot])(pointer, *args)
    enumerator, device, text = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
    ole = ctypes.windll.ole32
    try:
        cls = GUID("BCDE0395-E52F-467C-8E3D-C4579291692E")
        iid = GUID("A95664D2-9614-4F35-A746-DE8DB63617E6")
        if ole.CoCreateInstance(ctypes.byref(cls), None, 1, ctypes.byref(iid), ctypes.byref(enumerator)) != 0:
            return None
        if call(enumerator, 4, (ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)), 0, 0, ctypes.byref(device)) != 0:
            return None
        if call(device, 5, (ctypes.POINTER(ctypes.c_void_p),), ctypes.byref(text)) != 0:
            return None
        return ctypes.wstring_at(text)
    finally:
        if text.value:
            ole.CoTaskMemFree(text)
        for pointer in (device, enumerator):
            if pointer.value:
                call(pointer, 2, ())


class AudioSpectrum(QThread):
    levels_changed = pyqtSignal(object)
    availability_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.stopped = threading.Event()
        self.enabled = threading.Event()
        self.enabled.set()
        self.wakeup = threading.Event()
        self.capture_active = threading.Event()
        self.economy = threading.Event()

    def set_economy(self, enabled):
        if enabled:
            self.economy.set()
        else:
            self.economy.clear()

    def set_enabled(self, enabled):
        if enabled:
            self.enabled.set()
            self.wakeup.set()
        else:
            self.enabled.clear()

    def stop(self):
        self.stopped.set()
        self.wakeup.set()

    def run(self):
        ctypes.windll.ole32.CoInitializeEx(None, 0)
        previous = None
        try:
            while not self.stopped.is_set():
                if not self.enabled.is_set():
                    self.wakeup.clear()
                    if not self.enabled.is_set() and not self.stopped.is_set():
                        self.availability_changed.emit(False)
                        self.wakeup.wait()
                    previous = None
                    continue
                try:
                    endpoint = default_output_id()
                    with pa.PyAudio() as engine:
                        info = engine.get_default_wasapi_loopback()
                        if not info.get("isLoopbackDevice"):
                            raise RuntimeError("Capture device is not a WASAPI output loopback")
                        rate = int(info["defaultSampleRate"])
                        channels = int(info["maxInputChannels"])
                        analyzer = Spectrum(rate)
                        pending = deque(maxlen=2)
                        def callback(data, count, timing, status):
                            pending.append((data, time.monotonic()))
                            return (None, pa.paComplete if self.stopped.is_set() or not self.enabled.is_set() else pa.paContinue)
                        with engine.open(format=pa.paInt16, channels=channels, rate=rate,
                                         input=True, input_device_index=info["index"],
                                         frames_per_buffer=1024, stream_callback=callback) as stream:
                            self.availability_changed.emit(True)
                            self.capture_active.set()
                            previous_time, check_at = time.monotonic(), time.monotonic()
                            last_packet = previous_time
                            while not self.stopped.wait(0.05 if self.economy.is_set() else 0.025):
                                if not self.enabled.is_set():
                                    break
                                now = time.monotonic()
                                dt, previous_time = now - previous_time, now
                                if pending:
                                    packets = list(pending)
                                    pending.clear()
                                    data = b"".join(packet[0] for packet in packets)
                                    last_packet = packets[-1][1]
                                    levels = analyzer.process(data, channels, dt)
                                elif now - last_packet > 0.08:
                                    levels = analyzer.silence(dt)
                                else:
                                    continue
                                if previous is None or max(abs(a - b) for a, b in zip(previous, levels)) > 0.001:
                                    self.levels_changed.emit(levels)
                                    previous = levels
                                if now - check_at > 1.5:
                                    check_at = now
                                    if default_output_id() != endpoint or not stream.is_active():
                                        break
                except Exception:
                    self.availability_changed.emit(False)
                    self.levels_changed.emit((0.0,) * 5)
                    self.stopped.wait(1.5)
                finally:
                    self.capture_active.clear()
        finally:
            self.capture_active.clear()
            ctypes.windll.ole32.CoUninitialize()
