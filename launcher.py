"""Noova Web 桌面启动器 —— 启动本地 FastAPI 后端，用 Edge --app 打开应用窗口。

不依赖 pywebview/pythonnet（其在 PyInstaller onefile 下不稳定），改用系统自带的
Edge 以 --app 模式打开一个无标签栏的干净窗口，并监控其退出以关闭后端。
"""
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def start_server(port: int):
    import uvicorn
    uvicorn.run("server.app:app", host="127.0.0.1", port=port, log_level="warning")


def wait_for_server(url: str, tries: int = 120):
    for _ in range(tries):
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except Exception:
            time.sleep(0.25)
    return False


def find_edge():
    cands = [
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%LocalAppData%\Microsoft\Edge\Application\msedge.exe"),
    ]
    for c in cands:
        if os.path.isfile(c):
            return c
    return shutil.which("msedge")


def main():
    import subprocess

    port = free_port()
    url = f"http://127.0.0.1:{port}"

    t = threading.Thread(target=start_server, args=(port,), daemon=True)
    t.start()

    if not wait_for_server(url):
        print("后端启动失败", file=sys.stderr)
        sys.exit(1)

    edge = find_edge()
    if edge:
        profile = os.path.join(tempfile.gettempdir(), "noova_edge_profile")
        os.makedirs(profile, exist_ok=True)
        proc = subprocess.Popen([
            edge, "--app=" + url, "--window-size=1240,820",
            "--user-data-dir=" + profile, "--no-default-browser-check",
            "--no-first-run", "--disable-features=msEdgeWelcomeFLX",
        ])
        try:
            while proc.poll() is None:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        os._exit(0)
    else:
        import webbrowser
        webbrowser.open(url)
        print("未找到 Edge，已在默认浏览器打开。关闭本窗口将停止服务。")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            os._exit(0)


if __name__ == "__main__":
    main()
