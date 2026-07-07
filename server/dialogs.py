"""原生文件/文件夹选择对话框服务。

tkinter 非线程安全，故用一个专用守护线程串行处理所有对话框请求，
FastAPI 处理器通过 ask_folder() 阻塞等待结果（运行在线程池工作线程中，不阻塞事件循环）。
"""
import queue
import threading
import tkinter as tk
from tkinter import filedialog


class DialogServer:
    def __init__(self):
        self._q: "queue.Queue" = queue.Queue()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        while True:
            req = self._q.get()
            if req is None:
                break
            kind, kwargs, result = req
            try:
                root = tk.Tk()
                root.withdraw()
                root.attributes("-topmost", True)
                if kind == "folder":
                    val = filedialog.askdirectory(**kwargs)
                elif kind == "open":
                    val = filedialog.askopenfilename(**kwargs)
                elif kind == "save":
                    val = filedialog.asksaveasfilename(**kwargs)
                elif kind == "multi":
                    val = list(filedialog.askopenfilenames(**kwargs))
                else:
                    val = None
                root.destroy()
                result["value"] = val
            except Exception:
                result["value"] = None
            result["event"].set()

    def _ask(self, kind, kwargs, timeout=300):
        result = {"event": threading.Event(), "value": None}
        self._q.put((kind, kwargs, result))
        result["event"].wait(timeout)
        return result.get("value")

    def ask_folder(self, title="选择文件夹"):
        return self._ask("folder", {"title": title})

    def ask_open(self, title="选择文件", filetypes=None):
        return self._ask("open", {"title": title, "filetypes": filetypes or []})

    def ask_save(self, title="保存为", defaultextension=""):
        return self._ask("save", {"title": title, "defaultextension": defaultextension})

    def ask_open_multiple(self, title="选择文件", filetypes=None):
        return self._ask("multi", {"title": title, "filetypes": filetypes or []})
