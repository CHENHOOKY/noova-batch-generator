"""Noova AI API 共享通信层 —— 供批量出图插件复用

提供:
  - NoovaAPI:       与 Noova AI 绘图 API 通信
  - MODEL_CONFIG:   模型配置（比例、尺寸）
  - MAX_IMAGE_DIM:  图片最大边长（超出自动缩放）
  - MAX_POLL_RETRIES: 轮询最大次数

batch_draw / folder_batch_draw 两个插件共用此模块。
"""

import os
import time
from typing import List, Tuple

import requests

# ── 常量 ────────────────────────────────────────────
MAX_IMAGE_DIM = 2048
MAX_POLL_RETRIES = 120

MODEL_CONFIG = {
    "gpt-image-2": {
        "ratios": ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3",
                   "5:4", "4:5", "21:9", "9:21", "1:2", "2:1"],
        "sizes": ["1K"],
    },
    "nano-banana-pro": {
        "ratios": ["auto", "1:1", "16:9", "9:16", "4:3", "3:4", "3:2",
                   "2:3", "5:4", "4:5", "21:9"],
        "sizes": ["1K", "2K", "4K"],
    },
    "nano-banana-2": {
        "ratios": ["auto", "1:1", "16:9", "9:16", "4:3", "3:4", "3:2",
                   "2:3", "5:4", "4:5", "21:9", "1:4", "4:1", "1:8", "8:1"],
        "sizes": ["1K", "2K", "4K"],
    },
    "nano-banana-fast": {
        "ratios": ["auto", "1:1", "16:9", "9:16", "4:3", "3:4", "3:2",
                   "2:3", "5:4", "4:5", "21:9"],
        "sizes": ["1K", "2K", "4K"],
    },
    "nano-banana": {
        "ratios": ["auto", "1:1", "16:9", "9:16", "4:3", "3:4", "3:2",
                   "2:3", "5:4", "4:5", "21:9"],
        "sizes": ["1K", "2K", "4K"],
    },
}

MAX_CONCURRENCY = 10


# ── API 通信类 ───────────────────────────────────────

class NoovaAPI:
    """Noova AI 绘图 API 客户端"""

    BASE_URL = "https://noova.cn"

    def __init__(self, api_key: str):
        self.api_key = api_key.strip()
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def local_file_to_base64(self, filepath: str, log_callback=None) -> str:
        import base64
        import io
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"本地文件不存在: {filepath}")

        try:
            from PIL import Image
            img = Image.open(filepath)
            fmt = img.format
            if log_callback:
                log_callback(f"  -> 图片格式: {fmt}, 尺寸: {img.size}")

            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGB")

            w, h = img.size
            if max(w, h) > MAX_IMAGE_DIM:
                ratio = MAX_IMAGE_DIM / max(w, h)
                img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
                if log_callback:
                    log_callback(f"  -> 已缩放至: {img.size}")

            buf = io.BytesIO()
            img.save(buf, format="PNG")
            b64_str = base64.b64encode(buf.getvalue()).decode("utf-8")
            if log_callback:
                log_callback(f"  -> base64 编码完成, 长度: {len(b64_str)}")
            return b64_str
        except ImportError:
            with open(filepath, "rb") as f:
                raw = f.read()
            return base64.b64encode(raw).decode("utf-8")

    def create_draw_task(self, model: str, prompt: str, aspect_ratio: str,
                         image_size: str, urls: List[str]) -> Tuple[str, dict]:
        payload = {"model": model, "prompt": prompt, "imageSize": image_size,
                    "aspectRatio": aspect_ratio}
        if urls:
            payload["urls"] = urls

        create_url = f"{self.BASE_URL}/v1/draw/completions"
        resp = requests.post(create_url, headers=self.headers, json=payload, timeout=60)
        resp.raise_for_status()
        try:
            created = resp.json()
        except Exception:
            raise RuntimeError(
                f"API 返回非 JSON 内容 (status={resp.status_code}): {resp.text[:500]}")
        data = created.get("data") or {}
        task_id = data.get("id")
        if not task_id:
            raise RuntimeError(f"未返回任务 ID: {created}")
        return task_id, created

    def poll_task_result(self, task_id: str, poll_interval: int,
                         log_callback, cancel_check=None) -> dict:
        """轮询任务结果，cancel_check() 返回 True 时提前退出"""
        poll_url = f"{self.BASE_URL}/v1/draw/result"
        for _ in range(MAX_POLL_RETRIES):
            if cancel_check and cancel_check():
                raise InterruptedError("任务已取消")
            time.sleep(poll_interval)
            for retry in range(3):
                try:
                    resp = requests.post(poll_url, headers=self.headers,
                                         json={"id": task_id}, timeout=60)
                    resp.raise_for_status()
                    break
                except requests.exceptions.HTTPError as e:
                    if e.response is not None and e.response.status_code == 429:
                        wait = 2 ** (retry + 1)
                        log_callback(f"请求过于频繁，{wait}s 后重试...")
                        time.sleep(wait)
                        continue
                    raise
            else:
                raise RuntimeError("轮询请求连续失败：429 限流")

            try:
                current = resp.json()
            except Exception:
                raise RuntimeError(
                    f"轮询 API 返回非 JSON 内容 (status={resp.status_code}): {resp.text[:500]}")

            data = current.get("data") or {}
            status = str(data.get("status") or "")
            progress = data.get("progress", 0)
            log_callback(f"任务状态: {status} (进度: {progress}%)")

            if status in {"succeeded", "failed", "violation", "cancelled"}:
                break
        return current

    def download_image(self, url: str, save_path: str):
        resp = requests.get(url, stream=True)
        resp.raise_for_status()
        with open(save_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
