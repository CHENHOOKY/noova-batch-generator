"""插件系统基类 —— 所有功能插件继承 BasePlugin

每个插件是一个独立的功能模块，删除插件文件不会影响主程序运行。

新增插件只需三步：
  1. 在 plugins/ 目录下新建 .py 文件
  2. 定义继承 BasePlugin 的类，填写 metadata
  3. 实现 create_workspace() 返回工作区界面
"""

from PySide6.QtWidgets import QPushButton, QWidget, QVBoxLayout, QLabel, QGraphicsDropShadowEffect
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor


class BasePlugin:
    """功能插件基类

    子类必须提供:
        plugin_id  - 唯一标识符
        name       - 卡片标题
        icon       - 卡片图标 (emoji)
        color      - 主题色 (hex)
        description- 卡片描述文字
        create_workspace() - 返回工作区 QWidget
    """

    plugin_id: str = ""
    name: str = "未命名插件"
    icon: str = "📦"
    color: str = "#6366F1"
    description: str = "插件描述"

    def __init__(self):
        self.main_window = None
        self._card = None
        self._workspace = None

    def set_main_window(self, window):
        self.main_window = window

    # ---- 子类必须实现 ----

    def create_workspace(self) -> QWidget:
        """创建工作区页面，点击首页卡片后显示"""
        raise NotImplementedError("插件必须实现 create_workspace()")

    # ---- 子类可选覆写 ----

    def create_card(self) -> QPushButton:
        """创建首页卡片（默认实现基于 metadata 自动生成）"""
        card = QPushButton()
        card.setMinimumHeight(180)
        card.setCursor(Qt.PointingHandCursor)
        card.setStyleSheet(f"""
            QPushButton {{
                background-color: #FFFFFF;
                border: 1px solid #ECEDF0;
                border-radius: 14px;
                text-align: left;
                padding: 0px;
            }}
            QPushButton:hover {{
                border: 2px solid {self.color};
                background-color: #FAFAFE;
            }}
        """)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 20))
        shadow.setOffset(0, 4)
        card.setGraphicsEffect(shadow)

        inner = QVBoxLayout(card)
        inner.setContentsMargins(28, 24, 28, 24)
        inner.setSpacing(10)

        icon_lbl = QLabel(self.icon)
        icon_lbl.setStyleSheet("font-size: 40px; background: transparent;")
        inner.addWidget(icon_lbl)

        title_lbl = QLabel(self.name)
        title_lbl.setStyleSheet(
            "font-size: 16px; font-weight: 700; color: #1E1E2E; background: transparent;"
        )
        inner.addWidget(title_lbl)

        desc_lbl = QLabel(self.description)
        desc_lbl.setStyleSheet(
            "font-size: 12px; color: #6B7280; line-height: 1.5; background: transparent;"
        )
        desc_lbl.setWordWrap(True)
        inner.addWidget(desc_lbl)
        inner.addStretch()

        return card

    def on_activate(self):
        """插件工作区被打开时调用（可选）"""

    def on_deactivate(self):
        """离开插件工作区时调用（可选）"""

    def stop(self):
        """停止当前插件正在运行的任务（子类可选覆写）"""

    # ---- 内部方法 ----

    def get_card(self) -> QPushButton:
        if self._card is None:
            self._card = self.create_card()
        return self._card

    def get_workspace(self) -> QWidget:
        if self._workspace is None:
            self._workspace = self.create_workspace()
        return self._workspace
