"""分镜脚本生成器 —— Seedance2Plugin（主插件类）"""

import json
import os
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QScrollArea,
    QLabel, QPushButton, QTextEdit, QLineEdit, QSpinBox,
    QTabWidget, QProgressBar, QFileDialog, QMessageBox, QSplitter,
    QGridLayout, QSizePolicy, QCheckBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap

from plugin_base import BasePlugin
from plugins._noova_api import NoovaAPI, MODEL_CONFIG
from plugins._design import COMBO_STYLE, INPUT_STYLE, NoScrollComboBox as QComboBox

from plugins.storyboard_generator.config import (
    DS_BASE_URL, DS_MODELS,
    STYLE_PRESETS, DEFAULT_EPISODE_COUNT, DEFAULT_DURATION,
    DEFAULT_IMAGE_MODEL, DEFAULT_IMAGE_SIZE, DEFAULT_ASPECT_RATIO,
    IMAGE_CONCURRENCY, create_project_dir, sanitize_filename,
)
from plugins.storyboard_generator.worker import StoryboardWorker
from plugins.storyboard_generator.widgets import (
    AssetGridItem, EpisodeNavBar, StoryboardEpisodeView, PromptReviewDialog,
    RegenerateDialog,
)
from plugins.storyboard_generator.asset_manager import (
    ImageTask, build_asset_queue,
)


class Seedance2Plugin(BasePlugin):
    plugin_id = "storyboard_generator"
    name = "分镜脚本生成器"
    version = "2.0.0"
    description = (
        "基于 Seedance2 四幕式结构，将故事转化为完整的分镜脚本\n"
        "剧本 → 素材规划 → AI出图 → 逐秒分镜提示词"
    )
    icon = "🎬"
    color = "#8B5CF6"

    _STYLE_SECTION_CSS = (
        "QFrame#section { background: #FFFFFF; border: 1px solid #E5E7EB;"
        " border-radius: 12px; padding: 16px; }"
    )
    _LABEL_CSS = "font-size: 13px; font-weight: 600; color: #6B7280; background: transparent;"

    def __init__(self):
        super().__init__()
        self._worker: StoryboardWorker | None = None
        self._output_data: dict | None = None
        self._script_data: dict | None = None
        self._asset_plan: dict | None = None
        self._storyboards: dict[int, dict] = {}
        self._project_dir = ""
        self._asset_grid_items: dict[str, AssetGridItem] = {}

    # ── Workspace ────────────────────────────

    def create_workspace(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet(
            "background: #F8F9FC;"
            "font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif;")

        splitter = QSplitter(Qt.Horizontal)

        # ── Left Panel ──
        splitter.addWidget(self._build_left_panel())

        # ── Right Panel ──
        splitter.addWidget(self._build_right_panel())

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([380, 700])

        root = QVBoxLayout(w)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(splitter)
        return w

    def _build_left_panel(self) -> QWidget:
        left = QWidget()
        left.setFixedWidth(380)
        left.setStyleSheet("background: #FFFFFF; border-right: 1px solid #E5E7EB;")

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: #FFFFFF; }")

        inner = QWidget()
        inner.setStyleSheet("background: #FFFFFF;")
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Title
        title = QLabel("🎬 分镜脚本生成器")
        title.setStyleSheet(
            "font-size: 18px; font-weight: 700; color: #1E1E2E; background: transparent;")
        layout.addWidget(title)

        sub = QLabel(
            "输入故事或主题，AI 自动生成四幕剧本 + 素材规划 "
            "+ 角色/场景/道具出图 + Seedance 2.0 逐秒分镜提示词")
        sub.setWordWrap(True)
        sub.setStyleSheet("font-size: 12px; color: #9CA3AF; background: transparent;")
        layout.addWidget(sub)

        # Story input
        story_lbl = QLabel("故事/主题")
        story_lbl.setStyleSheet(self._LABEL_CSS)
        layout.addWidget(story_lbl)

        self._story_input = QTextEdit()
        self._story_input.setPlaceholderText(
            "输入故事内容或主题描述...\n\n"
            "例如：\n"
            "- 林冲风雪山神庙，被逼上梁山\n"
            "- 一个女孩在赛博朋克城市中寻找失散的弟弟\n"
            "- 两位武林高手在竹林间的宿命对决")
        self._story_input.setMinimumHeight(150)
        self._story_input.setMaximumHeight(200)
        self._story_input.setAcceptRichText(False)
        self._story_input.setStyleSheet(
            "QTextEdit { border: 1px solid #E5E7EB; border-radius: 10px;"
            " padding: 10px 14px; font-size: 13px; color: #1E1E2E;"
            " background: #FAFAFA; }"
            "QTextEdit:focus { border-color: #6366F1; background: #FFFFFF; }")
        layout.addWidget(self._story_input)

        # Style
        style_lbl = QLabel("视觉风格")
        style_lbl.setStyleSheet(self._LABEL_CSS)
        layout.addWidget(style_lbl)
        self._combo_style = QComboBox()
        self._combo_style.addItems(list(STYLE_PRESETS.keys()))
        self._combo_style.setStyleSheet(COMBO_STYLE)
        layout.addWidget(self._combo_style)

        # Episode count + Duration
        row = QHBoxLayout()
        row.setSpacing(12)
        ec = QVBoxLayout(); ec.setSpacing(4)
        ec.addWidget(self._make_small_label("集数"))
        self._spin_episodes = QSpinBox()
        self._spin_episodes.setRange(1, 12)
        self._spin_episodes.setValue(DEFAULT_EPISODE_COUNT)
        self._spin_episodes.setStyleSheet(INPUT_STYLE)
        ec.addWidget(self._spin_episodes)
        row.addLayout(ec)
        dc = QVBoxLayout(); dc.setSpacing(4)
        dc.addWidget(self._make_small_label("每集时长(秒)"))
        self._combo_duration = QComboBox()
        self._combo_duration.addItems(["8", "10", "15"])
        self._combo_duration.setCurrentText(str(DEFAULT_DURATION))
        self._combo_duration.setStyleSheet(COMBO_STYLE)
        dc.addWidget(self._combo_duration)
        row.addLayout(dc)
        layout.addLayout(row)

        # API config (keys from global settings)
        api_sec = self._build_section_frame("API 配置")
        api_lo = QVBoxLayout(api_sec)
        api_lo.setContentsMargins(12, 12, 12, 12)
        api_lo.setSpacing(8)
        api_lo.addWidget(self._make_section_title("API 配置"))

        self._api_status_label = QLabel()
        self._update_api_status()
        api_lo.addWidget(self._api_status_label)

        api_lo.addWidget(QLabel("文本模型"))
        self._combo_ds_model = QComboBox()
        self._combo_ds_model.addItems(DS_MODELS)
        self._combo_ds_model.setStyleSheet(COMBO_STYLE)
        api_lo.addWidget(self._combo_ds_model)

        api_lo.addWidget(QLabel("出图模型"))
        self._combo_img_model = QComboBox()
        self._combo_img_model.addItems(list(MODEL_CONFIG.keys()))
        idx = self._combo_img_model.findText(DEFAULT_IMAGE_MODEL)
        if idx >= 0:
            self._combo_img_model.setCurrentIndex(idx)
        self._combo_img_model.setStyleSheet(COMBO_STYLE)
        self._combo_img_model.currentTextChanged.connect(self._on_img_model_changed)
        api_lo.addWidget(self._combo_img_model)

        api_lo.addWidget(QLabel("画质"))
        self._combo_img_size = QComboBox()
        self._combo_img_size.setStyleSheet(COMBO_STYLE)
        api_lo.addWidget(self._combo_img_size)

        api_lo.addWidget(QLabel("比例"))
        self._combo_img_ratio = QComboBox()
        self._combo_img_ratio.setStyleSheet(COMBO_STYLE)
        api_lo.addWidget(self._combo_img_ratio)
        self._on_img_model_changed(self._combo_img_model.currentText())
        layout.addWidget(api_sec)

        # Generate checkbox
        self._chk_images = self._make_checkbox("生成素材图片（Phase 3）", True)
        layout.addWidget(self._chk_images)

        # Buttons
        self._btn_gen = QPushButton("🚀 生成分镜脚本")
        self._btn_gen.setStyleSheet(
            "QPushButton { background: #6366F1; border: none; border-radius: 10px;"
            " padding: 14px 28px; font-size: 15px; color: white; font-weight: 700; }"
            "QPushButton:hover { background: #4F46E5; }"
            "QPushButton:disabled { background: #A5B4FC; }")
        self._btn_gen.setCursor(Qt.PointingHandCursor)
        self._btn_gen.clicked.connect(self._start)
        layout.addWidget(self._btn_gen)

        self._btn_cancel = QPushButton("取消")
        self._btn_cancel.setStyleSheet(
            "QPushButton { background: #F3F4F6; border: 1px solid #E5E7EB;"
            " border-radius: 10px; padding: 10px 24px; font-size: 13px;"
            " color: #6B7280; font-weight: 600; }"
            "QPushButton:hover { background: #E5E7EB; color: #1E1E2E; }")
        self._btn_cancel.setCursor(Qt.PointingHandCursor)
        self._btn_cancel.clicked.connect(self._cancel)
        self._btn_cancel.setVisible(False)
        layout.addWidget(self._btn_cancel)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setVisible(False)
        self._progress_bar.setStyleSheet(
            "QProgressBar { border: 1px solid #E5E7EB; border-radius: 8px;"
            " background: #F3F4F6; height: 10px; }"
            "QProgressBar::chunk { background: #6366F1; border-radius: 8px; }")
        layout.addWidget(self._progress_bar)

        self._phase_lbl = QLabel("")
        self._phase_lbl.setStyleSheet(
            "font-size: 12px; color: #6366F1; font-weight: 600; background: transparent;")
        layout.addWidget(self._phase_lbl)

        layout.addStretch()
        scroll.setWidget(inner)
        outer = QVBoxLayout(left)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        return left

    def _build_right_panel(self) -> QWidget:
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)

        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(
            "QTabWidget::pane { border: none; background: #FFFFFF; }"
            "QTabBar::tab { background: #F3F4F6; border: none; padding: 10px 24px;"
            " font-size: 13px; color: #6B7280; font-weight: 600; margin-right: 2px; }"
            "QTabBar::tab:selected { background: #FFFFFF; color: #6366F1;"
            " border-bottom: 2px solid #6366F1; }")

        # Tab 1: Script
        self._tab_script = QTextEdit()
        self._tab_script.setReadOnly(True)
        self._tab_script.setPlaceholderText("生成的四幕剧本将显示在这里...")
        self._tab_script.setStyleSheet(
            "QTextEdit { border: none; padding: 20px; font-size: 14px;"
            " background: #FFFFFF; color: #1E1E2E;"
            " font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif; }")
        self._tabs.addTab(self._tab_script, "📜 剧本")

        # Tab 2: Assets
        self._tab_assets = QTextEdit()
        self._tab_assets.setReadOnly(True)
        self._tab_assets.setPlaceholderText("角色(C#)、场景(S#)、道具(P#) 素材清单将显示在这里...")
        self._tab_assets.setStyleSheet(self._tab_script.styleSheet())
        self._tabs.addTab(self._tab_assets, "📋 素材清单")

        # Tab 3: Image Grid
        img_tab = QWidget()
        img_layout = QVBoxLayout(img_tab)
        img_layout.setContentsMargins(0, 0, 0, 0)
        img_layout.setSpacing(0)

        # Filter row
        filter_row = QHBoxLayout()
        filter_row.setContentsMargins(16, 12, 16, 8)
        filter_row.setSpacing(8)
        filter_row.addWidget(QLabel("筛选:"))
        self._filter_all = self._make_filter_btn("全部", True)
        self._filter_char = self._make_filter_btn("角色", False)
        self._filter_scene = self._make_filter_btn("场景", False)
        self._filter_prop = self._make_filter_btn("道具", False)

        def make_filter_cb(btn, others, atype):
            def cb():
                btn.setStyleSheet(self._active_filter_style())
                for o in others:
                    o.setStyleSheet(self._inactive_filter_style())
                self._apply_asset_filter(atype)
            return cb

        self._filter_all.clicked.connect(
            make_filter_cb(self._filter_all,
                           [self._filter_char, self._filter_scene, self._filter_prop], None))
        self._filter_char.clicked.connect(
            make_filter_cb(self._filter_char,
                           [self._filter_all, self._filter_scene, self._filter_prop], "character"))
        self._filter_scene.clicked.connect(
            make_filter_cb(self._filter_scene,
                           [self._filter_all, self._filter_char, self._filter_prop], "scene"))
        self._filter_prop.clicked.connect(
            make_filter_cb(self._filter_prop,
                           [self._filter_all, self._filter_char, self._filter_scene], "prop"))

        filter_row.addWidget(self._filter_all)
        filter_row.addWidget(self._filter_char)
        filter_row.addWidget(self._filter_scene)
        filter_row.addWidget(self._filter_prop)
        filter_row.addStretch()

        self._img_progress_lbl = QLabel("")
        self._img_progress_lbl.setStyleSheet(
            "font-size: 12px; color: #6366F1; font-weight: 600; background: transparent;")
        filter_row.addWidget(self._img_progress_lbl)
        img_layout.addLayout(filter_row)

        # Grid scroll
        self._img_scroll = QScrollArea()
        self._img_scroll.setWidgetResizable(True)
        self._img_scroll.setStyleSheet(
            "QScrollArea { border: none; background: #FFFFFF; }")
        self._img_grid_w = QWidget()
        self._img_grid_w.setStyleSheet("background: #FFFFFF;")
        self._img_grid_layout = QGridLayout(self._img_grid_w)
        self._img_grid_layout.setContentsMargins(16, 8, 16, 16)
        self._img_grid_layout.setSpacing(12)
        self._img_scroll.setWidget(self._img_grid_w)
        img_layout.addWidget(self._img_scroll)

        self._tabs.addTab(img_tab, "🖼 素材图")

        # Tab 4: Storyboard
        sb_tab = QWidget()
        sb_layout = QVBoxLayout(sb_tab)
        sb_layout.setContentsMargins(0, 0, 0, 0)
        sb_layout.setSpacing(0)

        self._ep_nav = EpisodeNavBar()
        self._ep_nav.episode_selected.connect(self._on_episode_selected)
        sb_layout.addWidget(self._ep_nav)

        self._sb_view = StoryboardEpisodeView()
        sb_layout.addWidget(self._sb_view, 1)

        self._tabs.addTab(sb_tab, "🎬 分镜脚本")

        rl.addWidget(self._tabs, 1)

        # Bottom bar
        bottom = QWidget()
        bottom.setStyleSheet("background: #FFFFFF; border-top: 1px solid #E5E7EB;")
        bottom.setFixedHeight(52)
        bl = QHBoxLayout(bottom)
        bl.setContentsMargins(20, 10, 20, 10)
        bl.setSpacing(12)

        self._status_lbl = QLabel("就绪")
        self._status_lbl.setStyleSheet(
            "font-size: 12px; color: #9CA3AF; background: transparent;")
        bl.addWidget(self._status_lbl, 1)

        self._btn_export = QPushButton("📥 导出全部")
        self._btn_export.setStyleSheet(
            "QPushButton { background: #10B981; border: none; border-radius: 8px;"
            " padding: 8px 18px; font-size: 13px; color: white; font-weight: 600; }"
            "QPushButton:hover { background: #059669; }"
            "QPushButton:disabled { background: #A7F3D0; }")
        self._btn_export.setCursor(Qt.PointingHandCursor)
        self._btn_export.clicked.connect(self._export_all)
        self._btn_export.setEnabled(False)
        bl.addWidget(self._btn_export)

        rl.addWidget(bottom)
        return right

    # ── Mini widget builders ──

    def _make_small_label(self, text: str) -> QLabel:
        l = QLabel(text)
        l.setStyleSheet(self._LABEL_CSS)
        return l

    def _make_checkbox(self, text: str, checked: bool):
        cb = QCheckBox(text)
        cb.setChecked(checked)
        cb.setStyleSheet(
            "QCheckBox { font-size: 13px; color: #374151; background: transparent; }")
        return cb

    def _make_filter_btn(self, text: str, active: bool) -> QPushButton:
        btn = QPushButton(text)
        btn.setCheckable(True)
        btn.setChecked(active)
        btn.setStyleSheet(self._active_filter_style() if active else self._inactive_filter_style())
        btn.setCursor(Qt.PointingHandCursor)
        return btn

    def _active_filter_style(self) -> str:
        return (
            "QPushButton { background: #6366F1; border: none; border-radius: 6px;"
            " padding: 6px 14px; font-size: 12px; color: white; font-weight: 600; }")

    def _inactive_filter_style(self) -> str:
        return (
            "QPushButton { background: #F3F4F6; border: 1px solid #E5E7EB;"
            " border-radius: 6px; padding: 6px 14px; font-size: 12px;"
            " color: #6B7280; font-weight: 600; }"
            "QPushButton:hover { background: #E5E7EB; }")

    def _build_section_frame(self, title: str) -> QFrame:
        sec = QFrame()
        sec.setObjectName("section")
        sec.setStyleSheet(self._STYLE_SECTION_CSS)
        return sec

    def _make_section_title(self, text: str) -> QLabel:
        tl = QLabel(text)
        tl.setStyleSheet(
            "font-size: 13px; font-weight: 700; color: #1E1E2E; background: transparent;")
        return tl

    # ── API status ──

    def _update_api_status(self):
        if self.main_window:
            txt_ok = self.main_window.settings_manager.has_text_key()
            vis_ok = self.main_window.settings_manager.has_visual_key()
            parts = []
            if txt_ok:
                parts.append("✅ 文本 Key 已配置")
            else:
                parts.append("⚠️ 文本 Key 未配置")
            if vis_ok:
                parts.append("✅ 视觉 Key 已配置")
            else:
                parts.append("⚠️ 视觉 Key 未配置")
            status = "  |  ".join(parts)
            if txt_ok and vis_ok:
                color = "#10B981"
            else:
                color = "#F59E0B"
                status += "\n请点击侧边栏 ⚙️ 设置进行配置"
            self._api_status_label.setText(status)
            self._api_status_label.setStyleSheet(
                f"font-size: 12px; color: {color}; background: transparent; padding: 2px 0;")

    def on_activate(self):
        self._update_api_status()

    # ── Image model change ──

    def _on_img_model_changed(self, model_name: str):
        config = MODEL_CONFIG.get(model_name)
        if not config:
            return
        self._combo_img_size.clear()
        self._combo_img_size.addItems(config.get("sizes", ["1K"]))
        default_size = DEFAULT_IMAGE_SIZE if DEFAULT_IMAGE_SIZE in config.get("sizes", []) else config["sizes"][0]
        idx = self._combo_img_size.findText(default_size)
        if idx >= 0:
            self._combo_img_size.setCurrentIndex(idx)

        self._combo_img_ratio.clear()
        self._combo_img_ratio.addItems(config.get("ratios", ["16:9"]))
        default_ratio = DEFAULT_ASPECT_RATIO if DEFAULT_ASPECT_RATIO in config.get("ratios", []) else config["ratios"][0]
        idx = self._combo_img_ratio.findText(default_ratio)
        if idx >= 0:
            self._combo_img_ratio.setCurrentIndex(idx)

    # ── Asset filter ──

    def _apply_asset_filter(self, asset_type: str | None):
        for item in self._asset_grid_items.values():
            if asset_type is None:
                item.setVisible(True)
            else:
                # Determine type from asset_id prefix
                prefix = item._asset_id[0] if item._asset_id else ""
                type_map = {"C": "character", "S": "scene", "P": "prop"}
                item.setVisible(type_map.get(prefix, "") == asset_type)

    # ── Generate flow ──

    def _start(self):
        story = self._story_input.toPlainText().strip()
        if not story:
            QMessageBox.warning(self.main_window, "提示", "请输入故事或主题内容")
            return

        # Gather API configs (keys from global settings)
        ds_key = self.main_window.settings_manager.get_text_key()
        ds_model = self._combo_ds_model.currentText()
        noova_key = self.main_window.settings_manager.get_visual_key()

        if not ds_key:
            QMessageBox.warning(self.main_window, "提示",
                "未配置文本模型 API Key！请点击侧边栏 ⚙️ 设置进行配置")
            return

        style_label = self._combo_style.currentText()
        style_desc = STYLE_PRESETS.get(style_label, style_label)
        ep_count = self._spin_episodes.value()
        duration = int(self._combo_duration.currentText())
        run_images = self._chk_images.isChecked() and bool(noova_key)

        if run_images and not noova_key:
            QMessageBox.warning(self.main_window, "提示",
                "要生成素材图，需要视觉模型 API Key，请点击侧边栏 ⚙️ 设置进行配置，或取消勾选\"生成素材图片\"")
            return

        # Prepare project dir
        self._project_dir = create_project_dir()
        self._output_data = None
        self._script_data = None
        self._asset_plan = None
        self._storyboards = {}

        # Clear tabs
        self._tab_script.clear()
        self._tab_assets.clear()
        self._tabs.setCurrentIndex(0)

        # Clear image grid
        for item in self._asset_grid_items.values():
            item.deleteLater()
        self._asset_grid_items.clear()
        # Also clear layout
        while self._img_grid_layout.count():
            child = self._img_grid_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self._img_progress_lbl.setText("")

        # Clear storyboard
        self._ep_nav.set_episodes(0)

        # UI state
        self._btn_gen.setVisible(False)
        self._btn_cancel.setVisible(True)
        self._progress_bar.setVisible(True)
        self._btn_export.setEnabled(False)

        # Create Noova API
        noova = None
        if run_images:
            noova = NoovaAPI(noova_key)
            if os.environ.get("NOOVA_BASE_URL"):
                noova.BASE_URL = os.environ["NOOVA_BASE_URL"].rstrip("/")
        self._noova_api = noova  # store for regenerate dialog

        img_model = self._combo_img_model.currentText()
        img_size = self._combo_img_size.currentText()
        img_ratio = self._combo_img_ratio.currentText()
        self._img_model = img_model
        self._img_size = img_size
        self._img_ratio = img_ratio

        self._worker = StoryboardWorker(
            api_key=ds_key, base_url=self.main_window.settings_manager.get_text_base_url(), ds_model=ds_model,
            noova_api=noova, image_model=img_model,
            image_size=img_size, image_ratio=img_ratio,
            story_text=story, style_label=style_label, style_desc=style_desc,
            episode_count=ep_count, duration=duration,
            project_dir=self._project_dir, run_images=run_images,
        )
        self._worker.log.connect(self._on_log)
        self._worker.progress.connect(self._on_progress)
        self._worker.script_ready.connect(self._on_script)
        self._worker.asset_plan_ready.connect(self._on_asset_plan)
        self._worker.asset_generated.connect(self._on_asset_done)
        self._worker.asset_progress.connect(self._on_asset_progress)
        self._worker.storyboard_episode_ready.connect(self._on_sb_episode)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def stop(self):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(3000)

    def _cancel(self):
        self.stop()
        self._reset_ui()

    def _reset_ui(self):
        self._btn_gen.setVisible(True)
        self._btn_cancel.setVisible(False)
        self._progress_bar.setVisible(False)
        self._phase_lbl.setText("")

    def _on_log(self, msg: str):
        self._status_lbl.setText(msg)

    def _on_progress(self, pct: int, label: str):
        self._progress_bar.setValue(pct)
        self._phase_lbl.setText(label)

    # ── Phase 1 ──

    def _on_script(self, data: dict):
        self._script_data = data
        self._tab_script.setMarkdown(self._fmt_script_display(data))
        self._tabs.setCurrentIndex(0)
        self._status_lbl.setText("✅ 剧本生成完成")

    # ── Phase 2 ──

    def _on_asset_plan(self, data: dict):
        self._asset_plan = data
        self._tab_assets.setMarkdown(self._fmt_asset_display(data))
        self._tabs.setCurrentIndex(1)
        self._status_lbl.setText("✅ 素材规划完成")

        # Build grid items for Phase 3 preview
        for ca in data.get("character_assets", []):
            cid = ca.get("character_id", "C??")
            name = ca.get("name", "")
            view_label = ca.get("view_label", "")
            prompt = ca.get("prompt", "")
            asset_key = f"{cid}_{view_label}"
            display_name = f"{name}·{view_label}" if view_label else name
            item = AssetGridItem(asset_key, display_name, "character", view_label, prompt)
            item.clicked.connect(self._on_asset_clicked)
            item.replace_requested.connect(self._on_asset_replace)
            self._asset_grid_items[asset_key] = item
            self._img_grid_layout.addWidget(item,
                len(self._asset_grid_items) // 4,
                len(self._asset_grid_items) % 4)
        for sa in data.get("scene_assets", []):
            sid = sa.get("scene_id", "S??")
            name = sa.get("name", "")
            prompt = sa.get("prompt", "")
            item = AssetGridItem(sid, name, "scene", "", prompt)
            item.clicked.connect(self._on_asset_clicked)
            self._asset_grid_items[sid] = item
            self._img_grid_layout.addWidget(item,
                len(self._asset_grid_items) // 4,
                len(self._asset_grid_items) % 4)
        for pa in data.get("prop_assets", []):
            pid = pa.get("prop_id", "P??")
            name = pa.get("name", "")
            prompt = pa.get("prompt", "")
            item = AssetGridItem(pid, name, "prop", "", prompt)
            item.clicked.connect(self._on_asset_clicked)
            self._asset_grid_items[pid] = item
            self._img_grid_layout.addWidget(item,
                len(self._asset_grid_items) // 4,
                len(self._asset_grid_items) % 4)

    # ── Phase 3 ──

    def _on_asset_progress(self, done: int, total: int):
        self._img_progress_lbl.setText(f"生成中: {done}/{total}")
        self._tabs.setCurrentIndex(2)

    def _on_asset_done(self, asset_id: str, filepath: str, success: bool):
        # asset_id from worker matches ImageTask.asset_id (e.g. "C01_角色三视图")
        item = self._asset_grid_items.get(asset_id)
        if item:
            item.set_status("done" if success else "failed", filepath if success else "")
        else:
            # Fallback: try character ID prefix match
            prefix = asset_id.split("_")[0] if "_" in asset_id else asset_id
            for key, it in self._asset_grid_items.items():
                if key.startswith(prefix):
                    it.set_status("done" if success else "failed", filepath if success else "")
                    break
        self._status_lbl.setText(f"{'✅' if success else '❌'} {asset_id}")

    # ── Phase 4 ──

    def _on_sb_episode(self, ep_num: int, sb_data: dict):
        self._storyboards[ep_num] = sb_data
        self._ep_nav.set_episodes(max(self._storyboards.keys()))
        self._tabs.setCurrentIndex(3)

    def _on_episode_selected(self, ep_num: int):
        sb = self._storyboards.get(ep_num)
        if sb:
            self._sb_view.load_storyboard(sb)

    # ── Finished ──

    def _on_finished(self, success: bool, msg: str):
        self._reset_ui()
        if success:
            self._btn_export.setEnabled(True)
            self._status_lbl.setText(f"✅ {msg}")
        else:
            QMessageBox.critical(self.main_window, "生成失败", msg)

    # ── Export ──

    def _export_all(self):
        if not self._project_dir:
            return
        path = QFileDialog.getExistingDirectory(
            self.main_window, "选择导出目录",
            str(Path.home() / "Desktop"))
        if not path:
            return

        import shutil
        dest = os.path.join(path, os.path.basename(self._project_dir))
        try:
            if os.path.exists(dest):
                shutil.rmtree(dest)
            shutil.copytree(self._project_dir, dest)
            self._status_lbl.setText(f"已导出到: {dest}")
            QMessageBox.information(self.main_window, "导出成功",
                                    f"项目已导出到:\n{dest}")
        except Exception as e:
            QMessageBox.critical(self.main_window, "导出失败", str(e))

    # ── Asset Click (Regenerate) / Replace ──

    def _on_asset_replace(self, asset_id: str):
        """通过右键菜单上传本地图片替换角色图"""
        item = self._asset_grid_items.get(asset_id)
        if not item:
            return
        path, _ = QFileDialog.getOpenFileName(
            self.main_window, f"选择替换图片 — {asset_id}",
            "", "Images (*.png *.jpg *.jpeg *.webp *.bmp);;All Files (*)")
        if not path:
            return
        try:
            import shutil
            filepath = item._filepath
            if os.path.exists(filepath):
                shutil.copy2(filepath, filepath + ".replace.bak")
            shutil.copy2(path, filepath)
            if os.path.exists(filepath + ".replace.bak"):
                os.remove(filepath + ".replace.bak")
            item.set_status("done", filepath)
            self._status_lbl.setText(f"✅ {asset_id} 已替换为上传图片")
        except Exception as e:
            QMessageBox.critical(self.main_window, "替换失败", str(e))

    def _on_asset_clicked(self, asset_id: str, filepath: str):
        item = self._asset_grid_items.get(asset_id)
        if not item or not self._noova_api:
            return

        asset_type = item._asset_type
        prompt = getattr(item, "_prompt", "")
        # Get name from display format: extract after the last "·" for characters
        full_name = asset_id.split("_", 1)[1] if "_" in asset_id and len(asset_id.split("_", 1)) > 1 else asset_id
        display_name = full_name if full_name else asset_id

        dlg = RegenerateDialog(
            asset_id, display_name, asset_type, prompt,
            filepath, self._noova_api, self.main_window)
        if dlg.exec_() or dlg.should_reload():
            # Refresh the grid item preview
            pix = QPixmap(filepath)
            if not pix.isNull():
                item.set_status("done", filepath)
            self._status_lbl.setText(f"✅ {asset_id} 已更新")

    # ── Display formatters ──

    def _fmt_script_display(self, d: dict) -> str:
        lines = [
            f"# {d.get('title', '未命名')}",
            "", f"> {d.get('summary', '')}", "",
            f"**类型**: {d.get('genre', '')}",
            "", "---", "## 📜 角色", "",
        ]
        for c in d.get("characters", []):
            lines.append(
                f"### {c['id']} — {c.get('name', '')}（{c.get('role', '')}）\n"
                f"- 性别: {c.get('gender', '')} | 年龄: {c.get('age_range', '')}\n"
                f"- 外貌: {c.get('appearance', '')}\n"
                f"- 服装: {c.get('clothing', '')}\n"
                f"- 特征: {c.get('distinctive_features', '')}\n")
        lines += ["---", "## 🏠 场景", ""]
        for s in d.get("scenes", []):
            lines.append(
                f"### {s['id']} — {s.get('name', '')}\n"
                f"- 类型: {s.get('type', '')} | 时间: {s.get('time_of_day', '')}\n"
                f"- 光线: {s.get('lighting', '')}\n"
                f"- 描述: {s.get('description', '')}\n"
                f"- 氛围: {s.get('mood', '')}\n")
        lines += ["---", "## 📦 道具", ""]
        for p in d.get("props", []):
            lines.append(f"- **{p['id']}** — {p.get('name', '')}: {p.get('description', '')}")
        lines += ["", "---", "## 🎬 四幕剧本", ""]
        for ep in d.get("episodes", []):
            lines.append(
                f"### 第 {ep.get('episode', '?')} 集 — {ep.get('act', '')}\n"
                f"**{ep.get('title', '')}**\n\n"
                f"{ep.get('summary', '')}\n\n"
                f"- 角色: {', '.join(ep.get('characters_in_scene', []))}\n"
                f"- 场景: {ep.get('scene_id', '')} | 道具: {', '.join(ep.get('key_props', []))}\n"
                f"- 情感: {ep.get('emotion', '')} | 氛围: {ep.get('visual_mood', '')}\n")
        return "\n".join(lines)

    def _fmt_asset_display(self, a: dict) -> str:
        lines = ["# 素材清单", ""]
        lines += ["## 👤 角色素材", ""]
        for ca in a.get("character_assets", []):
            cid = ca.get("character_id", "??")
            name = ca.get("name", "")
            view_label = ca.get("view_label", "")
            purpose = ca.get("purpose", "")
            prompt = ca.get("prompt", "")
            lines.append(f"### {cid} — {name} · {view_label}")
            if purpose:
                lines.append(f"*用途: {purpose}*")
            lines.append("")
            lines.append(prompt)
            lines.append("")
        lines += ["---", "## 🏠 场景素材", ""]
        for sa in a.get("scene_assets", []):
            sid = sa.get("scene_id", "??")
            name = sa.get("name", "")
            purpose = sa.get("purpose", "")
            prompt = sa.get("prompt", "")
            lines.append(f"### {sid} — {name}")
            if purpose:
                lines.append(f"*用途: {purpose}*")
            lines.append("")
            lines.append(prompt)
            lines.append("")
        lines += ["---", "## 📦 道具素材", ""]
        for pa in a.get("prop_assets", []):
            pid = pa.get("prop_id", "??")
            name = pa.get("name", "")
            purpose = pa.get("purpose", "")
            prompt = pa.get("prompt", "")
            lines.append(f"### {pid} — {name}")
            if purpose:
                lines.append(f"*用途: {purpose}*")
            lines.append("")
            lines.append(prompt)
            lines.append("")
        return "\n".join(lines)

    # ── Lifecycle ──

    def on_plugin_loaded(self):
        pass

    def on_plugin_unloaded(self):
        self.stop()
