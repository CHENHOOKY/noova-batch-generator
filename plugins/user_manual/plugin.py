"""使用手册插件 —— 集中展示 Noova 全部功能插件的图文使用手册。

架构：
  - content.py   每个页面的富 HTML 内容（依据各插件源码撰写）
  - htmlkit.py   HTML 构建工具（彩色提示框 / 参数表 / 步骤 / 代码块）
  - plugin.py    插件 UI：左侧目录导航 + 右侧 QTextBrowser 渲染
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QTextBrowser, QScrollArea, QFrame,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QPixmap, QIcon

from plugin_base import BasePlugin
from plugins._design import (
    C_BG, C_CARD_BG, C_CARD_BDR, C_PRIMARY, C_PRIMARY_HV, C_PRIMARY_SOFT,
    C_TEXT, C_TEXT_SUB, C_TEXT_MUTED, R_LG, R_MD,
)
from plugins.user_manual import content


class UserManualPlugin(BasePlugin):
    """Noova 使用手册插件"""

    plugin_id = "user_manual"
    name = "使用手册"
    icon = "📚"
    color = "#0EA5E9"
    description = ("Noova 全部功能插件的图文使用手册与快速上手指南\n"
                   "含 API 配置、参数详解、使用步骤与注意事项")

    def create_workspace(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet(f"background-color: {C_BG};")

        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 顶栏
        top = QWidget()
        top.setStyleSheet("background: transparent;")
        top_lo = QVBoxLayout(top)
        top_lo.setContentsMargins(56, 40, 56, 18)
        top_lo.setSpacing(4)

        back = self._make_back_button()
        top_lo.addWidget(back)
        top_lo.addSpacing(8)

        title = QLabel("📚  使用手册")
        title.setStyleSheet(
            f"font-size: 28px; font-weight: 700; color: {C_TEXT};"
            f" background: transparent;")
        subtitle = QLabel("Noova 全部功能的图文使用指南 —— 选择左侧目录查看对应插件说明")
        subtitle.setStyleSheet(
            f"font-size: 14px; color: {C_TEXT_SUB}; background: transparent;")
        top_lo.addWidget(title)
        top_lo.addWidget(subtitle)
        root.addWidget(top)

        # 主体：左目录 + 右内容
        body = QHBoxLayout()
        body.setContentsMargins(56, 0, 56, 40)
        body.setSpacing(20)

        body.addWidget(self._build_nav())
        body.addWidget(self._build_content(), 1)
        root.addLayout(body, 1)

        return page

    # ── 左侧目录 ──────────────────────────────
    def _build_nav(self) -> QWidget:
        card = QFrame()
        card.setFixedWidth(236)
        card.setStyleSheet(
            f"QFrame {{ background: {C_CARD_BG}; border: 1px solid {C_CARD_BDR};"
            f" border-radius: {R_LG}px; }}")

        lo = QVBoxLayout(card)
        lo.setContentsMargins(12, 14, 12, 14)
        lo.setSpacing(6)

        head = QLabel("目  录")
        head.setStyleSheet(
            f"font-size: 12px; font-weight: 700; color: {C_TEXT_MUTED};"
            f" letter-spacing: 2px; padding: 2px 8px 6px 8px;"
            f" background: transparent;")
        lo.addWidget(head)

        self._nav_list = QListWidget()
        self._nav_list.setStyleSheet(self._nav_qss())
        self._nav_list.setFrameShape(QListWidget.NoFrame)
        self._nav_list.setSpacing(2)
        self._nav_list.setCursor(Qt.PointingHandCursor)
        self._nav_list.currentRowChanged.connect(self._on_nav_changed)

        for pid, name, icon, color, _fn in content.PAGES:
            item = QListWidgetItem(f"  {icon}   {name}")
            item.setData(Qt.UserRole, pid)
            self._nav_list.addItem(item)

        lo.addWidget(self._nav_list)
        return card

    def _nav_qss(self) -> str:
        return (
            f"QListWidget {{ background: transparent; border: none; outline: none; }}"
            f"QListWidget::item {{ color: {C_TEXT_SUB}; font-size: 13.5px;"
            f" padding: 10px 10px; border-radius: {R_MD}px; }}"
            f"QListWidget::item:hover {{ background: #F5F5FA; color: {C_TEXT}; }}"
            f"QListWidget::item:selected {{ background: {C_PRIMARY_SOFT};"
            f" color: {C_PRIMARY}; font-weight: 600; }}"
        )

    # ── 右侧内容浏览器 ────────────────────────
    def _build_content(self) -> QWidget:
        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background: {C_CARD_BG}; border: 1px solid {C_CARD_BDR};"
            f" border-radius: {R_LG}px; }}")

        lo = QVBoxLayout(card)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(0)

        self._browser = QTextBrowser()
        self._browser.setOpenExternalLinks(True)
        self._browser.setFrameShape(QTextBrowser.NoFrame)
        self._browser.setStyleSheet(
            f"QTextBrowser {{ background: {C_CARD_BG}; border: none;"
            f" padding: 8px 6px; }}")
        # 默认字体
        doc = self._browser.document()
        doc.setDefaultStyleSheet(
            f"body {{ font-family: 'Microsoft YaHei'; color: {C_TEXT};"
            f" font-size: 13px; line-height: 1.6; }}")
        lo.addWidget(self._browser)

        # 默认显示第一页
        self._nav_list.setCurrentRow(0)
        return card

    # ── 事件 ──────────────────────────────────
    def _on_nav_changed(self, row: int):
        if row < 0 or row >= len(content.PAGES):
            return
        _pid, _name, _icon, color, fn = content.PAGES[row]
        html = fn()
        # 用主题色作为页面强调色基底（内容已自带配色，此处仅设 body）
        self._browser.setHtml(
            f'<html><body style="font-family:Microsoft YaHei;'
            f'color:{C_TEXT};font-size:13px;">{html}</body></html>')

    def _make_back_button(self):
        from plugins._design import make_back_button
        return make_back_button(lambda: self.main_window.switch_page(0))

    def on_activate(self):
        # 进入手册时确保首页已渲染
        if self._nav_list.currentRow() < 0:
            self._nav_list.setCurrentRow(0)
