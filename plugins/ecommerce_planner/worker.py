"""电商图 —— 后台 Worker（4 阶段编排）

Phase 0: DeepSeek 文本视觉推理 (M1 + M3)
Phase 1: DeepSeek 意图解析 (M2)
Phase 2: DeepSeek 出图提示词生成 (N 个 image_prompt)
Phase 3: Noova API 批量出图
"""

import json
import os
import time
from datetime import datetime

from PySide6.QtCore import QThread, Signal

from plugins._text_api import call_text_api_with_retry
from plugins._utils import extract_json, safe_traceback
from plugins._noova_api import NoovaAPI
from plugins.ecommerce_planner.prompts import (
    VISUAL_INFERENCE_SYSTEM, make_visual_inference_user,
    INTENT_SYSTEM, make_intent_user,
    IMAGE_PROMPT_SYSTEM, make_image_prompt_user,
)
from plugins.ecommerce_planner.config import (
    DEFAULT_MAX_TOKENS, DEFAULT_TEMPERATURE,
    MAX_POLL_RETRIES, NOOVA_BASE_URL,
)


class EcommerceWorker(QThread):
    # Phase 0
    vision_ready = Signal(dict)
    # Phase 1
    intent_ready = Signal(dict)
    # Phase 2
    prompts_ready = Signal(dict)
    # Phase 3 — per image
    image_generated = Signal(int, str, dict)
    # Generic
    log = Signal(str)
    progress = Signal(int, str)
    finished = Signal(bool, str)

    def __init__(self, api_key: str, base_url: str, ds_model: str,
                 product_name: str, category: str, material: str,
                 color_desc: str, brand_marks: str, platform: str,
                 task_type: str, style_direction: str, is_redesign: bool,
                 product_image_paths: list, ref_image_paths: list,
                 image_count: int,
                 image_api_key: str, image_model: str,
                 aspect_ratio: str, image_size: str,
                 image_base_url: str = NOOVA_BASE_URL,
                 output_dir: str = "", parent=None):
        super().__init__(parent)
        self._api_key = api_key
        self._base_url = base_url
        self._ds_model = ds_model
        self._product_name = product_name
        self._category = category
        self._material = material
        self._color_desc = color_desc
        self._brand_marks = brand_marks
        self._platform = platform
        self._task_type = task_type
        self._style_direction = style_direction
        self._is_redesign = is_redesign
        self._product_image_paths = product_image_paths
        self._ref_image_paths = ref_image_paths
        self._image_count = image_count
        self._image_api_key = image_api_key
        self._image_model = image_model
        self._aspect_ratio = aspect_ratio
        self._image_size = image_size
        self._image_base_url = image_base_url
        self._output_dir = output_dir
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            self._do_all()
        except Exception as e:
            if not self._cancel:
                self.log.emit(f"[FATAL] {e}")
                self.log.emit(safe_traceback())
                self.finished.emit(False, str(e))

    def _ds(self, system: str, user: str, max_tokens: int = DEFAULT_MAX_TOKENS,
            json_mode: bool = True) -> str:
        return call_text_api_with_retry(
            self._api_key, self._base_url, self._ds_model,
            system, user,
            temperature=DEFAULT_TEMPERATURE, max_tokens=max_tokens,
            json_mode=json_mode, log_fn=self.log.emit)

    def _do_all(self):
        # ═══ Phase 0: Visual Inference ═══
        self.log.emit("🔍 Phase 0/3: 视觉特征推理中...")
        self.progress.emit(5, "视觉推理中...")

        raw = self._ds(
            VISUAL_INFERENCE_SYSTEM,
            make_visual_inference_user(
                self._product_name, self._category, self._material,
                self._color_desc, self._brand_marks, self._platform,
                self._task_type, self._style_direction,
                self._is_redesign,
                len(self._product_image_paths),
                [os.path.basename(p) for p in self._ref_image_paths]),
            max_tokens=16384)
        vision_data = extract_json(raw)
        routing = vision_data.get("routing_mode", "?")
        self.log.emit(
            f"  ✓ 路由模式: {vision_data.get('routing_mode_label', routing)}")
        self.vision_ready.emit(vision_data)
        self.progress.emit(25, "视觉推理完成")
        if self._cancel:
            return

        # ═══ Phase 1: Intent Parsing ═══
        self.log.emit("📝 Phase 1/3: 意图矩阵解析中...")
        self.progress.emit(30, "意图解析中...")

        raw = self._ds(
            INTENT_SYSTEM,
            make_intent_user(
                json.dumps(vision_data, ensure_ascii=False, indent=2),
                self._product_name, self._platform,
                self._task_type, self._style_direction),
            max_tokens=16384)
        intent_data = extract_json(raw)
        im = intent_data.get("intent_matrix", {})
        self.log.emit(
            f"  ✓ 意图解析完成 — 冲突: {im.get('conflict_resolution', '?')}")
        self.intent_ready.emit(intent_data)
        self.progress.emit(50, "意图解析完成")
        if self._cancel:
            return

        # ═══ Phase 2: Image Prompt Generation ═══
        self.log.emit(f"🎨 Phase 2/3: 生成 {self._image_count} 套出图提示词...")
        self.progress.emit(55, "提示词生成中...")

        raw = self._ds(
            IMAGE_PROMPT_SYSTEM,
            make_image_prompt_user(
                json.dumps(intent_data, ensure_ascii=False, indent=2),
                json.dumps(vision_data, ensure_ascii=False, indent=2),
                self._product_name, self._platform, self._task_type,
                self._image_count,
                len(self._product_image_paths),
                len(self._ref_image_paths)),
            max_tokens=DEFAULT_MAX_TOKENS)
        prompts_data = extract_json(raw)
        proposals = prompts_data.get("proposals", [])
        self.log.emit(f"  ✓ 提示词生成完成 — {len(proposals)} 套方案")
        self.prompts_ready.emit(prompts_data)
        self.progress.emit(65, "提示词生成完成")
        if self._cancel:
            return

        # ═══ Phase 3: Image Generation (Noova API) ═══
        self.log.emit(f"🖼️  Phase 3/3: 调用出图 API 生成 {len(proposals)} 张方案图...")

        os.makedirs(self._output_dir, exist_ok=True)
        api = NoovaAPI(self._image_api_key)
        if self._image_base_url and self._image_base_url != NOOVA_BASE_URL:
            api.BASE_URL = self._image_base_url.rstrip("/")

        # Convert uploaded reference images to base64
        ref_urls = []
        all_ref_paths = self._product_image_paths + self._ref_image_paths
        for p in all_ref_paths:
            if os.path.exists(p):
                try:
                    b64 = api.local_file_to_base64(p, self.log.emit)
                    ref_urls.append(b64)
                except Exception as e:
                    self.log.emit(f"  [WARN] 参考图编码失败 {os.path.basename(p)}: {e}")
        if ref_urls:
            self.log.emit(f"  ✓ 已编码 {len(ref_urls)} 张参考图 (产品图+风格参考)")

        generated = 0
        for i, proposal in enumerate(proposals):
            if self._cancel:
                break

            style_name = proposal.get("style_name", f"方案{i+1}")
            image_prompt = proposal.get("image_prompt", "")
            if not image_prompt:
                self.log.emit(f"  [WARN] 方案 {i+1} ({style_name}) 无 image_prompt，跳过")
                continue

            pct = 65 + int(35 * (i + 1) / len(proposals))
            self.progress.emit(pct, f"出图中 {i+1}/{len(proposals)}: {style_name}")
            self.log.emit(f"  方案 {i+1}/{len(proposals)}: {style_name} — 提交出图...")

            try:
                task_id, _ = api.create_draw_task(
                    self._image_model, image_prompt,
                    self._aspect_ratio, self._image_size, urls=ref_urls)
                self.log.emit(f"    task_id={task_id}, 等待结果...")

                result = api.poll_task_result(
                    task_id, poll_interval=5,
                    log_callback=self.log.emit,
                    cancel_check=lambda: self._cancel)

                if self._cancel:
                    break

                status = str((result.get("data") or {}).get("status") or "")
                if status == "succeeded":
                    results = (result.get("data") or {}).get("results", [])
                    if results:
                        img_url = results[0].get("url")
                        save_path = os.path.join(
                            self._output_dir,
                            f"proposal_{i+1:02d}_{datetime.now().strftime('%H%M%S')}.png")
                        api.download_image(img_url, save_path)
                        self.image_generated.emit(i, save_path, proposal)
                        generated += 1
                        self.log.emit(f"    [OK] 已保存: {os.path.basename(save_path)}")
                    else:
                        self.log.emit(f"    [WARN] 任务成功但无图片返回")
                else:
                    self.log.emit(f"    [WARN] 任务状态: {status}")
            except Exception as e:
                self.log.emit(f"    [ERROR] 方案 {i+1} 出图失败: {e}")

        self.progress.emit(100, "完成!")
        self.finished.emit(True, f"成功生成 {generated}/{len(proposals)} 张方案图")
