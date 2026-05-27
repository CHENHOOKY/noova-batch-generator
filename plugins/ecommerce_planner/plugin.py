"""电商套图AI规划器 —— EcommercePlannerPlugin（主插件类）

4 阶段流水线:
  Phase 0: DeepSeek 文本视觉推理 (M1 + M3)
  Phase 1: DeepSeek 意图解析 (M2)
  Phase 2: DeepSeek 出图提示词生成
  Phase 3: Noova API 批量出图 → 右侧画廊展示
"""

import json
import os
import re
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QScrollArea,
    QLabel, QPushButton, QTextEdit, QLineEdit, QCheckBox,
    QTabWidget, QProgressBar, QFileDialog, QMessageBox, QSplitter,
    QGridLayout, QSizePolicy, QSpinBox, QApplication,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap

from plugin_base import BasePlugin
from plugins._design import COMBO_STYLE, INPUT_STYLE, NoScrollComboBox as QComboBox
from plugins._noova_api import MODEL_CONFIG

from plugins.ecommerce_planner.config import (
    DS_BASE_URL, DS_MODELS, NOOVA_BASE_URL,
    DEFAULT_IMAGE_MODEL, DEFAULT_IMAGE_SIZE, DEFAULT_ASPECT_RATIO,
    CATEGORY_OPTIONS, PLATFORM_OPTIONS, TASK_TYPE_OPTIONS,
)
from plugins.ecommerce_planner.worker import EcommerceWorker


class EcommercePlannerPlugin(BasePlugin):
    plugin_id = "ecommerce_planner"
    name = "电商套图AI规划器"
    version = "2.0.0"
    description = (
        "输入产品信息，AI 推理视觉DNA并直接生成 N 套差异化方案图\n"
        "DeepSeek 文本推理 + Noova 出图，所见即所得"
    )
    icon = "🛒"
    color = "#F97316"

    _STYLE_SECTION_CSS = (
        "QFrame#section { background: #FFFFFF; border: 1px solid #E5E7EB;"
        " border-radius: 12px; padding: 16px; }"
    )
    _LABEL_CSS = "font-size: 13px; font-weight: 600; color: #6B7280; background: transparent;"

    def __init__(self):
        super().__init__()
        self._worker: EcommerceWorker | None = None
        self._vision_data: dict | None = None
        self._intent_data: dict | None = None
        self._prompts_data: dict | None = None
        self._image_paths: dict[int, str] = {}  # index -> save_path
        self._image_metas: dict[int, dict] = {}  # index -> proposal dict
        self._image_cards: list[QFrame] = []
        self._product_image_paths: list[str] = []
        self._product_thumb_labels: list[QLabel] = []
        self._ref_image_paths: list[str] = []
        self._ref_thumb_labels: list[QLabel] = []

    # ── Workspace ────────────────────────────

    def create_workspace(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet(
            "background: #F8F9FC;"
            "font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif;")

        self._status_lbl = QLabel("就绪")
        self._status_lbl.setStyleSheet("font-size: 12px; color: #9CA3AF;")

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([420, 700])

        root = QVBoxLayout(w)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(splitter)
        return w

    # ── Left Panel ───────────────────────────

    def _build_left_panel(self) -> QWidget:
        left = QWidget()
        left.setFixedWidth(420)
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
        title = QLabel("🛒 电商套图AI规划器")
        title.setStyleSheet(
            "font-size: 18px; font-weight: 700; color: #1E1E2E; background: transparent;")
        layout.addWidget(title)

        sub = QLabel(
            "输入产品信息，AI 推理视觉DNA并直接生成方案图\n"
            "DeepSeek 做视觉推理 + Noova 出图 API 直接出图\n"
            "选择方案数量，一键生成 N 张不同风格的电商套图")
        sub.setWordWrap(True)
        sub.setStyleSheet("font-size: 12px; color: #9CA3AF; background: transparent;")
        layout.addWidget(sub)

        # ── Product Image Section ──
        sec_img = self._section_frame()
        si = QVBoxLayout(sec_img)
        si.setContentsMargins(12, 12, 12, 12)
        si.setSpacing(8)
        si.addWidget(self._section_title("📷 产品图（最多 3 张）"))

        row = QHBoxLayout()
        btn = QPushButton("📁 上传产品图")
        btn.setStyleSheet(self._btn_secondary_css())
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(self._upload_product_images)
        row.addWidget(btn)
        row.addStretch()
        si.addLayout(row)

        self._product_thumb_container = QWidget()
        self._product_thumb_layout = QHBoxLayout(self._product_thumb_container)
        self._product_thumb_layout.setContentsMargins(0, 0, 0, 0)
        self._product_thumb_layout.setSpacing(6)
        self._product_thumb_layout.addStretch()
        si.addWidget(self._product_thumb_container)
        layout.addWidget(sec_img)

        # ── Reference Image Section ──
        sec_ref = self._section_frame()
        sr = QVBoxLayout(sec_ref)
        sr.setContentsMargins(12, 12, 12, 12)
        sr.setSpacing(8)
        sr.addWidget(self._section_title("🎨 参考图 — 对标风格（最多 5 张）"))

        row2 = QHBoxLayout()
        btn2 = QPushButton("📁 上传参考图")
        btn2.setStyleSheet(self._btn_secondary_css())
        btn2.setCursor(Qt.PointingHandCursor)
        btn2.clicked.connect(self._upload_ref_images)
        row2.addWidget(btn2)
        row2.addStretch()
        sr.addLayout(row2)

        self._ref_thumb_container = QWidget()
        self._ref_thumb_layout = QHBoxLayout(self._ref_thumb_container)
        self._ref_thumb_layout.setContentsMargins(0, 0, 0, 0)
        self._ref_thumb_layout.setSpacing(6)
        self._ref_thumb_layout.addStretch()
        sr.addWidget(self._ref_thumb_container)
        layout.addWidget(sec_ref)

        # ── Product Info ──
        sec1 = self._section_frame()
        s1 = QVBoxLayout(sec1)
        s1.setContentsMargins(12, 12, 12, 12)
        s1.setSpacing(8)
        s1.addWidget(self._section_title("📝 产品信息"))

        s1.addWidget(self._lbl("产品名称"))
        self._input_name = QLineEdit()
        self._input_name.setPlaceholderText("如：氨基酸洁面慕斯")
        self._input_name.setStyleSheet(INPUT_STYLE)
        s1.addWidget(self._input_name)

        s1.addWidget(self._lbl("类目"))
        self._combo_category = QComboBox()
        self._combo_category.addItems(CATEGORY_OPTIONS)
        self._combo_category.setStyleSheet(COMBO_STYLE)
        s1.addWidget(self._combo_category)

        s1.addWidget(self._lbl("材质描述"))
        self._input_material = QLineEdit()
        self._input_material.setPlaceholderText("如：磨砂玻璃瓶身，白色慕斯质地")
        self._input_material.setStyleSheet(INPUT_STYLE)
        s1.addWidget(self._input_material)

        s1.addWidget(self._lbl("颜色描述"))
        self._input_color = QLineEdit()
        self._input_color.setPlaceholderText("如：瓶身哑光白，膏体纯白")
        self._input_color.setStyleSheet(INPUT_STYLE)
        s1.addWidget(self._input_color)

        s1.addWidget(self._lbl("品牌标识 / Logo"))
        self._input_brand = QLineEdit()
        self._input_brand.setPlaceholderText("如：瓶身正面银色logo 'DR.SOFT'")
        self._input_brand.setStyleSheet(INPUT_STYLE)
        s1.addWidget(self._input_brand)
        layout.addWidget(sec1)

        # ── Strategy ──
        sec2 = self._section_frame()
        s2 = QVBoxLayout(sec2)
        s2.setContentsMargins(12, 12, 12, 12)
        s2.setSpacing(8)
        s2.addWidget(self._section_title("🎯 策略"))

        s2.addWidget(self._lbl("目标平台"))
        self._combo_platform = QComboBox()
        self._combo_platform.addItems(PLATFORM_OPTIONS)
        self._combo_platform.setStyleSheet(COMBO_STYLE)
        s2.addWidget(self._combo_platform)

        s2.addWidget(self._lbl("任务类型"))
        self._combo_task = QComboBox()
        self._combo_task.addItems(TASK_TYPE_OPTIONS)
        self._combo_task.setStyleSheet(COMBO_STYLE)
        s2.addWidget(self._combo_task)

        s2.addWidget(self._lbl("风格方向（可选）"))
        self._input_style = QLineEdit()
        self._input_style.setPlaceholderText("如：极简高端、夏日清爽、国潮复古... 留空由AI发想")
        self._input_style.setStyleSheet(INPUT_STYLE)
        s2.addWidget(self._input_style)

        self._check_redesign = QCheckBox("🔄 改版意图（在原图基础上优化升级）")
        self._check_redesign.setStyleSheet(
            "QCheckBox { font-size: 13px; color: #6B7280; background: transparent;"
            " spacing: 8px; }"
            "QCheckBox::indicator { width: 18px; height: 18px;"
            " border: 2px solid #D1D5DB; border-radius: 4px; background: #FFFFFF; }"
            "QCheckBox::indicator:checked { background: #F97316; border-color: #F97316; }")
        self._check_redesign.setCursor(Qt.PointingHandCursor)
        s2.addWidget(self._check_redesign)

        # Image count
        count_row = QHBoxLayout()
        count_row.addWidget(self._lbl("方案图数量"))
        self._spin_count = QSpinBox()
        self._spin_count.setRange(1, 10)
        self._spin_count.setValue(3)
        self._spin_count.setSuffix(" 张")
        self._spin_count.setStyleSheet(
            "QSpinBox { border: 1px solid #E5E7EB; border-radius: 10px;"
            " padding: 9px 12px; font-size: 14px; background: #FAFAFA;"
            " color: #1A1A1A; }"
            "QSpinBox:focus { border: 1px solid #F97316; background: #FFFFFF; }")
        count_row.addWidget(self._spin_count)
        count_row.addStretch()
        s2.addLayout(count_row)
        layout.addWidget(sec2)

        # ── Image Settings ──
        sec_imgset = self._section_frame()
        sis = QVBoxLayout(sec_imgset)
        sis.setContentsMargins(12, 12, 12, 12)
        sis.setSpacing(8)
        sis.addWidget(self._section_title("🖼️ 出图设置"))

        sis.addWidget(self._lbl("比例"))
        self._combo_ratio = QComboBox()
        self._combo_ratio.setStyleSheet(COMBO_STYLE)
        sis.addWidget(self._combo_ratio)

        sis.addWidget(self._lbl("尺寸"))
        self._combo_img_size = QComboBox()
        self._combo_img_size.setStyleSheet(COMBO_STYLE)
        sis.addWidget(self._combo_img_size)
        layout.addWidget(sec_imgset)

        # ── API Config ──
        sec_api = self._section_frame()
        sa = QVBoxLayout(sec_api)
        sa.setContentsMargins(12, 12, 12, 12)
        sa.setSpacing(8)
        sa.addWidget(self._section_title("🔑 API 配置"))

        # DeepSeek
        sa.addWidget(QLabel("DeepSeek API Key（文本推理，必填）"))
        self._input_ds_key = QLineEdit()
        self._input_ds_key.setPlaceholderText("DeepSeek API Key")
        self._input_ds_key.setEchoMode(QLineEdit.Password)
        self._input_ds_key.setText(os.environ.get("DEEPSEEK_API_KEY", ""))
        self._input_ds_key.setStyleSheet(INPUT_STYLE)
        sa.addWidget(self._input_ds_key)

        sa.addWidget(QLabel("DeepSeek 模型"))
        self._combo_ds_model = QComboBox()
        self._combo_ds_model.addItems(DS_MODELS)
        self._combo_ds_model.setStyleSheet(COMBO_STYLE)
        sa.addWidget(self._combo_ds_model)

        # Noova
        sa.addWidget(QLabel("Noova API Key（出图，必填）"))
        self._input_img_key = QLineEdit()
        self._input_img_key.setPlaceholderText("Noova API Key")
        self._input_img_key.setEchoMode(QLineEdit.Password)
        self._input_img_key.setStyleSheet(INPUT_STYLE)
        sa.addWidget(self._input_img_key)

        sa.addWidget(QLabel("出图模型"))
        self._combo_img_model = QComboBox()
        model_keys = list(MODEL_CONFIG.keys())
        self._combo_img_model.addItems(model_keys)
        default_idx = model_keys.index(DEFAULT_IMAGE_MODEL) if DEFAULT_IMAGE_MODEL in model_keys else 0
        self._combo_img_model.setCurrentIndex(default_idx)
        self._combo_img_model.setStyleSheet(COMBO_STYLE)
        self._combo_img_model.currentTextChanged.connect(self._on_img_model_changed)
        sa.addWidget(self._combo_img_model)
        layout.addWidget(sec_api)

        # Init image model settings
        self._on_img_model_changed(self._combo_img_model.currentText())

        # ── Buttons ──
        self._btn_gen = QPushButton("🚀 生成方案图")
        self._btn_gen.setStyleSheet(
            "QPushButton { background: #F97316; border: none; border-radius: 10px;"
            " padding: 14px 28px; font-size: 15px; color: white; font-weight: 700; }"
            "QPushButton:hover { background: #EA580C; }"
            "QPushButton:disabled { background: #FDBA74; }")
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
            "QProgressBar::chunk { background: #F97316; border-radius: 8px; }")
        layout.addWidget(self._progress_bar)

        self._phase_lbl = QLabel("")
        self._phase_lbl.setStyleSheet(
            "font-size: 12px; color: #F97316; font-weight: 600; background: transparent;")
        layout.addWidget(self._phase_lbl)

        layout.addWidget(self._status_lbl)
        layout.addStretch()

        scroll.setWidget(inner)
        outer = QVBoxLayout(left)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        return left

    # ── Right Panel — Image Gallery ──────────

    def _build_right_panel(self) -> QWidget:
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)

        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(
            "QTabWidget::pane { border: none; background: #FFFFFF; }"
            "QTabBar::tab { background: #F3F4F6; border: none; padding: 10px 20px;"
            " font-size: 13px; color: #6B7280; font-weight: 600; margin-right: 2px; }"
            "QTabBar::tab:selected { background: #FFFFFF; color: #F97316;"
            " border-bottom: 2px solid #F97316; }")

        # Gallery tab
        gallery = QWidget()
        g_layout = QVBoxLayout(gallery)
        g_layout.setContentsMargins(0, 0, 0, 0)

        self._gallery_scroll = QScrollArea()
        self._gallery_scroll.setWidgetResizable(True)
        self._gallery_scroll.setStyleSheet(
            "QScrollArea { border: none; background: #FAFBFC; }")

        self._gallery_container = QWidget()
        self._gallery_container.setStyleSheet("background: #FAFBFC;")
        self._gallery_layout = QVBoxLayout(self._gallery_container)
        self._gallery_layout.setContentsMargins(24, 20, 24, 20)
        self._gallery_layout.setSpacing(20)

        self._gallery_placeholder = QLabel(
            "🖼️  方案图将在这里逐张展示\n\n"
            "填写左侧信息后点击「生成方案图」\n"
            "AI 将推理产品视觉DNA并直接出图")
        self._gallery_placeholder.setAlignment(Qt.AlignCenter)
        self._gallery_placeholder.setStyleSheet(
            "font-size: 15px; color: #9CA3AF; background: transparent;"
            " padding: 80px 40px;")
        self._gallery_layout.addWidget(self._gallery_placeholder)
        self._gallery_layout.addStretch()

        self._gallery_scroll.setWidget(self._gallery_container)
        g_layout.addWidget(self._gallery_scroll)
        self._tabs.addTab(gallery, "方案图")

        # JSON Raw tab
        self._tab_json = QTextEdit()
        self._tab_json.setReadOnly(True)
        self._tab_json.setPlaceholderText("运行日志与 JSON 数据将显示在这里...")
        self._tab_json.setStyleSheet(
            "QTextEdit { border: none; padding: 20px; font-size: 12px;"
            " background: #FAFAFA; color: #1E1E2E;"
            " font-family: 'Consolas', 'Courier New', monospace; }")
        self._tabs.addTab(self._tab_json, "JSON Log")

        rl.addWidget(self._tabs)

        # Bottom bar
        bar = QWidget()
        bar.setStyleSheet("background: #FFFFFF; border-top: 1px solid #E5E7EB;")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(16, 10, 16, 10)

        bar_layout.addStretch()

        self._btn_export = QPushButton("📥 导出全部")
        self._btn_export.setStyleSheet(
            "QPushButton { background: #F3F4F6; border: 1px solid #E5E7EB;"
            " border-radius: 8px; padding: 8px 18px; font-size: 13px;"
            " color: #374151; font-weight: 600; }"
            "QPushButton:hover { background: #E5E7EB; }")
        self._btn_export.setCursor(Qt.PointingHandCursor)
        self._btn_export.setEnabled(False)
        self._btn_export.clicked.connect(self._export)
        bar_layout.addWidget(self._btn_export)

        rl.addWidget(bar)
        return right

    # ── UI Helpers ───────────────────────────

    def _lbl(self, text: str) -> QLabel:
        l = QLabel(text)
        l.setStyleSheet(self._LABEL_CSS)
        return l

    def _section_frame(self) -> QFrame:
        sec = QFrame()
        sec.setObjectName("section")
        sec.setStyleSheet(self._STYLE_SECTION_CSS)
        return sec

    def _section_title(self, text: str) -> QLabel:
        tl = QLabel(text)
        tl.setStyleSheet(
            "font-size: 13px; font-weight: 700; color: #1E1E2E; background: transparent;")
        return tl

    def _btn_secondary_css(self) -> str:
        return (
            "QPushButton { background: #F3F4F6; border: 1px solid #E5E7EB;"
            " border-radius: 8px; padding: 8px 16px; font-size: 12px;"
            " color: #374151; font-weight: 600; }"
            "QPushButton:hover { background: #E5E7EB; }")

    # ── Image Model Change ───────────────────

    def _on_img_model_changed(self, model_name: str):
        cfg = MODEL_CONFIG.get(model_name, {})
        ratios = cfg.get("ratios", ["1:1"])
        sizes = cfg.get("sizes", ["1K"])

        self._combo_ratio.clear()
        self._combo_ratio.addItems(ratios)
        if "1:1" in ratios:
            self._combo_ratio.setCurrentText("1:1")

        self._combo_img_size.clear()
        self._combo_img_size.addItems(sizes)
        if DEFAULT_IMAGE_SIZE in sizes:
            self._combo_img_size.setCurrentText(DEFAULT_IMAGE_SIZE)

    # ── Image Upload ─────────────────────────

    def _render_thumb_grid(self, paths, labels, container_layout, max_count):
        for lbl in labels:
            lbl.deleteLater()
        labels.clear()

        for p in paths[:max_count]:
            thumb = QLabel()
            thumb.setFixedSize(64, 64)
            thumb.setScaledContents(True)
            thumb.setStyleSheet(
                "border: 1px solid #E5E7EB; border-radius: 6px;"
                " background: #F3F4F6;")
            pix = QPixmap(p)
            if not pix.isNull():
                thumb.setPixmap(pix.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                thumb.setToolTip(os.path.basename(p))
            else:
                thumb.setText("🖼️")
                thumb.setAlignment(Qt.AlignCenter)
            container_layout.insertWidget(container_layout.count() - 1, thumb)
            labels.append(thumb)

    def _upload_product_images(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self.main_window, "选择产品图片", "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)")
        if not paths:
            return
        self._product_image_paths = paths[:3]
        self._render_thumb_grid(
            self._product_image_paths, self._product_thumb_labels,
            self._product_thumb_layout, 3)

    def _upload_ref_images(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self.main_window, "选择参考图片", "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)")
        if not paths:
            return
        self._ref_image_paths = paths[:5]
        self._render_thumb_grid(
            self._ref_image_paths, self._ref_thumb_labels,
            self._ref_thumb_layout, 5)

    # ── Generate Flow ────────────────────────

    def _start(self):
        product_name = self._input_name.text().strip()
        if not product_name:
            QMessageBox.warning(self.main_window, "提示", "请输入产品名称")
            return

        ds_key = self._input_ds_key.text().strip()
        if not ds_key:
            QMessageBox.warning(self.main_window, "提示", "请输入 DeepSeek API Key")
            return

        img_key = self._input_img_key.text().strip()
        if not img_key:
            QMessageBox.warning(self.main_window, "提示", "请输入 Noova 出图 API Key")
            return

        ds_model = self._combo_ds_model.currentText()
        category = self._combo_category.currentText()
        material = self._input_material.text().strip()
        color_desc = self._input_color.text().strip()
        brand_marks = self._input_brand.text().strip()
        platform = self._combo_platform.currentText()
        task_type = self._combo_task.currentText()
        style_direction = self._input_style.text().strip()
        is_redesign = self._check_redesign.isChecked()
        image_count = self._spin_count.value()
        image_model = self._combo_img_model.currentText()
        aspect_ratio = self._combo_ratio.currentText()
        image_size = self._combo_img_size.currentText()

        ref_names = [os.path.basename(p) for p in self._ref_image_paths]

        # Output dir
        from plugins.ecommerce_planner.config import NOOVA_PROJECTS_DIR
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = re.sub(r'[\\/:*?"<>|]', '_', product_name)[:30]
        output_dir = os.path.join(NOOVA_PROJECTS_DIR, f"ecommerce_{safe_name}_{ts}")
        os.makedirs(output_dir, exist_ok=True)

        # Reset state
        self._vision_data = None
        self._intent_data = None
        self._prompts_data = None
        self._image_paths.clear()
        self._image_metas.clear()

        # Clear gallery
        for card in self._image_cards:
            card.deleteLater()
        self._image_cards.clear()
        self._gallery_placeholder.setVisible(True)
        self._tab_json.clear()
        self._tabs.setCurrentIndex(0)

        # UI state
        self._btn_gen.setVisible(False)
        self._btn_cancel.setVisible(True)
        self._progress_bar.setVisible(True)
        self._btn_export.setEnabled(False)
        self._phase_lbl.setText("")

        self._worker = EcommerceWorker(
            api_key=ds_key, base_url=DS_BASE_URL, ds_model=ds_model,
            product_name=product_name, category=category, material=material,
            color_desc=color_desc, brand_marks=brand_marks,
            platform=platform, task_type=task_type,
            style_direction=style_direction, is_redesign=is_redesign,
            product_image_paths=self._product_image_paths,
            ref_image_paths=self._ref_image_paths,
            image_count=image_count,
            image_api_key=img_key, image_model=image_model,
            aspect_ratio=aspect_ratio, image_size=image_size,
            output_dir=output_dir,
        )
        self._worker.log.connect(self._on_log)
        self._worker.progress.connect(self._on_progress)
        self._worker.vision_ready.connect(self._on_vision)
        self._worker.intent_ready.connect(self._on_intent)
        self._worker.prompts_ready.connect(self._on_prompts)
        self._worker.image_generated.connect(self._on_image_generated)
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
        # Append to JSON log
        current = self._tab_json.toPlainText()
        self._tab_json.setPlainText(current + msg + "\n")

    def _on_progress(self, pct: int, label: str):
        self._progress_bar.setValue(pct)
        self._phase_lbl.setText(label)

    # ── Phase 0 ──────────────────────────────

    def _on_vision(self, data: dict):
        self._vision_data = data
        routing = data.get("routing_mode", "?")
        self._status_lbl.setText(f"✅ 视觉推理完成 — 路由: {routing}")

    # ── Phase 1 ──────────────────────────────

    def _on_intent(self, data: dict):
        self._intent_data = data
        self._status_lbl.setText("✅ 意图解析完成，正在生成出图提示词...")

    # ── Phase 2 ──────────────────────────────

    def _on_prompts(self, data: dict):
        self._prompts_data = data
        proposals = data.get("proposals", [])
        self._tab_json.setPlainText(json.dumps(data, ensure_ascii=False, indent=2))
        self._status_lbl.setText(f"✅ 提示词生成完成 ({len(proposals)} 套)，正在出图...")

    # ── Phase 3: Per-image callback ──────────

    def _on_image_generated(self, index: int, save_path: str, metadata: dict):
        self._image_paths[index] = save_path
        self._image_metas[index] = metadata

        self._gallery_placeholder.setVisible(False)
        self._add_image_card(index, save_path, metadata)
        self._status_lbl.setText(f"🖼️  已完成 {len(self._image_paths)} 张出图")

    def _add_image_card(self, index: int, save_path: str, metadata: dict):
        style_name = metadata.get("style_name", f"方案 {index + 1}")
        rationale = metadata.get("design_rationale", "")
        cp = metadata.get("color_palette", {})
        primary = cp.get("primary", "")
        secondary = cp.get("secondary", "")
        accent = cp.get("accent", "")

        card = QFrame()
        card.setStyleSheet(
            "QFrame#imgCard { background: #FFFFFF; border: 1px solid #E5E7EB;"
            " border-radius: 14px; padding: 0px; }")
        card.setObjectName("imgCard")

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(10)

        # Header
        header = QHBoxLayout()
        num_lbl = QLabel(f"方案 {index + 1}")
        num_lbl.setStyleSheet(
            "font-size: 18px; font-weight: 700; color: #F97316; background: transparent;")
        header.addWidget(num_lbl)

        style_lbl = QLabel(style_name)
        style_lbl.setStyleSheet(
            "font-size: 16px; font-weight: 600; color: #1E1E2E; background: transparent;")
        header.addWidget(style_lbl)
        header.addStretch()

        # Color dots
        for hex_code in [primary, secondary, accent]:
            if hex_code and re.search(r"#[0-9A-Fa-f]{6}", hex_code):
                dot = QLabel()
                dot.setFixedSize(18, 18)
                dot.setStyleSheet(
                    f"background: {hex_code}; border-radius: 9px;"
                    f" border: 1px solid #DDD;")
                dot.setToolTip(hex_code)
                header.addWidget(dot)

        card_layout.addLayout(header)

        # Image
        img_label = QLabel()
        img_label.setAlignment(Qt.AlignCenter)
        img_label.setMinimumHeight(280)
        img_label.setMaximumHeight(500)
        img_label.setScaledContents(True)
        img_label.setStyleSheet(
            "background: #F5F5F5; border-radius: 10px; border: 1px solid #EEE;")

        pix = QPixmap(save_path)
        if not pix.isNull():
            scaled = pix.scaled(600, 450, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            img_label.setPixmap(scaled)
            img_label.setMaximumHeight(scaled.height())
            img_label.setMinimumHeight(scaled.height())
        else:
            img_label.setText("⚠️ 图片加载失败")
        card_layout.addWidget(img_label)

        # Rationale
        if rationale:
            r_lbl = QLabel(rationale)
            r_lbl.setWordWrap(True)
            r_lbl.setStyleSheet(
                "font-size: 13px; color: #6B7280; background: transparent;"
                " padding: 4px 0px;")
            card_layout.addWidget(r_lbl)

        # Bottom bar: prompt preview + download
        bottom = QHBoxLayout()
        prompt_text = metadata.get("image_prompt", "")
        if prompt_text:
            prompt_btn = QPushButton("📋 查看提示词")
            prompt_btn.setStyleSheet(
                "QPushButton { background: #F3F4F6; border: 1px solid #E5E7EB;"
                " border-radius: 6px; padding: 6px 14px; font-size: 12px;"
                " color: #6B7280; font-weight: 600; }"
                "QPushButton:hover { background: #E5E7EB; }")
            prompt_btn.setCursor(Qt.PointingHandCursor)
            prompt_btn.clicked.connect(
                lambda checked, p=prompt_text, n=style_name: self._show_prompt(n, p))
            bottom.addWidget(prompt_btn)
        bottom.addStretch()

        dl_btn = QPushButton("💾 下载")
        dl_btn.setStyleSheet(
            "QPushButton { background: #F97316; border: none; border-radius: 6px;"
            " padding: 6px 16px; font-size: 12px; color: white; font-weight: 600; }"
            "QPushButton:hover { background: #EA580C; }")
        dl_btn.setCursor(Qt.PointingHandCursor)
        dl_btn.clicked.connect(lambda checked, p=save_path: self._download_image(p))
        bottom.addWidget(dl_btn)

        card_layout.addLayout(bottom)
        self._image_cards.append(card)

        # Insert before stretch in gallery
        stretch = self._gallery_layout.takeAt(self._gallery_layout.count() - 1)
        self._gallery_layout.addWidget(card)
        if stretch:
            self._gallery_layout.addItem(stretch)

    def _show_prompt(self, style_name: str, prompt: str):
        dlg = QMessageBox(self.main_window)
        dlg.setWindowTitle(f"出图提示词 — {style_name}")
        dlg.setText(prompt)
        dlg.setTextInteractionFlags(Qt.TextSelectableByMouse)
        dlg.exec()

    def _download_image(self, save_path: str):
        dest, _ = QFileDialog.getSaveFileName(
            self.main_window, "保存图片", os.path.basename(save_path),
            "PNG (*.png);;JPEG (*.jpg)")
        if dest:
            import shutil
            shutil.copy2(save_path, dest)
            self._status_lbl.setText(f"✅ 已保存: {os.path.basename(dest)}")

    # ── Phase Complete ───────────────────────

    def _on_finished(self, success: bool, msg: str):
        self._reset_ui()
        if success:
            self._btn_export.setEnabled(True)
            self._status_lbl.setText(f"✅ {msg}")
        else:
            QMessageBox.critical(self.main_window, "生成失败", msg)

    # ── Export ────────────────────────────────

    def _export(self):
        if not self._image_paths:
            return

        path, _ = QFileDialog.getSaveFileName(
            self.main_window, "导出方案包", "",
            "JSON (*.json);;Markdown (*.md)")
        if not path:
            return

        try:
            if path.endswith(".json"):
                export = {
                    "vision_analysis": self._vision_data,
                    "intent_matrix": self._intent_data,
                    "proposals": self._prompts_data.get("proposals", []) if self._prompts_data else [],
                    "generated_images": list(self._image_paths.values()),
                }
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(export, f, ensure_ascii=False, indent=2)
            else:
                lines = [
                    "# 电商套图AI规划方案",
                    f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    "",
                ]
                diagnostic = (self._prompts_data or {}).get("_system_diagnostic_log", {})
                if diagnostic:
                    lines.append("## 系统诊断")
                    for k, v in diagnostic.items():
                        lines.append(f"- **{k}**: {v}")
                    lines.append("")

                proposals = (self._prompts_data or {}).get("proposals", [])
                for i, p in enumerate(proposals):
                    lines.append(f"## 方案 {i+1}: {p.get('style_name', '')}")
                    lines.append(f"**设计思路**: {p.get('design_rationale', '')}")
                    lines.append(f"**色彩**: {p.get('color_palette', {})}")
                    lines.append(f"**出图提示词**:")
                    lines.append(f"```")
                    lines.append(p.get("image_prompt", ""))
                    lines.append(f"```")
                    lines.append("")
                with open(path, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines))

            self._status_lbl.setText(f"✅ 已导出: {os.path.basename(path)}")
            QMessageBox.information(self.main_window, "导出成功", f"方案已导出到:\n{path}")
        except Exception as e:
            QMessageBox.critical(self.main_window, "导出失败", str(e))
