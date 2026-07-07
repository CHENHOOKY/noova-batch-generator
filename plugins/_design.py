"""共享设计令牌与组件 — main.py / plugin_base.py / 各插件共用

本模块是整个应用的「单一设计真相源」：
  - 颜色 / 圆角 / 字体 令牌
  - 共享 QSS 片段（输入框 / 下拉 / 卡片 / 按钮 / 返回按钮）
  - 颜色工具函数（明度调节，用于派生柔和配色）
  - 复用构建函数（section_card / back_button / workspace_header）

所有插件与主壳应从此处取用设计令牌，避免各处硬编码颜色导致视觉漂移。
"""

import sys

from PySide6.QtWidgets import (
    QComboBox, QPushButton, QLabel, QFrame, QWidget, QVBoxLayout, QHBoxLayout,
)
from PySide6.QtCore import Qt


# ═══════════════════════  平台字体  ═══════════════════════
FONT_FAMILY = (
    "Microsoft YaHei" if sys.platform == "win32" else
    "PingFang SC" if sys.platform == "darwin" else
    "Noto Sans CJK SC")

# ═══════════════════════  颜色令牌  ═══════════════════════
C_BG           = "#F8F9FC"   # 应用底色
C_SIDEBAR_BG   = "#FFFFFF"   # 侧边栏
C_SIDEBAR_BDR  = "#F0F0F3"   # 侧边栏右边框
C_CARD_BG      = "#FFFFFF"   # 卡片底色
C_CARD_BDR     = "#ECEDF0"   # 卡片边框
C_CARD_BDR_HV  = "#E2E2EA"   # 卡片悬停边框

C_PRIMARY      = "#6366F1"   # 主色（靛蓝）
C_PRIMARY_HV   = "#4F46E5"   # 主色悬停
C_PRIMARY_SOFT = "#EEF2FF"   # 主色柔和底（选中态/徽章）

C_TEXT         = "#1E1E2E"   # 主文字
C_TEXT_SUB     = "#6B7280"   # 次级文字
C_TEXT_MUTED   = "#9CA3AF"   # 弱化文字

C_GREEN        = "#10B981"   # 成功 / 已配置
C_GREEN_SOFT   = "#ECFDF5"
C_AMBER        = "#F59E0B"   # 警示 / 未配置
C_AMBER_SOFT   = "#FFFBEB"
C_DANGER       = "#EF4444"   # 危险 / 终止

# ═══════════════════════  圆角令牌  ═══════════════════════
R_SM = 8
R_MD = 12
R_LG = 16
R_XL = 24


class NoScrollComboBox(QComboBox):
    """QComboBox 子类：禁用滚轮切换选项，防止误触"""

    def wheelEvent(self, event):
        event.ignore()


# ═══════════════════════  颜色工具  ═══════════════════════
def lighten(hex_color: str, amount: float = 0.85) -> str:
    """向白色混合，amount∈[0,1]，0=原色，1=纯白。用于派生柔和底色。"""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return hex_color
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    r = int(r + (255 - r) * amount)
    g = int(g + (255 - g) * amount)
    b = int(b + (255 - b) * amount)
    return f"#{r:02X}{g:02X}{b:02X}"


def with_alpha(hex_color: str, alpha: int = 255) -> str:
    """返回 rgba() 字符串，alpha∈[0,255]。"""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return hex_color
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


# ═══════════════════════  共享 QSS 片段  ═══════════════════════
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

CARD_STYLE = (
    f"QFrame {{ background: {C_CARD_BG}; border: 1px solid {C_CARD_BDR};"
    f" border-radius: {R_LG}px; }}"
)

SECTION_TITLE_STYLE = (
    f"font-size: 16px; font-weight: 700; color: {C_TEXT}; background: transparent;"
)

# 返回首页按钮（各插件工作区顶部复用）
BACK_BTN_STYLE = (
    f"QPushButton {{ background: transparent; border: none; color: {C_TEXT_SUB};"
    f" font-size: 14px; padding: 6px 0; }}"
    f"QPushButton:hover {{ color: {C_PRIMARY}; }}"
)

# 主操作按钮（开始执行 / 保存）
PRIMARY_BTN_STYLE = (
    f"QPushButton {{ background-color: {C_PRIMARY}; color: #FFFFFF; border: none;"
    f" border-radius: {R_MD}px; padding: 14px 40px; font-size: 16px; font-weight: 600; }}"
    f"QPushButton:hover {{ background-color: {C_PRIMARY_HV}; }}"
    f"QPushButton:disabled {{ background-color: #C7C9D6; }}"
)

# 次级按钮（选择文件 / 取消）
SECONDARY_BTN_STYLE = (
    f"QPushButton {{ background: #F3F4F6; border: 1px solid #E5E7EB;"
    f" border-radius: {R_SM}px; padding: 10px 20px; font-size: 14px; color: {C_TEXT}; }}"
    f"QPushButton:hover {{ background: #E5E7EB; }}"
)


# ═══════════════════════  复用构建函数  ═══════════════════════
def make_back_button(on_back) -> QPushButton:
    """生成「← 返回首页」按钮，统一各插件工作区顶栏样式。

    on_back: 点击回调（通常为 lambda: self.main_window.switch_page(0)）
    """
    btn = QPushButton("←  返回首页")
    btn.setStyleSheet(BACK_BTN_STYLE)
    btn.setCursor(Qt.PointingHandCursor)
    btn.clicked.connect(on_back)
    return btn


def make_workspace_header(icon: str, name: str, subtitle: str):
    """生成插件工作区统一标题（图标+名称 + 副标题）。

    返回 (container_widget, title_label) —— container 可直接加入布局。
    """
    container = QWidget()
    container.setStyleSheet("background: transparent;")
    lo = QVBoxLayout(container)
    lo.setContentsMargins(0, 0, 0, 0)
    lo.setSpacing(4)

    title = QLabel(f"{icon}  {name}")
    title.setStyleSheet(
        f"font-size: 28px; font-weight: 700; color: {C_TEXT}; background: transparent;")
    sub = QLabel(subtitle)
    sub.setStyleSheet(
        f"font-size: 14px; color: {C_TEXT_SUB}; background: transparent;")
    lo.addWidget(title)
    lo.addWidget(sub)
    return container, title


def make_section_card() -> QFrame:
    """生成标准白色圆角卡片容器（带边框），供表单/文件设置等区域复用。"""
    card = QFrame()
    card.setStyleSheet(
        f"QFrame {{ background: {C_CARD_BG}; border-radius: {R_LG}px;"
        f" border: 1px solid {C_CARD_BDR}; }}")
    return card


def make_chip(text: str, bg: str = "rgba(255,255,255,0.12)",
              fg: str = "rgba(255,255,255,0.92)") -> QLabel:
    """生成半透明胶囊标签（用于深色 Hero 背景）。"""
    chip = QLabel(text)
    chip.setStyleSheet(
        f"QLabel {{ background: {bg}; color: {fg};"
        f" border-radius: 12px; padding: 5px 12px;"
        f" font-size: 12px; font-weight: 500; }}")
    return chip
