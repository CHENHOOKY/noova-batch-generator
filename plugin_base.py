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

from plugins._design import lighten, C_TEXT, C_TEXT_SUB, C_TEXT_MUTED


class PluginCard(QPushButton):
    """首页功能卡片：彩色图标徽章 + 标题/描述 + 悬停点亮的「进入」入口。

    QLabel 子控件默认 textInteractionFlags=NoTextInteraction，不拦截鼠标事件，
    因此点击会穿透到 QPushButton 自身，clicked 信号可正常触发。
    """

    def __init__(self, icon, name, description, color, parent=None):
        super().__init__(parent)
        self._color = color

        badge_bg = lighten(color, 0.86)
        badge_bd = lighten(color, 0.68)
        hover_bg = lighten(color, 0.96)
        press_bg = lighten(color, 0.92)

        self.setMinimumHeight(200)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(f"""
            PluginCard {{
                background-color: #FFFFFF;
                border: 2px solid #ECEDF0;
                border-radius: 16px;
                text-align: left;
                padding: 0px;
            }}
            PluginCard:hover {{
                border: 2px solid {color};
                background-color: {hover_bg};
            }}
            PluginCard:pressed {{
                background-color: {press_bg};
            }}
        """)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(22)
        shadow.setColor(QColor(0, 0, 0, 18))
        shadow.setOffset(0, 5)
        self.setGraphicsEffect(shadow)

        inner = QVBoxLayout(self)
        inner.setContentsMargins(24, 22, 24, 20)
        inner.setSpacing(10)

        # 图标徽章（柔和主题色底）
        badge = QLabel(icon)
        badge.setFixedSize(54, 54)
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet(
            f"QLabel {{ font-size: 28px; background: {badge_bg};"
            f" border: 1px solid {badge_bd}; border-radius: 14px; }}")
        inner.addWidget(badge)
        inner.addSpacing(2)

        # 标题
        title = QLabel(name)
        title.setStyleSheet(
            f"font-size: 16px; font-weight: 700; color: {C_TEXT};"
            f" background: transparent;")
        inner.addWidget(title)

        # 描述
        desc = QLabel(description)
        desc.setStyleSheet(
            f"font-size: 12px; color: {C_TEXT_SUB}; background: transparent;")
        desc.setWordWrap(True)
        inner.addWidget(desc)

        inner.addStretch()

        # 「进入」入口（悬停点亮为主题色）
        self._enter_lbl = QLabel("进入  →")
        self._enter_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._enter_lbl.setStyleSheet(self._enter_style(False))
        inner.addWidget(self._enter_lbl)

    def _enter_style(self, hover: bool) -> str:
        col = self._color if hover else C_TEXT_MUTED
        return (f"font-size: 13px; font-weight: 600; color: {col};"
                f" background: transparent;")

    def enterEvent(self, event):
        super().enterEvent(event)
        self._enter_lbl.setStyleSheet(self._enter_style(True))

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._enter_lbl.setStyleSheet(self._enter_style(False))


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
        """创建首页卡片（默认实现基于 metadata 自动生成 PluginCard）"""
        return PluginCard(self.icon, self.name, self.description, self.color)

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
