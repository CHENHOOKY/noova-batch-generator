"""全局设置管理器 — 持久化 API Key 到 ~/.noova/settings.json"""

import json
import os
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from plugins._noova_api import MODEL_CONFIG

SETTINGS_DIR = Path.home() / ".noova"
SETTINGS_PATH = SETTINGS_DIR / "settings.json"

DEFAULT_SETTINGS = {
    "visual_api_key": "",
    "visual_base_url": "https://noova.cn",
    "text_api_key": "",
    "text_base_url": "https://apic.dpdns.org",
}

TEXT_MODELS = [
    "gpt-5.4",
    "gpt-5.5",
    "claude-opus-4-6",
    "claude-opus-4-7",
    "deepseek-v4-pro",
    "deepseek-v4-flash",
]


class SettingsManager(QObject):
    settings_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = dict(DEFAULT_SETTINGS)
        self._load()

    # ── 文件读写 ──────────────────────────────

    def _load(self):
        try:
            if SETTINGS_PATH.exists():
                with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                for k in DEFAULT_SETTINGS:
                    if k in saved:
                        self._data[k] = saved[k]
        except Exception:
            pass

        if not self._data.get("visual_api_key"):
            env_val = os.environ.get("NOOVA_API_KEY", "")
            if env_val:
                self._data["visual_api_key"] = env_val

        if not self._data.get("text_api_key"):
            env_val = os.environ.get("DEEPSEEK_API_KEY", "")
            if env_val:
                self._data["text_api_key"] = env_val

    def save(self):
        SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
        self.settings_changed.emit()

    # ── Getters ───────────────────────────────

    def get_visual_key(self) -> str:
        return self._data.get("visual_api_key", "")

    def get_text_key(self) -> str:
        return self._data.get("text_api_key", "")

    def get_visual_base_url(self) -> str:
        return self._data.get("visual_base_url", "https://noova.cn")

    def get_text_base_url(self) -> str:
        return self._data.get("text_base_url", "https://apic.dpdns.org")

    def has_visual_key(self) -> bool:
        return bool(self._data.get("visual_api_key", ""))

    def has_text_key(self) -> bool:
        return bool(self._data.get("text_api_key", ""))

    # ── Setters ───────────────────────────────

    def set_visual_key(self, key: str):
        self._data["visual_api_key"] = key

    def set_text_key(self, key: str):
        self._data["text_api_key"] = key

    # ── 只读模型列表 ────────────────────────────

    @property
    def visual_models(self) -> list:
        return list(MODEL_CONFIG.keys())

    @property
    def text_models(self) -> list:
        return list(TEXT_MODELS)
