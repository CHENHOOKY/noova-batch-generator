"""分镜脚本生成器 —— 素材管理与并发生成"""

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from plugins.storyboard_generator.api_client import generate_single_image
from plugins.storyboard_generator.config import IMAGE_CONCURRENCY


@dataclass
class ImageTask:
    asset_type: str       # "character" | "scene" | "prop"
    asset_id: str         # "C01_full", "S03", etc. — unique key for grid lookup
    asset_name: str       # Chinese name
    view: str             # descriptive view label (e.g. "正面全身立绘", "雪中背影") or ""
    prompt: str           # full image generation prompt
    save_path: str = ""   # disk path where the image will be saved


def build_asset_queue(asset_plan: dict, asset_dir: str,
                      safe_title: str) -> list[ImageTask]:
    """从 Phase 2 输构建扁平化的图片生成任务队列"""
    from plugins.storyboard_generator.config import sanitize_filename

    tasks: list[ImageTask] = []

    for ca in asset_plan.get("character_assets", []):
        cid = ca.get("character_id", "C??")
        name = ca.get("name", "")
        view_label = ca.get("view_label", "")
        prompt = ca.get("prompt", "")
        if not prompt:
            continue
        safe_name = sanitize_filename(name)
        safe_view = sanitize_filename(view_label)
        filename = f"{cid}_{safe_name}_{safe_view}.png"
        asset_key = f"{cid}_{view_label}"
        tasks.append(ImageTask(
            asset_type="character",
            asset_id=asset_key,
            asset_name=f"{name}·{view_label}" if view_label else name,
            view=view_label,
            prompt=prompt,
            save_path=f"{asset_dir}/{filename}",
        ))

    for sa in asset_plan.get("scene_assets", []):
        sid = sa.get("scene_id", "S??")
        name = sa.get("name", "")
        prompt = sa.get("prompt", "")
        if not prompt:
            continue
        safe_name = sanitize_filename(name)
        filename = f"{sid}_{safe_name}.png"
        tasks.append(ImageTask(
            asset_type="scene",
            asset_id=sid,
            asset_name=name,
            view="",
            prompt=prompt,
            save_path=f"{asset_dir}/{filename}",
        ))

    for pa in asset_plan.get("prop_assets", []):
        pid = pa.get("prop_id", "P??")
        name = pa.get("name", "")
        prompt = pa.get("prompt", "")
        if not prompt:
            continue
        safe_name = sanitize_filename(name)
        filename = f"{pid}_{safe_name}.png"
        tasks.append(ImageTask(
            asset_type="prop",
            asset_id=pid,
            asset_name=name,
            view="",
            prompt=prompt,
            save_path=f"{asset_dir}/{filename}",
        ))

    return tasks


def generate_all_assets(noova_api, tasks: list[ImageTask],
                        image_model: str, image_size: str, image_ratio: str,
                        poll_interval: int = 20,
                        concurrency: int = IMAGE_CONCURRENCY,
                        log_fn=None, progress_fn=None, cancel_check=None):
    """并发生成所有素材图片。
    Yields: (task, success, filepath_or_error)
    progress_fn receives (completed_count, total_count)."""
    total = len(tasks)
    completed = 0
    lock = threading.Lock()

    def _gen_one(task: ImageTask):
        nonlocal completed
        if cancel_check and cancel_check():
            return task, False, "cancelled"
        if log_fn:
            log_fn(f"  🎨 {task.asset_id} {task.asset_name} ({task.view or 'default'})")

        ok, err = generate_single_image(
            noova_api, image_model, task.prompt,
            image_ratio, image_size, task.save_path,
            poll_interval=poll_interval, log_fn=log_fn, cancel_check=cancel_check)

        with lock:
            completed += 1
            if progress_fn:
                progress_fn(completed, total)

        return task, ok, task.save_path if ok else err

    if not tasks:
        return

    if concurrency <= 1 or total == 1:
        for task in tasks:
            yield _gen_one(task)
        return

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {executor.submit(_gen_one, t): t for t in tasks}
        for future in as_completed(futures):
            if cancel_check and cancel_check():
                for f in futures:
                    f.cancel()
                return
            yield future.result()
