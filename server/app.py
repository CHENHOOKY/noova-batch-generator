"""Noova FastAPI 本地后端 —— 复用现有 QThread 插件 worker。"""
import asyncio
import os
import sys
from pathlib import Path
from typing import List

from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.registry import PLUGINS
from server.dialogs import DialogServer
from server.task_manager import TaskManager
from config.settings_manager import SettingsManager

app = FastAPI(title="Noova API")
dialogs = DialogServer()
tasks = TaskManager()
settings = SettingsManager()
WEB_DIST = ROOT / "web" / "dist"


def _kv(opts):
    """把 (key,label,...) 元组列表转成 [{key,label}]。"""
    return [{"key": o[0], "label": o[1]} for o in opts]


def _ensure_output(path, default_name):
    p = (path or "").strip()
    if not p:
        p = os.path.join(os.path.expanduser("~"), "NoovaProjects", default_name)
    os.makedirs(p, exist_ok=True)
    return p


def _need_visual():
    k = settings.get_visual_key()
    if not k:
        raise HTTPException(400, "未配置视觉 API Key，请先在设置中填写")
    return k


def _need_text():
    k = settings.get_text_key()
    if not k:
        raise HTTPException(400, "未配置文本 API Key，请先在设置中填写")
    return k


# ── 基础 ──────────────────────────────────
@app.get("/api/plugins")
def list_plugins():
    return PLUGINS


@app.get("/api/settings")
def get_settings():
    return {
        "visual_key": settings.get_visual_key(), "text_key": settings.get_text_key(),
        "has_visual": settings.has_visual_key(), "has_text": settings.has_text_key(),
        "visual_models": settings.visual_models, "text_models": settings.text_models,
        "visual_base_url": settings.get_visual_base_url(), "text_base_url": settings.get_text_base_url(),
    }


class SettingsIn(BaseModel):
    visual_key: str | None = None
    text_key: str | None = None


@app.post("/api/settings")
def set_settings(s: SettingsIn):
    if s.visual_key is not None:
        settings.set_visual_key(s.visual_key.strip())
    if s.text_key is not None:
        settings.set_text_key(s.text_key.strip())
    settings.save()
    return {"ok": True}


# ── 原生对话框 ────────────────────────────
class FolderIn(BaseModel):
    title: str = "选择文件夹"


class OpenIn(BaseModel):
    title: str = "选择文件"
    filetypes: List[str] = []


@app.post("/api/dialog/folder")
def dialog_folder(body: FolderIn):
    return {"path": dialogs.ask_folder(body.title)}


@app.post("/api/dialog/open")
def dialog_open(body: OpenIn):
    ft = [(x, x) for x in body.filetypes] if body.filetypes else []
    return {"path": dialogs.ask_open(body.title, ft)}


@app.post("/api/dialog/open-multi")
def dialog_open_multi(body: OpenIn):
    ft = [(x, x) for x in body.filetypes] if body.filetypes else []
    return {"paths": dialogs.ask_open_multiple(body.title, ft) or []}


# ── 选项端点 ──────────────────────────────
@app.get("/api/options/{name}")
def get_options(name: str):
    if name in ("batch_draw", "folder_batch_draw"):
        from plugins._noova_api import MODEL_CONFIG
        return {"models": list(MODEL_CONFIG.keys()),
                "config": {m: {"ratios": MODEL_CONFIG[m]["ratios"], "sizes": MODEL_CONFIG[m]["sizes"]} for m in MODEL_CONFIG}}
    if name == "ecommerce":
        from plugins.ecommerce_planner.config import (CATEGORY_OPTIONS, PLATFORM_OPTIONS, TASK_TYPE_OPTIONS, ROUTING_MODES)
        from plugins._noova_api import MODEL_CONFIG
        return {"categories": CATEGORY_OPTIONS, "platforms": PLATFORM_OPTIONS,
                "task_types": TASK_TYPE_OPTIONS, "routing_modes": ROUTING_MODES,
                "image_models": list(MODEL_CONFIG.keys())}
    if name == "storyboard":
        from plugins.storyboard_generator.config import STYLE_PRESETS
        from plugins._noova_api import MODEL_CONFIG
        return {"styles": list(STYLE_PRESETS.keys()), "durations": ["8", "10", "15"],
                "image_models": list(MODEL_CONFIG.keys())}
    if name == "picture_book":
        import plugins.picture_book as pb
        from plugins._noova_api import MODEL_CONFIG
        return {"styles": _kv(pb.STYLE_OPTIONS), "scenes": _kv(pb.SCENE_OPTIONS),
                "characters": _kv(pb.CHARACTER_OPTIONS), "emotions": _kv(pb.EMOTION_OPTIONS),
                "themes": _kv(pb.THEME_OPTIONS), "narratives": _kv(pb.NARRATIVE_OPTIONS),
                "cclp": _kv(pb.CCLP_OPTIONS), "pacing": _kv(pb.PACING_OPTIONS),
                "color_mood": _kv(pb.COLOR_MOOD_OPTIONS), "supporting": _kv(pb.SUPPORTING_CHAR_OPTS),
                "animal": _kv(pb.ANIMAL_OPTS), "image_models": list(MODEL_CONFIG.keys())}
    if name == "ppt_master":
        from plugins.ppt_master.config import (DESIGN_SCHEMES, INDUSTRY_PALETTES, LAYOUT_TEMPLATES, CANVAS_OPTIONS)
        return {"design_schemes": _kv(DESIGN_SCHEMES), "industry_palettes": _kv(INDUSTRY_PALETTES),
                "layout_templates": _kv(LAYOUT_TEMPLATES), "canvas": _kv(CANVAS_OPTIONS),
                "text_models": settings.text_models}
    raise HTTPException(404, "未知选项")


# ── 信号映射 ──────────────────────────────
_SIMPLE = {
    "log_msg": lambda a: {"type": "log", "msg": a[0]},
    "progress_update": lambda a: {"type": "progress", "current": a[0], "total": a[1]},
    "finished_task": lambda a: {"type": "done", "success": a[0]},
}
_ECOM = {
    "log": lambda a: {"type": "log", "msg": a[0]},
    "progress": lambda a: {"type": "progress", "pct": a[0], "label": a[1]},
    "finished": lambda a: {"type": "done", "success": a[0], "msg": a[1]},
    "vision_ready": lambda a: {"type": "vision", "data": a[0]},
    "intent_ready": lambda a: {"type": "intent", "data": a[0]},
    "prompts_ready": lambda a: {"type": "prompts", "data": a[0]},
    "image_generated": lambda a: {"type": "image", "index": a[0], "path": a[1], "data": a[2]},
}
_SB = {
    "log": lambda a: {"type": "log", "msg": a[0]},
    "progress": lambda a: {"type": "progress", "pct": a[0], "label": a[1]},
    "finished": lambda a: {"type": "done", "success": a[0], "msg": a[1]},
    "script_ready": lambda a: {"type": "script", "data": a[0]},
    "asset_plan_ready": lambda a: {"type": "asset_plan", "data": a[0]},
    "asset_generated": lambda a: {"type": "asset", "id": a[0], "path": a[1], "success": a[2]},
    "asset_progress": lambda a: {"type": "asset_progress", "done": a[0], "total": a[1]},
    "storyboard_episode_ready": lambda a: {"type": "episode", "num": a[0], "data": a[1]},
}
_PB = {
    "log_msg": lambda a: {"type": "log", "msg": a[0]},
    "progress": lambda a: {"type": "progress", "current": a[0], "total": a[1], "phase": a[2]},
    "finished": lambda a: {"type": "done", "success": a[0], "msg": a[1]},
    "page_generated": lambda a: {"type": "page", "num": a[0], "title": a[1], "status": a[2]},
}
_PPT = {
    "log_msg": lambda a: {"type": "log", "msg": a[0]},
    "progress": lambda a: {"type": "progress", "current": a[0], "total": a[1], "phase": a[2]},
    "finished": lambda a: {"type": "done", "success": a[0], "msg": a[1]},
    "outline_ready": lambda a: {"type": "outline", "data": a[0], "dir": a[1]},
    "slide_started": lambda a: {"type": "slide_start", "num": a[0], "title": a[1], "status": a[2]},
    "slide_completed": lambda a: {"type": "slide_done", "num": a[0], "title": a[1], "status": a[2], "ok": a[3]},
}


# ── 图像放大 ──────────────────────────────
class UpscaleIn(BaseModel):
    input_dir: str
    output_dir: str
    output_format: str = "png"


@app.post("/api/tasks/upscale")
def start_upscale(body: UpscaleIn):
    if not os.path.isdir(body.input_dir):
        raise HTTPException(400, "输入文件夹不存在")
    tid = tasks.start_upscale(body.input_dir, _ensure_output(body.output_dir, "upscale"), body.output_format)
    return {"task_id": tid}


# ── 批量出图 ──────────────────────────────
class BatchDrawIn(BaseModel):
    excel_path: str
    output_dir: str
    model: str
    aspect_ratio: str
    image_size: str
    poll_interval: int = 20
    concurrency: int = 1


@app.post("/api/tasks/batch_draw")
def start_batch_draw(body: BatchDrawIn):
    api_key = _need_visual()
    if not os.path.isfile(body.excel_path):
        raise HTTPException(400, "Excel 文件不存在")
    from plugins.batch_draw import BatchDrawWorker
    w = BatchDrawWorker(api_key, body.excel_path, _ensure_output(body.output_dir, "batch_draw"),
                        body.model, body.aspect_ratio, body.image_size, body.poll_interval, body.concurrency)
    return {"task_id": tasks.start_worker(w, _SIMPLE)}


# ── 文件夹批量出图 ────────────────────────
class GroupIn(BaseModel):
    prompt: str
    folder: str = ""
    fixed1: str = ""
    fixed2: str = ""
    output_dir: str = ""


class FolderBatchIn(BaseModel):
    output_dir: str
    default_input_dir: str = ""
    groups: List[GroupIn]
    model: str
    aspect_ratio: str
    image_size: str
    poll_interval: int = 20
    concurrency: int = 1
    output_mode: str = "prompt"


@app.post("/api/tasks/folder_batch_draw")
def start_folder_batch_draw(body: FolderBatchIn):
    api_key = _need_visual()
    groups = []
    for g in body.groups:
        if not g.prompt.strip():
            continue
        d = g.model_dump()
        if not d.get("folder"):
            d["folder"] = body.default_input_dir
        groups.append(d)
    if not groups:
        raise HTTPException(400, "至少需要一组提示词")
    if not any(g["folder"] for g in groups):
        raise HTTPException(400, "请先选择「默认参考图文件夹」，或为每组单独选择参考图文件夹")
    from plugins.folder_batch_draw import FolderBatchDrawWorker
    w = FolderBatchDrawWorker(api_key, groups, _ensure_output(body.output_dir, "folder_batch_draw"),
                              body.model, body.aspect_ratio, body.image_size, body.poll_interval, body.concurrency,
                              settings.get_fixed_image_1_path(), settings.get_fixed_image_2_path(), body.output_mode)
    return {"task_id": tasks.start_worker(w, _SIMPLE)}


# ── 电商图 ────────────────────────────────
class EcommerceIn(BaseModel):
    product_name: str
    category: str
    material: str = ""
    color_desc: str = ""
    brand_marks: str = ""
    platform: str
    task_type: str
    style_direction: str = ""
    is_redesign: bool = False
    product_image_paths: List[str] = []
    ref_image_paths: List[str] = []
    image_count: int = 3
    aspect_ratio: str = "1:1"
    image_size: str = "1K"
    image_model: str = "nano-banana-pro"
    ds_model: str = "deepseek-v4-pro"
    output_dir: str = ""


@app.post("/api/tasks/ecommerce")
def start_ecommerce(body: EcommerceIn):
    text_key = _need_text()
    img_key = _need_visual()
    from plugins.ecommerce_planner.worker import EcommerceWorker
    w = EcommerceWorker(text_key, settings.get_text_base_url(), body.ds_model,
                        body.product_name, body.category, body.material, body.color_desc, body.brand_marks,
                        body.platform, body.task_type, body.style_direction, body.is_redesign,
                        body.product_image_paths, body.ref_image_paths, body.image_count,
                        img_key, body.image_model, body.aspect_ratio, body.image_size,
                        settings.get_visual_base_url(), _ensure_output(body.output_dir, "ecommerce"))
    return {"task_id": tasks.start_worker(w, _ECOM)}


# ── 分镜脚本生成器 ────────────────────────
class StoryboardIn(BaseModel):
    story_text: str
    style_label: str
    episode_count: int = 4
    duration: int = 15
    ds_model: str = "deepseek-v4-pro"
    image_model: str = "nano-banana-pro"
    image_size: str = "1K"
    image_ratio: str = "16:9"
    run_images: bool = True
    project_dir: str = ""


@app.post("/api/tasks/storyboard")
def start_storyboard(body: StoryboardIn):
    text_key = _need_text()
    img_key = _need_visual()
    from plugins._noova_api import NoovaAPI
    from plugins.storyboard_generator.config import STYLE_PRESETS
    from plugins.storyboard_generator.worker import StoryboardWorker
    noova = NoovaAPI(img_key)
    style_desc = STYLE_PRESETS.get(body.style_label, "")
    w = StoryboardWorker(text_key, settings.get_text_base_url(), body.ds_model, noova,
                         body.image_model, body.image_size, body.image_ratio, body.story_text,
                         body.style_label, style_desc, body.episode_count, body.duration,
                         _ensure_output(body.project_dir, "storyboard"), body.run_images)
    return {"task_id": tasks.start_worker(w, _SB)}


# ── 绘本魔法师 ────────────────────────────
class PictureBookIn(BaseModel):
    style_key: str = "watercolor"
    scene_key: str = "meadow"
    age: int = 5
    pages: int = 4
    character_key: str = "yueyue"
    emotion: str = ""
    theme: str = ""
    custom_topic: str = ""
    story_title: str = ""
    narrative: str = ""
    cclp_mode: str = ""
    pacing: str = ""
    color_mood: str = ""
    generate_images: bool = True
    image_model: str = "nano-banana-pro"
    aspect_ratio: str = "1:1"
    image_size: str = "1K"
    output_formats: List[str] = ["markdown"]
    output_dir: str = ""
    text_model: str = "deepseek-v4-pro"


@app.post("/api/tasks/picture_book")
def start_picture_book(body: PictureBookIn):
    text_key = _need_text()
    img_key = _need_visual()
    import plugins.picture_book as pb
    from plugins.picture_book import PictureBookWorker

    def first(opts):
        return opts[0][0] if opts else ""

    w = PictureBookWorker(
        text_key, settings.get_text_base_url(), body.text_model,
        img_key, settings.get_visual_base_url(), body.image_model,
        body.style_key, body.scene_key, body.age, body.pages, body.character_key,
        body.emotion, body.theme, body.cclp_mode or first(pb.CCLP_OPTIONS),
        body.narrative or first(pb.NARRATIVE_OPTIONS), body.pacing or first(pb.PACING_OPTIONS),
        body.color_mood or first(pb.COLOR_MOOD_OPTIONS), [], [],
        body.custom_topic, body.story_title, _ensure_output(body.output_dir, "picture_book"),
        [f for f in body.output_formats if f != "pdf"], body.generate_images,
        body.aspect_ratio, body.image_size)
    return {"task_id": tasks.start_worker(w, _PB)}


# ── PPT 大师 ──────────────────────────────
class PPTIn(BaseModel):
    prompt: str
    page_count: int = 10
    canvas_key: str = "ppt169"
    design_scheme_key: str = "general"
    industry_key: str = "none"
    layout_key: str = "none"
    custom_style: str = ""
    output_dir: str = ""
    model: str = "deepseek-v4-pro"


@app.post("/api/tasks/ppt_master")
def start_ppt(body: PPTIn):
    text_key = _need_text()
    from plugins.ppt_master.config import (DESIGN_SCHEMES, INDUSTRY_PALETTES, LAYOUT_TEMPLATES, CANVAS_OPTIONS, CANVAS_VIEWBOX)
    from plugins.ppt_master.worker import PPTGenerateWorker

    def find(lst, key):
        for t in lst:
            if t[0] == key:
                return t
        return lst[0] if lst else None

    ds = find(DESIGN_SCHEMES, body.design_scheme_key)
    ind = find(INDUSTRY_PALETTES, body.industry_key) or ("none", "（不使用行业配色）", {})
    lay = find(LAYOUT_TEMPLATES, body.layout_key) or ("none", "（默认布局）", "")
    viewbox = CANVAS_VIEWBOX.get(body.canvas_key, CANVAS_VIEWBOX.get("ppt169", "0 0 1280 720"))
    w = PPTGenerateWorker(text_key, settings.get_text_base_url(), body.model, body.prompt, body.page_count,
                          body.canvas_key, viewbox, _ensure_output(body.output_dir, "ppt_master"),
                          ds, ind, lay, body.custom_style, [], "full", None, "")
    return {"task_id": tasks.start_worker(w, _PPT)}


# ── 任务状态 / 停止 ───────────────────────
@app.get("/api/tasks/{tid}")
def task_status(tid: str):
    s = tasks.status(tid)
    if not s:
        raise HTTPException(404, "任务不存在")
    return s


@app.post("/api/tasks/{tid}/stop")
def task_stop(tid: str):
    if not tasks.stop(tid):
        raise HTTPException(404, "任务不存在")
    return {"ok": True}


@app.websocket("/ws/tasks/{tid}")
async def ws_tasks(ws: WebSocket, tid: str):
    await ws.accept()
    import json
    try:
        while True:
            evs = tasks.drain(tid)
            for ev in evs:
                try:
                    await ws.send_json(ev)
                except Exception:
                    await ws.send_text(json.dumps({"type": "log", "msg": str(ev)}, ensure_ascii=False))
            st = tasks.status(tid)
            if st and st["status"] == "done" and not evs:
                await ws.send_json({"type": "done", "success": st["success"]})
                break
            if st is None:
                await ws.send_json({"type": "error", "msg": "任务不存在"})
                break
            await asyncio.sleep(0.12)
    except Exception:
        pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass


# ── 使用手册（复用 plugins.user_manual 的 HTML 内容）────────
@app.get("/api/manual/pages")
def manual_pages():
    from plugins.user_manual import content
    return [{"id": pid, "title": name, "icon": icon, "color": color} for (pid, name, icon, color, _fn) in content.PAGES]


@app.get("/api/manual/{pid}")
def manual_page(pid: str):
    from plugins.user_manual import content
    for (p, n, i, c, fn) in content.PAGES:
        if p == pid:
            return {"html": fn()}
    raise HTTPException(404, "页面不存在")


# ── 前端静态资源 ──────────────────────────
if WEB_DIST.exists() and (WEB_DIST / "index.html").exists():
    assets = WEB_DIST / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        p = WEB_DIST / full_path
        if full_path and p.is_file():
            return FileResponse(str(p))
        return FileResponse(str(WEB_DIST / "index.html"))
else:
    @app.get("/")
    def no_frontend():
        return JSONResponse({"message": "前端未构建。请在 web/ 目录执行: npm install && npm run build"}, status_code=200)
