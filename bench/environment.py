"""Read-only desktop and process-resource probes, independent of Nyx code."""
import os
import threading
import time


def desktop_probe():
    result = {'windows': os.name == 'nt', 'foreground_available': False,
              'clipboard_accessible': False, 'clipboard_error_code': None}
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes as w
        user = ctypes.WinDLL('user32', use_last_error=True)
        user.GetForegroundWindow.restype = w.HWND
        user.IsWindowVisible.argtypes = [w.HWND]
        user.OpenClipboard.argtypes = [w.HWND]
        handle = user.GetForegroundWindow()
        result['foreground_available'] = bool(handle and user.IsWindowVisible(handle))
        opened = bool(user.OpenClipboard(None))
        result['clipboard_accessible'] = opened
        result['clipboard_error_code'] = 0 if opened else ctypes.get_last_error()
        if opened:
            user.CloseClipboard()  # Never read the contents.
    result['interactive_probe_passed'] = result['foreground_available'] and result['clipboard_accessible']
    return result


class ResourceSampler:
    """RSS of this harness+children; system GPU usage, not exclusive Nyx VRAM."""
    def __init__(self):
        self.ram_peak_mib = self.vram_peak_mib = None
        self.samples = 0
        self._stop = threading.Event()
        self._thread = None
        self._gpu = None
        self._nvml_api = None

    def _sample(self):
        import psutil
        process = psutil.Process()
        rss = 0
        for member in [process, *process.children(recursive=True)]:
            try:
                rss += member.memory_info().rss
            except psutil.Error:
                pass
        self.ram_peak_mib = max(self.ram_peak_mib or 0, rss / 1024**2)
        if self._gpu:
            try:
                api, handle = self._gpu
                used = api.nvmlDeviceGetMemoryInfo(handle).used / 1024**2
                self.vram_peak_mib = max(self.vram_peak_mib or 0, used)
            except Exception:
                self._gpu = None
        self.samples += 1

    def __enter__(self):
        try:
            import pynvml
            pynvml.nvmlInit()
            self._nvml_api = pynvml
            self._gpu = pynvml, pynvml.nvmlDeviceGetHandleByIndex(0)
        except Exception:
            self._gpu = None
        self._sample()
        def monitor():
            while not self._stop.wait(.25):
                try:
                    self._sample()
                except Exception:
                    break
        self._thread = threading.Thread(target=monitor, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *args):
        self._stop.set()
        self._thread.join(timeout=2)
        try:
            self._sample()
        finally:
            if self._nvml_api:
                try:
                    self._nvml_api.nvmlShutdown()
                except Exception:
                    pass

    def report(self):
        return {'ram_peak_mib': self.ram_peak_mib, 'vram_peak_mib': self.vram_peak_mib,
                'samples': self.samples, 'sampling_interval_s': .25,
                'ram_scope': 'harness and descendant process working sets, shared pages may repeat',
                'vram_scope': 'system GPU usage, not exclusive Nyx allocation', 'measured_at': time.time()}
