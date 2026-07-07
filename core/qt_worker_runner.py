"""通用 Qt Worker 适配器 —— 复用现有 QThread 插件 worker，无需重写业务逻辑。

原理：
  - QThread worker 可在无 QApplication 的情况下构造；
  - 用 Qt.DirectConnection 把信号直连到回调（在 worker 线程内直接调用，无需事件循环）；
  - worker.run() 在普通线程中执行，事件推入队列供 WebSocket 拉取。
"""
import threading
from PySide6.QtCore import Qt


class QtWorkerTask:
    def __init__(self, worker, signal_map, on_event):
        self._worker = worker
        self._signal_map = signal_map  # {signal_name: callable(args_tuple) -> event_dict}
        self._on_event = on_event
        self._thread = None

    def start(self):
        for name, transform in self._signal_map.items():
            sig = getattr(self._worker, name, None)
            if sig is None:
                continue
            sig.connect(self._make(transform), Qt.DirectConnection)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _make(self, transform):
        def handler(*args):
            try:
                ev = transform(args)
            except Exception as e:
                ev = {"type": "log", "msg": f"[event-conv-error] {e}"}
            self._on_event(ev)
        return handler

    def _run(self):
        try:
            self._worker.run()
        except Exception as e:
            self._on_event({"type": "log", "msg": f"[FATAL] {e}"})
            self._on_event({"type": "done", "success": False, "msg": str(e)})

    def stop(self):
        for m in ("stop", "cancel"):
            if hasattr(self._worker, m):
                try:
                    getattr(self._worker, m)()
                except Exception:
                    pass
                return
