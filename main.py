"""Noova AI 批量出图助手 —— 主程序入口

架构说明:
  - plugin_base.py  定义插件协议 (BasePlugin)
  - plugins/        每个 .py 文件是一个独立的功能插件
  - main.py         主程序壳：侧边栏、首页卡片区、插件路由、共享监控台

新增功能：在 plugins/ 下新建文件，写一个继承 BasePlugin 的类即可自动注册。
删除插件：直接删除对应 .py 文件，不影响任何其他功能。
"""

__version__ = "2.1.0"

import os
import sys
import importlib
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QStackedWidget, QScrollArea, QGridLayout,
    QProgressBar, QTextEdit, QButtonGroup,
)
from PySide6.QtCore import Qt, Signal

from plugin_base import BasePlugin

# ═══════════════════════  Design Tokens  ═══════════════════════
C_BG          = "#F8F9FC"
C_SIDEBAR_BG  = "#FFFFFF"
C_SIDEBAR_BDR = "#F0F0F3"
C_CARD_BG     = "#FFFFFF"
C_CARD_BDR    = "#ECEDF0"
C_PRIMARY     = "#6366F1"
C_PRIMARY_HV  = "#4F46E5"
C_TEXT        = "#1E1E2E"
C_TEXT_SUB    = "#6B7280"
C_TEXT_MUTED  = "#9CA3AF"
C_GREEN       = "#10B981"
C_DANGER      = "#EF4444"

R_SM  = 8
R_MD  = 12
R_LG  = 16
R_XL  = 24

class ModernAppShell(QMainWindow):
    """主程序壳 —— 管理整体布局、插件路由、共享监控台"""

    stop_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Noova AI 批量出图助手")
        self.resize(1024, 720)
        self.setMinimumSize(920, 620)

        self._plugins: list[BasePlugin] = []
        self._plugin_by_id: dict[str, BasePlugin] = {}
        self._plugin_nav_buttons: dict[str, QPushButton] = {}
        self._opened_plugins: list[str] = []       # 按最近打开排序
        self._current_page = 0

        self._init_styles()
        self._build_shell()
        self._load_plugins()
        self._build_home_page()
        self._build_monitor_page()

    # ═══════════════════════  全局样式  ═══════════════════════
    def _init_styles(self):
        self.setStyleSheet(
            "QMainWindow { background-color: " + C_BG + "; }"
            "QWidget#Sidebar {"
            " background-color: " + C_SIDEBAR_BG + ";"
            " border-right: 1px solid " + C_SIDEBAR_BDR + "; }"
            # 侧边栏导航按钮
            "QPushButton#NavBtn {"
            " text-align: left; padding: 10px 16px; border: none;"
            " border-left: 3px solid transparent;"
            " border-radius: 0 " + str(R_SM) + "px " + str(R_SM) + "px 0;"
            " font-size: 14px; color: " + C_TEXT_SUB + "; font-weight: 500; }"
            "QPushButton#NavBtn:hover {"
            " background-color: #F5F5FA; color: " + C_TEXT + "; }"
            "QPushButton#NavBtn:checked {"
            " background-color: #F4F4FF;"
            " border-left: 3px solid " + C_PRIMARY + ";"
            " color: " + C_PRIMARY + "; font-weight: 600; }"
            # 监控台
            "QTextEdit#MonitorLog {"
            " border: 1px solid " + C_CARD_BDR + ";"
            " border-radius: " + str(R_MD) + "px; padding: 14px;"
            " background-color: #FFFFFF; font-size: 13px;"
            " color: " + C_TEXT + "; }"
            "QProgressBar#MonitorProgress {"
            " border: none; background-color: #EEEEF2;"
            " border-radius: 6px; height: 10px;"
            " text-align: center; color: transparent; }"
            "QProgressBar#MonitorProgress::chunk {"
            " background-color: " + C_PRIMARY + "; border-radius: 6px; }"
            # 全局滚动条
            "QScrollBar:vertical {"
            " width: 6px; background: transparent; border: none; }"
            "QScrollBar::handle:vertical {"
            " background: #D1D5DB; border-radius: 3px; min-height: 30px; }"
            "QScrollBar::handle:vertical:hover { background: #9CA3AF; }"
            "QScrollBar::add-line:vertical,"
            " QScrollBar::sub-line:vertical { height: 0px; }"
            "QScrollBar:horizontal {"
            " height: 6px; background: transparent; border: none; }"
            "QScrollBar::handle:horizontal {"
            " background: #D1D5DB; border-radius: 3px; min-width: 30px; }"
            "QScrollBar::add-line:horizontal,"
            " QScrollBar::sub-line:horizontal { width: 0px; }"
            # 输入控件焦点
            "QLineEdit:focus, QComboBox:focus, QSpinBox:focus {"
            " border: 1px solid " + C_PRIMARY + "; }"
        )

    # ═══════════════════════  主布局骨架  ═══════════════════════
    def _build_shell(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- 侧边栏 ---
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(240)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(16, 28, 16, 28)
        side_layout.setSpacing(6)

        logo = QLabel("Noova AI")
        logo.setStyleSheet(
            "font-size: 20px; font-weight: 800; color: " + C_TEXT + ";"
            " padding: 0 10px 24px 10px; background: transparent;")
        side_layout.addWidget(logo)

        self._nav_group = QButtonGroup()
        self._nav_group.setExclusive(True)

        self.nav_home = QPushButton("    Noova应用")
        self.nav_home.setObjectName("NavBtn")
        self.nav_home.setCheckable(True)
        self.nav_home.setChecked(True)
        self.nav_home.setCursor(Qt.PointingHandCursor)
        self.nav_home.clicked.connect(lambda: self.switch_page(0))
        self._nav_group.addButton(self.nav_home)
        side_layout.addWidget(self.nav_home)

        # 插件导航区域（初始隐藏，首次打开插件时显示）
        self._nav_plugin_section = QWidget()
        self._nav_plugin_section.setVisible(False)
        plugin_nav_layout = QVBoxLayout(self._nav_plugin_section)
        plugin_nav_layout.setContentsMargins(0, 6, 0, 4)
        plugin_nav_layout.setSpacing(2)

        self._nav_plugin_sep = QLabel("  已打开")
        self._nav_plugin_sep.setStyleSheet(
            "color: " + C_TEXT_MUTED + "; font-size: 11px; font-weight: 500;"
            " padding: 4px 10px 2px 10px; background: transparent;")
        plugin_nav_layout.addWidget(self._nav_plugin_sep)

        self._plugin_btn_container = QVBoxLayout()
        self._plugin_btn_container.setSpacing(2)
        plugin_nav_layout.addLayout(self._plugin_btn_container)
        side_layout.addWidget(self._nav_plugin_section)

        # 监控台导航（初始隐藏）
        self.nav_monitor = QPushButton("   运行监控台")
        self.nav_monitor.setObjectName("NavBtn")
        self.nav_monitor.setCheckable(True)
        self.nav_monitor.setVisible(False)
        self.nav_monitor.setCursor(Qt.PointingHandCursor)
        self.nav_monitor.clicked.connect(
            lambda: self.switch_page(self._monitor_index()))
        self._nav_group.addButton(self.nav_monitor)
        side_layout.addWidget(self.nav_monitor)

        side_layout.addStretch()

        ver = QLabel("v" + __version__)
        ver.setStyleSheet(
            "color: " + C_TEXT_MUTED + "; font-size: 12px; padding-left: 10px;"
            " background: transparent;")
        side_layout.addWidget(ver)

        main_layout.addWidget(sidebar)

        # 页面容器
        self.stacked_widget = QStackedWidget()
        main_layout.addWidget(self.stacked_widget, 1)

    # ═══════════════════════  插件发现与注册  ═══════════════════════
    def _load_plugins(self):
        import plugins
        import pkgutil

        module_names = set()

        for info in pkgutil.iter_modules(plugins.__path__, plugins.__name__ + "."):
            if not info.name.endswith(".__init__"):
                module_names.add(info.name)
                print(f"[发现] pkgutil: {info.name}")

        scan_dirs = [Path(__file__).parent / "plugins"]
        if getattr(sys, "frozen", False):
            scan_dirs.append(Path(sys._MEIPASS) / "plugins")
        for p in plugins.__path__:
            pp = Path(p)
            if pp.is_dir() and pp not in scan_dirs:
                scan_dirs.append(pp)

        for scan_dir in scan_dirs:
            if scan_dir.is_dir():
                for f in scan_dir.glob("*.py"):
                    if not f.name.startswith("_"):
                        module_names.add(f"plugins.{f.stem}")
                        print(f"[发现] 文件扫描: plugins.{f.stem}")

        print(f"[信息] 候选插件模块: {sorted(module_names)}")

        for name in sorted(module_names):
            try:
                module = importlib.import_module(name)
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (isinstance(attr, type)
                            and issubclass(attr, BasePlugin)
                            and attr is not BasePlugin):
                        plugin = attr()
                        plugin.set_main_window(self)
                        self._register_plugin(plugin)
                        print(f"[OK] 已注册插件: {plugin.name} ({plugin.plugin_id})")
            except Exception as e:
                print(f"[ERR] 导入插件模块 {name} 失败: {e}")

    def _register_plugin(self, plugin: BasePlugin):
        """注册插件：创建 workspace，不创建侧边栏按钮（延迟到首次打开）"""
        self._plugins.append(plugin)
        self._plugin_by_id[plugin.plugin_id] = plugin
        ws = plugin.get_workspace()
        self.stacked_widget.addWidget(ws)

    # ═══════════════════════  侧边栏动态排序  ═══════════════════════
    def _rebuild_plugin_nav(self):
        """按 _opened_plugins 顺序重建侧边栏插件按钮"""
        for btn in self._plugin_nav_buttons.values():
            self._nav_group.removeButton(btn)
            self._plugin_btn_container.removeWidget(btn)
            btn.deleteLater()
        self._plugin_nav_buttons.clear()

        has_opened = bool(self._opened_plugins)
        self._nav_plugin_section.setVisible(has_opened)

        if not has_opened:
            return

        for pid in self._opened_plugins:
            plugin = self._plugin_by_id.get(pid)
            if plugin is None:
                continue

            ws_index = self._plugins.index(plugin) + 1

            nav_btn = QPushButton("    " + plugin.icon + "  " + plugin.name)
            nav_btn.setObjectName("NavBtn")
            nav_btn.setCheckable(True)
            nav_btn.setCursor(Qt.PointingHandCursor)
            nav_btn.clicked.connect(
                lambda checked=None, idx=ws_index: self.switch_page(idx))
            self._nav_group.addButton(nav_btn)
            self._plugin_btn_container.addWidget(nav_btn)
            self._plugin_nav_buttons[pid] = nav_btn

            if ws_index == self._current_page:
                nav_btn.setChecked(True)

    # ═══════════════════════  首页  ═══════════════════════
    def _build_home_page(self):
        page = QWidget()
        page.setStyleSheet("background-color: " + C_BG + ";")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(60, 50, 60, 50)
        layout.setSpacing(0)

        # Hero
        hero = QWidget()
        hero.setStyleSheet(
            "QWidget#Hero {"
            " background: qlineargradient(x1:0, y1:0, x2:1, y2:1,"
            " stop:0 #2D2B55, stop:0.35 #1E1E3A, stop:1 #0F3460);"
            " border-radius: " + str(R_XL) + "px; }")
        hero.setObjectName("Hero")
        hero.setFixedHeight(190)
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(44, 38, 44, 38)

        hero_title = QLabel("你好，我是 Noova 助手")
        hero_title.setStyleSheet(
            "font-size: 32px; font-weight: 800; color: #FFFFFF;"
            " background: transparent; letter-spacing: 1px;")
        hero_sub = QLabel("AI 图像生成平台  ·  批量处理  ·  高效创作")
        hero_sub.setStyleSheet(
            "font-size: 15px; color: rgba(255,255,255,0.65);"
            " background: transparent; margin-top: 6px;")
        hero_layout.addWidget(hero_title)
        hero_layout.addWidget(hero_sub)
        hero_layout.addStretch()
        layout.addWidget(hero)
        layout.addSpacing(40)

        # 功能服务
        sec_label = QLabel("功能服务")
        sec_label.setStyleSheet(
            "font-size: 20px; font-weight: 700; color: " + C_TEXT + ";"
            " background: transparent;")
        layout.addWidget(sec_label)
        layout.addSpacing(20)

        # 插件卡片网格
        self._card_grid = QGridLayout()
        self._card_grid.setSpacing(16)
        self._home_cards = []

        for i, plugin in enumerate(self._plugins):
            card = plugin.get_card()
            ws_index = i + 1
            pid = plugin.plugin_id
            card.clicked.connect(
                lambda checked=None, idx=ws_index, p=pid:
                    self._on_card_clicked(idx, p))
            self._home_cards.append(card)

        self._relayout_cards()
        layout.addLayout(self._card_grid)
        layout.addStretch()

        scroll.setWidget(content)
        wrapped = QVBoxLayout(page)
        wrapped.setContentsMargins(0, 0, 0, 0)
        wrapped.addWidget(scroll)

        self.stacked_widget.insertWidget(0, page)

    def _on_card_clicked(self, ws_index: int, plugin_id: str):
        """首页卡片点击 → 记录到 _opened_plugins 并导航"""
        if plugin_id in self._opened_plugins:
            self._opened_plugins.remove(plugin_id)
        self._opened_plugins.insert(0, plugin_id)
        self._rebuild_plugin_nav()
        self.switch_page(ws_index)

    # ═══════════════════════  共享监控台  ═══════════════════════
    def _build_monitor_page(self):
        page = QWidget()
        page.setStyleSheet("background-color: " + C_BG + ";")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(60, 56, 60, 56)

        header = QHBoxLayout()
        title = QLabel("运行监控台")
        title.setStyleSheet(
            "font-size: 28px; font-weight: 700; color: " + C_TEXT + ";"
            " background: transparent;")

        self.btn_stop = QPushButton("   终止任务")
        self.btn_stop.setStyleSheet(
            "background-color: " + C_DANGER + "; color: white;"
            " border-radius: " + str(R_SM) + "px; padding: 10px 20px;"
            " border: none; font-size: 14px; font-weight: 500;")
        self.btn_stop.setCursor(Qt.PointingHandCursor)
        self.btn_stop.clicked.connect(self._on_stop_clicked)
        self.btn_stop.hide()

        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.btn_stop)
        layout.addLayout(header)
        layout.addSpacing(24)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("MonitorProgress")
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(10)
        layout.addWidget(self.progress_bar)
        layout.addSpacing(16)

        self.log_area = QTextEdit()
        self.log_area.setObjectName("MonitorLog")
        self.log_area.setReadOnly(True)
        layout.addWidget(self.log_area)

        self.stacked_widget.addWidget(page)

    # ═══════════════════════  页面导航  ═══════════════════════
    def switch_page(self, index: int):
        old_idx = self._current_page

        if 1 <= old_idx <= len(self._plugins):
            self._plugins[old_idx - 1].on_deactivate()

        mon_idx = self._monitor_index()
        self.nav_home.setChecked(index == 0)
        self.nav_monitor.setChecked(index == mon_idx)

        # 同步侧边栏插件按钮高亮
        for pid in self._opened_plugins:
            btn = self._plugin_nav_buttons.get(pid)
            plugin = self._plugin_by_id.get(pid)
            if btn and plugin:
                ws_idx = self._plugins.index(plugin) + 1
                btn.setChecked(index == ws_idx)

        self.stacked_widget.setCurrentIndex(index)
        self._current_page = index

        if 1 <= index <= len(self._plugins):
            self._plugins[index - 1].on_activate()

    def switch_to_monitor(self):
        self.switch_page(self._monitor_index())

    def _monitor_index(self) -> int:
        return self.stacked_widget.count() - 1

    # ═══════════════════════  监控台接口  ═══════════════════════
    def monitor_clear(self):
        self.log_area.clear()
        self.progress_bar.setValue(0)

    def monitor_log(self, text: str):
        self.log_area.append(text)
        scrollbar = self.log_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def monitor_progress(self, current: int, total: int):
        pct = int((current / total) * 100) if total > 0 else 0
        self.progress_bar.setValue(pct)

    def monitor_set_running(self, running: bool):
        self.btn_stop.setVisible(running)
        self.btn_stop.setDisabled(not running)
        self.nav_monitor.setVisible(running)
        if not running:
            self.btn_stop.setDisabled(False)

    # ═══════════════════════  停止信号  ═══════════════════════
    def _on_stop_clicked(self):
        self.stop_requested.emit()
        self.btn_stop.setDisabled(True)

    # ═══════════════════════  窗口事件  ═══════════════════════
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout_cards()

    def _relayout_cards(self):
        if not hasattr(self, '_home_cards') or not self._home_cards:
            return
        w = self.width()
        cols = 4 if w >= 1200 else (3 if w >= 900 else (2 if w >= 650 else 1))
        # 使用 removeItem 保留 widget，不销毁
        for i in reversed(range(self._card_grid.count())):
            item = self._card_grid.itemAt(i)
            if item:
                self._card_grid.removeItem(item)
        for i, card in enumerate(self._home_cards):
            self._card_grid.addWidget(card, i // cols, i % cols)

    def closeEvent(self, event):
        self.stop_requested.emit()
        for plugin in self._plugins:
            if (hasattr(plugin, '_worker')
                    and plugin._worker
                    and plugin._worker.isRunning()):
                plugin._worker.stop()
                plugin._worker.wait(3000)
        super().closeEvent(event)

    @property
    def plugins(self):
        return self._plugins


# ═══════════════════════  入口  ═══════════════════════
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ModernAppShell()
    window.show()
    sys.exit(app.exec())
