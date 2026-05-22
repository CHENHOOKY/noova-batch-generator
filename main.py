"""Noova AI 批量出图助手 —— 主程序入口

架构说明:
  - plugin_base.py  定义插件协议 (BasePlugin)
  - plugins/        每个 .py 文件是一个独立的功能插件
  - main.py         主程序壳：侧边栏、首页卡片区、插件路由、共享监控台

新增功能：在 plugins/ 下新建文件，写一个继承 BasePlugin 的类即可自动注册。
删除插件：直接删除对应 .py 文件，不影响任何其他功能。
"""

import os
import sys
import importlib
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QStackedWidget, QScrollArea, QGridLayout,
    QProgressBar, QTextEdit,
)
from PySide6.QtCore import Qt

from plugin_base import BasePlugin


class ModernAppShell(QMainWindow):
    """主程序壳 —— 管理整体布局、插件路由、共享监控台"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Noova AI 批量出图助手")
        self.resize(1000, 700)
        self.setMinimumSize(900, 600)

        self._plugins = []
        self._nav_plugin_buttons = []       # 侧边栏插件导航按钮
        self._nav_plugin_section = None     # 插件导航区域容器
        self._stop_handler = None
        self.btn_start = None  # 由插件设置，用于恢复按钮状态

        self._init_styles()
        self._build_shell()
        self._load_plugins()
        self._build_home_page()
        self._build_monitor_page()

    # ═══════════════════════════════════════
    #  样式
    # ═══════════════════════════════════════
    def _init_styles(self):
        self.setStyleSheet("""
            QMainWindow { background-color: #F9FAFB; }
            QWidget#Sidebar { background-color: #FFFFFF; border-right: 1px solid #EBEBEB; }
            QPushButton.NavBtn {
                text-align: left; padding: 12px 20px; border: none;
                border-radius: 8px; font-size: 14px; color: #555555; font-weight: 500;
            }
            QPushButton.NavBtn:hover { background-color: #F5F5F5; }
            QPushButton.NavBtn:checked { background-color: #EEEEFF; font-weight: bold; color: #6366F1; }

            QTextEdit { border: 1px solid #EBEBEB; border-radius: 12px; padding: 10px;
                background-color: #FAFAFA; font-size: 13px; }
            QProgressBar { border: none; background-color: #F0F0F0; border-radius: 4px;
                height: 8px; text-align: center; color: transparent; }
            QProgressBar::chunk { background-color: #6366F1; border-radius: 4px; }

            QLineEdit, QComboBox {
                padding: 10px; border: 1px solid #E5E7EB; border-radius: 8px;
                font-size: 14px; background-color: #FFFFFF;
            }
            QLineEdit:focus, QComboBox:focus { border: 1px solid #6366F1; }
            QSpinBox {
                padding: 10px; border: 1px solid #E5E7EB; border-radius: 8px;
                font-size: 14px; background-color: #FFFFFF;
            }
        """)

    # ═══════════════════════════════════════
    #  主布局骨架
    # ═══════════════════════════════════════
    def _build_shell(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- 侧边栏 ---
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(220)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(15, 30, 15, 30)
        side_layout.setSpacing(10)

        logo = QLabel("✨ Noova AI")
        logo.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #1A1A1A; "
            "padding-left: 10px; padding-bottom: 20px;")
        side_layout.addWidget(logo)

        self.nav_home = QPushButton("🏠 Noova应用")
        self.nav_home.setCheckable(True)
        self.nav_home.setChecked(True)
        self.nav_home.setProperty("class", "NavBtn")
        self.nav_home.clicked.connect(lambda: self.switch_page(0))
        side_layout.addWidget(self.nav_home)

        # --- 插件导航区域（进入工作区后显示） ---
        self._nav_plugin_section = QWidget()
        plugin_nav_layout = QVBoxLayout(self._nav_plugin_section)
        plugin_nav_layout.setContentsMargins(0, 4, 0, 4)
        plugin_nav_layout.setSpacing(2)

        sep = QLabel("  功能插件")
        sep.setStyleSheet(
            "color: #BBB; font-size: 11px; font-weight: 500; "
            "padding: 4px 20px 2px 20px; background: transparent;")
        plugin_nav_layout.addWidget(sep)

        self._plugin_btn_container = QVBoxLayout()
        self._plugin_btn_container.setSpacing(2)
        plugin_nav_layout.addLayout(self._plugin_btn_container)
        side_layout.addWidget(self._nav_plugin_section)

        self.nav_monitor = QPushButton("🚀 运行监控台")
        self.nav_monitor.setCheckable(True)
        self.nav_monitor.setProperty("class", "NavBtn")
        self.nav_monitor.setVisible(False)
        self.nav_monitor.clicked.connect(lambda: self.switch_page(self._monitor_index()))
        side_layout.addWidget(self.nav_monitor)

        side_layout.addStretch()

        ver = QLabel("v1.0.0 Desktop")
        ver.setStyleSheet("color: #AAAAAA; font-size: 12px; padding-left: 10px;")
        side_layout.addWidget(ver)

        main_layout.addWidget(sidebar)

        # --- 页面容器 ---
        self.stacked_widget = QStackedWidget()
        main_layout.addWidget(self.stacked_widget, 1)

    # ═══════════════════════════════════════
    #  插件发现与注册
    # ═══════════════════════════════════════
    def _load_plugins(self):
        """自动扫描 plugins/ 目录，发现所有 BasePlugin 子类并注册"""
        plugins_dir = Path(__file__).parent / "plugins"
        if not plugins_dir.exists():
            return

        # 确保 plugins 包已导入
        import plugins  # noqa: F401

        for f in sorted(plugins_dir.glob("*.py")):
            if f.name.startswith("_"):
                continue
            module_name = f"plugins.{f.stem}"
            try:
                module = importlib.import_module(module_name)
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (isinstance(attr, type)
                            and issubclass(attr, BasePlugin)
                            and attr is not BasePlugin):
                        plugin = attr()
                        plugin.set_main_window(self)
                        self._register_plugin(plugin)
                        print(f"[OK] 已加载插件: {plugin.name} ({plugin.plugin_id})")
            except Exception as e:
                print(f"[ERR] 加载插件 {module_name} 失败: {e}")

    def _register_plugin(self, plugin: BasePlugin):
        """将插件注册到主程序"""
        self._plugins.append(plugin)
        # 工作区页面加入 stacked_widget
        ws = plugin.get_workspace()
        self.stacked_widget.addWidget(ws)
        # 工作区索引 = 插件顺序 + 1（首页在 0，在 _build_home_page 中插入）
        ws_index = len(self._plugins)

        # 创建侧边栏导航按钮
        nav_btn = QPushButton(f"  {plugin.icon}  {plugin.name}")
        nav_btn.setCheckable(True)
        nav_btn.setProperty("class", "NavBtn")
        nav_btn.clicked.connect(
            lambda checked=None, idx=ws_index: self.switch_page(idx))
        self._plugin_btn_container.addWidget(nav_btn)
        self._nav_plugin_buttons.append(nav_btn)

    # ═══════════════════════════════════════
    #  首页
    # ═══════════════════════════════════════
    def _build_home_page(self):
        page = QWidget()
        page.setStyleSheet("background-color: #F9FAFB;")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(60, 50, 60, 50)

        # Hero
        hero = QWidget()
        hero.setStyleSheet("""
            QWidget#Hero {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #1A1A2E, stop:0.5 #16213E, stop:1 #0F3460);
                border-radius: 20px;
            }
        """)
        hero.setObjectName("Hero")
        hero.setFixedHeight(180)
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(40, 35, 40, 35)

        hero_title = QLabel("你好，我是 Noova 助手")
        hero_title.setStyleSheet(
            "font-size: 32px; font-weight: bold; color: #FFFFFF; background: transparent;")
        hero_sub = QLabel("AI 图像生成平台 · 批量处理 · 高效创作")
        hero_sub.setStyleSheet(
            "font-size: 15px; color: rgba(255,255,255,0.7); background: transparent; "
            "margin-top: 4px;")
        hero_layout.addWidget(hero_title)
        hero_layout.addWidget(hero_sub)
        hero_layout.addStretch()
        layout.addWidget(hero)
        layout.addSpacing(40)

        # 功能服务标题
        sec_label = QLabel("功能服务")
        sec_label.setStyleSheet("font-size: 20px; font-weight: bold; color: #1A1A1A;")
        layout.addWidget(sec_label)
        layout.addSpacing(20)

        # 插件卡片网格
        card_grid = QGridLayout()
        card_grid.setSpacing(20)

        for i, plugin in enumerate(self._plugins):
            card = plugin.get_card()
            # 工作区索引 = 插件在列表中的位置 + 1（0 是首页）
            ws_index = i + 1
            card.clicked.connect(
                lambda checked=None, idx=ws_index: self.switch_page(idx))
            card_grid.addWidget(card, i // 3, i % 3)

        layout.addLayout(card_grid)
        layout.addStretch()

        scroll.setWidget(content)
        wrapped = QVBoxLayout(page)
        wrapped.setContentsMargins(0, 0, 0, 0)
        wrapped.addWidget(scroll)

        self.stacked_widget.insertWidget(0, page)

    # ═══════════════════════════════════════
    #  共享监控台
    # ═══════════════════════════════════════
    def _build_monitor_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(60, 60, 60, 60)

        header = QHBoxLayout()
        title = QLabel("运行监控台")
        title.setStyleSheet("font-size: 24px; font-weight: bold;")

        self.btn_stop = QPushButton("⏹ 终止任务")
        self.btn_stop.setStyleSheet(
            "background-color: #FF4D4F; color: white; border-radius: 8px; "
            "padding: 8px 16px; border: none;")
        self.btn_stop.setCursor(Qt.PointingHandCursor)
        self.btn_stop.clicked.connect(self._on_stop_clicked)
        self.btn_stop.hide()

        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.btn_stop)
        layout.addLayout(header)
        layout.addSpacing(20)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        layout.addWidget(self.log_area)

        self.stacked_widget.addWidget(page)

    # ═══════════════════════════════════════
    #  页面导航
    # ═══════════════════════════════════════
    def switch_page(self, index: int):
        """切换到指定页面（0=首页, 1..N=插件工作区, 最后=监控台）"""
        mon_idx = self._monitor_index()
        self.nav_home.setChecked(index == 0)
        self.nav_monitor.setChecked(index == mon_idx)

        # 高亮当前插件按钮
        for i, btn in enumerate(self._nav_plugin_buttons):
            btn.setChecked(index == i + 1)

        self.stacked_widget.setCurrentIndex(index)

    def switch_to_monitor(self):
        """切换到监控台页面"""
        self.nav_monitor.setVisible(True)
        self.switch_page(self._monitor_index())

    def _monitor_index(self) -> int:
        return self.stacked_widget.count() - 1

    # ═══════════════════════════════════════
    #  监控台接口（供插件调用）
    # ═══════════════════════════════════════
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
        """设置监控台运行状态：显示/隐藏停止按钮"""
        self.btn_stop.setVisible(running)
        self.btn_stop.setDisabled(not running)
        if running:
            self.nav_monitor.setVisible(True)
        if not running:
            self.btn_stop.setDisabled(False)

    # ═══════════════════════════════════════
    #  停止回调（由插件设置）
    # ═══════════════════════════════════════
    def set_stop_handler(self, handler):
        """插件设置停止任务的回调函数"""
        self._stop_handler = handler

    def _on_stop_clicked(self):
        if self._stop_handler:
            self._stop_handler()
            self.btn_stop.setDisabled(True)

    # ═══════════════════════════════════════
    #  属性
    # ═══════════════════════════════════════
    @property
    def plugins(self):
        return self._plugins


# ═══════════════════════════════════════════
#  入口
# ═══════════════════════════════════════════
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ModernAppShell()
    window.show()
    sys.exit(app.exec())
