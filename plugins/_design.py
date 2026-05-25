"""共享设计令牌 — main.py / plugin_base.py / 各插件共用"""

import sys

# ── 平台字体 ──────────────────────────────
FONT_FAMILY = (
    "Microsoft YaHei" if sys.platform == "win32" else
    "PingFang SC" if sys.platform == "darwin" else
    "Noto Sans CJK SC")

# ── 颜色 ─────────────────────────────────
C_BG          = "#F8F9FC"
C_SIDEBAR_BG  = "#FFFFFF"
C_SIDEBAR_BDR = "#F0F0F3"
C_CARD_BG     = "#FFFFFF"
C_CARD_BDR    = "#ECEDF0"
C_PRIMARY     = "#6366F1"
C_TEXT        = "#1E1E2E"
C_TEXT_SUB    = "#6B7280"

# ── 共享 QSS 片段 ─────────────────────────
COMBO_STYLE = (
    "QComboBox { border: 1px solid #E5E7EB; border-radius: 10px;"
    " padding: 10px 14px; font-size: 14px; background: #FAFAFA; color: #1A1A1A; }"
    "QComboBox:focus { border: 1px solid #6366F1; background: #FFFFFF; }"
    "QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right;"
    " width: 24px; border-left: 1px solid #E5E7EB; border-top-right-radius: 10px;"
    " border-bottom-right-radius: 10px; }"
    "QComboBox QAbstractItemView { background: #FFFFFF; color: #1A1A1A;"
    " border: 1px solid #E5E7EB; border-radius: 6px; selection-background-color: #EEF2FF;"
    " selection-color: #1A1A1A; outline: none; }"
)

INPUT_STYLE = (
    "QLineEdit { border: 1px solid #E5E7EB; border-radius: 10px;"
    " padding: 10px 14px; font-size: 14px; background: #FAFAFA; }"
    "QLineEdit:focus { border: 1px solid #6366F1; background: #FFFFFF; }"
)
