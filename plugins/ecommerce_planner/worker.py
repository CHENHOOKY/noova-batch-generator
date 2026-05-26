"""电商套图AI规划器 —— 后台 Worker（2 阶段编排）"""

import json
from datetime import datetime

from PySide6.QtCore import QThread, Signal

from plugins._text_api import call_text_api_with_retry
from plugins._utils import extract_json, safe_traceback
from plugins.ecommerce_planner.prompts import (
    INTENT_SYSTEM, make_intent_user,
    PROPOSAL_SYSTEM, make_proposal_user,
)
from plugins.ecommerce_planner.config import DEFAULT_MAX_TOKENS, DEFAULT_TEMPERATURE


class EcommerceWorker(QThread):
    # Phase 1
    intent_ready = Signal(dict)
    # Phase 2
    proposals_ready = Signal(dict)
    # Generic
    log = Signal(str)
    progress = Signal(int, str)
    finished = Signal(bool, str)

    def __init__(self, api_key: str, base_url: str, ds_model: str,
                 product_name: str, category: str, material: str,
                 color_desc: str, brand_marks: str, platform: str,
                 task_type: str, style_direction: str, parent=None):
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
        # ═══ Phase 1: Intent Analysis ═══
        self.log.emit("📝 Phase 1/2: 意图解析中...")
        self.progress.emit(10, "意图解析中...")

        raw = self._ds(
            INTENT_SYSTEM,
            make_intent_user(
                self._product_name, self._category, self._material,
                self._color_desc, self._brand_marks, self._platform,
                self._task_type, self._style_direction),
            max_tokens=16384)
        intent = extract_json(raw)
        self.log.emit(
            f"  ✓ 意图解析完成 — "
            f"模式: {intent.get('routing_mode', '?')}, "
            f"风格锚点: {intent.get('intent_matrix', {}).get('level_2_style_expansion', {}).get('mode', '?')}")
        self.intent_ready.emit(intent)
        self.progress.emit(45, "意图解析完成")

        if self._cancel:
            return

        # ═══ Phase 2: Proposal Generation ═══
        self.log.emit("🎨 Phase 2/2: 多智能体方案推演中...")
        self.progress.emit(50, "方案推演中...")

        raw = self._ds(
            PROPOSAL_SYSTEM,
            make_proposal_user(
                json.dumps(intent, ensure_ascii=False, indent=2),
                self._product_name, self._platform, self._task_type),
            max_tokens=DEFAULT_MAX_TOKENS)
        proposals = extract_json(raw)
        opt_count = len(proposals.get("options", []))
        self.log.emit(f"  ✓ 方案生成完成 — {opt_count} 套方案")
        self.proposals_ready.emit(proposals)
        self.progress.emit(100, "完成!")

        self.finished.emit(True, f"{opt_count} 套视觉方案生成完成！")
