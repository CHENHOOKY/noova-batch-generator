"""任务管理器 —— 跟踪后台任务、缓存事件供 WebSocket 拉取。"""
import collections
import threading
import uuid


class TaskManager:
    def __init__(self):
        self._tasks: dict = {}
        self._lock = threading.Lock()

    def _new(self, tid):
        info = {
            "events": collections.deque(),
            "status": "running",
            "success": None,
            "lock": threading.Lock(),
            "task": None,
        }
        with self._lock:
            self._tasks[tid] = info
        return info

    def _emit_for(self, info):
        def emit(ev):
            with info["lock"]:
                info["events"].append(ev)
                if ev.get("type") == "done":
                    info["status"] = "done"
                    info["success"] = ev.get("success", False)
        return emit

    def start_upscale(self, input_dir: str, output_dir: str, output_format: str) -> str:
        from core.upscale_service import UpscaleTask
        tid = uuid.uuid4().hex[:8]
        info = self._new(tid)
        task = UpscaleTask(input_dir, output_dir, output_format)
        info["task"] = task
        task.start(self._emit_for(info))
        return tid

    def start_worker(self, worker, signal_map) -> str:
        """通用：用 QtWorkerTask 适配现有 QThread worker。"""
        from core.qt_worker_runner import QtWorkerTask
        tid = uuid.uuid4().hex[:8]
        info = self._new(tid)
        qt = QtWorkerTask(worker, signal_map, self._emit_for(info))
        info["task"] = qt
        qt.start()
        return tid

    def status(self, tid: str):
        info = self._tasks.get(tid)
        if not info:
            return None
        return {"id": tid, "status": info["status"], "success": info["success"]}

    def drain(self, tid: str) -> list:
        info = self._tasks.get(tid)
        if not info:
            return []
        with info["lock"]:
            evs = list(info["events"])
            info["events"].clear()
        return evs

    def stop(self, tid: str) -> bool:
        info = self._tasks.get(tid)
        if not info or not info["task"]:
            return False
        info["task"].stop()
        return True
