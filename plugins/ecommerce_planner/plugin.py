"""电商套图AI规划器 —— EcommercePlannerPlugin（主插件类）"""

import json
import os
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QScrollArea,
    QLabel, QPushButton, QTextEdit, QLineEdit,
    QTabWidget, QProgressBar, QFileDialog, QMessageBox, QSplitter,
    QGridLayout, QSizePolicy,
)
from PySide6.QtCore import Qt

from plugin_base import BasePlugin
from plugins._design import COMBO_STYLE, INPUT_STYLE, NoScrollComboBox as QComboBox

from plugins.ecommerce_planner.config import (
    DS_BASE_URL, DS_MODELS,
    CATEGORY_OPTIONS, PLATFORM_OPTIONS, TASK_TYPE_OPTIONS,
)
from plugins.ecommerce_planner.worker import EcommerceWorker


class EcommercePlannerPlugin(BasePlugin):
    plugin_id = "ecommerce_planner"
    name = "电商套图AI规划器"
    version = "1.0.0"
    description = (
        "输入产品信息和平台，AI 生成 3 套差异化视觉企划方案\n"
        "含色彩资产、排版哲学、文案策略、信任证据规划"
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
        self._intent_data: dict | None = None
        self._proposals_data: dict | None = None
        self._ref_image_paths: list[str] = []
        self._ref_thumb_labels: list[QLabel] = []

    # ── Workspace ────────────────────────────

    def create_workspace(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet(
            "background: #F8F9FC;"
            "font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif;")

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([380, 700])

        root = QVBoxLayout(w)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(splitter)
        return w

    # ── Left Panel ───────────────────────────

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
        title = QLabel("🛒 电商套图AI规划器")
        title.setStyleSheet(
            "font-size: 18px; font-weight: 700; color: #1E1E2E; background: transparent;")
        layout.addWidget(title)

        sub = QLabel(
            "输入产品信息，AI 自动解析意图并生成 "
            "A/B/C 三套差异化视觉企划方案\n"
            "包含色彩资产、排版哲学、文案策略、信任证据规划")
        sub.setWordWrap(True)
        sub.setStyleSheet("font-size: 12px; color: #9CA3AF; background: transparent;")
        layout.addWidget(sub)

        # ── Product Info Section ──
        sec1 = self._build_section_frame()
        s1 = QVBoxLayout(sec1)
        s1.setContentsMargins(12, 12, 12, 12)
        s1.setSpacing(8)
        s1.addWidget(self._make_section_title("📦 产品信息"))

        s1.addWidget(self._make_label("产品名称"))
        self._input_name = QLineEdit()
        self._input_name.setPlaceholderText("如：氨基酸洁面慕斯")
        self._input_name.setStyleSheet(INPUT_STYLE)
        s1.addWidget(self._input_name)

        s1.addWidget(self._make_label("类目"))
        self._combo_category = QComboBox()
        self._combo_category.addItems(CATEGORY_OPTIONS)
        self._combo_category.setStyleSheet(COMBO_STYLE)
        s1.addWidget(self._combo_category)

        s1.addWidget(self._make_label("材质描述"))
        self._input_material = QLineEdit()
        self._input_material.setPlaceholderText("如：磨砂玻璃瓶身，白色慕斯质地")
        self._input_material.setStyleSheet(INPUT_STYLE)
        s1.addWidget(self._input_material)

        s1.addWidget(self._make_label("颜色描述"))
        self._input_color = QLineEdit()
        self._input_color.setPlaceholderText("如：瓶身哑光白，膏体纯白")
        self._input_color.setStyleSheet(INPUT_STYLE)
        s1.addWidget(self._input_color)

        s1.addWidget(self._make_label("品牌标识 / Logo"))
        self._input_brand = QLineEdit()
        self._input_brand.setPlaceholderText("如：瓶身正面银色logo 'DR.SOFT'")
        self._input_brand.setStyleSheet(INPUT_STYLE)
        s1.addWidget(self._input_brand)
        layout.addWidget(sec1)

        # ── Strategy Section ──
        sec2 = self._build_section_frame()
        s2 = QVBoxLayout(sec2)
        s2.setContentsMargins(12, 12, 12, 12)
        s2.setSpacing(8)
        s2.addWidget(self._make_section_title("🎯 策略"))

        s2.addWidget(self._make_label("目标平台"))
        self._combo_platform = QComboBox()
        self._combo_platform.addItems(PLATFORM_OPTIONS)
        self._combo_platform.setStyleSheet(COMBO_STYLE)
        s2.addWidget(self._combo_platform)

        s2.addWidget(self._make_label("任务类型"))
        self._combo_task = QComboBox()
        self._combo_task.addItems(TASK_TYPE_OPTIONS)
        self._combo_task.setStyleSheet(COMBO_STYLE)
        s2.addWidget(self._combo_task)

        s2.addWidget(self._make_label("风格方向（可选）"))
        self._input_style = QLineEdit()
        self._input_style.setPlaceholderText("如：极简高端、夏日清爽、国潮复古... 留空由AI发想")
        self._input_style.setStyleSheet(INPUT_STYLE)
        s2.addWidget(self._input_style)
        layout.addWidget(sec2)

        # ── Reference Image Section ──
        sec3 = self._build_section_frame()
        s3 = QVBoxLayout(sec3)
        s3.setContentsMargins(12, 12, 12, 12)
        s3.setSpacing(8)
        s3.addWidget(self._make_section_title("🖼️ 参考图（可选）"))

        upload_row = QHBoxLayout()
        upload_btn = QPushButton("📁 上传图片")
        upload_btn.setStyleSheet(
            "QPushButton { background: #F3F4F6; border: 1px solid #E5E7EB;"
            " border-radius: 8px; padding: 8px 16px; font-size: 12px;"
            " color: #374151; font-weight: 600; }"
            "QPushButton:hover { background: #E5E7EB; }")
        upload_btn.setCursor(Qt.PointingHandCursor)
        upload_btn.clicked.connect(self._upload_ref_images)
        upload_row.addWidget(upload_btn)
        upload_row.addStretch()
        s3.addLayout(upload_row)

        self._ref_thumb_container = QWidget()
        self._ref_thumb_layout = QHBoxLayout(self._ref_thumb_container)
        self._ref_thumb_layout.setContentsMargins(0, 0, 0, 0)
        self._ref_thumb_layout.setSpacing(6)
        self._ref_thumb_layout.addStretch()
        s3.addWidget(self._ref_thumb_container)
        layout.addWidget(sec3)

        # ── API Config Section ──
        sec4 = self._build_section_frame()
        s4 = QVBoxLayout(sec4)
        s4.setContentsMargins(12, 12, 12, 12)
        s4.setSpacing(8)
        s4.addWidget(self._make_section_title("🔑 DeepSeek API 配置"))

        s4.addWidget(QLabel("API Key"))
        self._input_ds_key = QLineEdit()
        self._input_ds_key.setPlaceholderText("DeepSeek API Key")
        self._input_ds_key.setEchoMode(QLineEdit.Password)
        self._input_ds_key.setText(os.environ.get("DEEPSEEK_API_KEY", ""))
        self._input_ds_key.setStyleSheet(INPUT_STYLE)
        s4.addWidget(self._input_ds_key)

        s4.addWidget(QLabel("Model"))
        self._combo_ds_model = QComboBox()
        self._combo_ds_model.addItems(DS_MODELS)
        self._combo_ds_model.setStyleSheet(COMBO_STYLE)
        s4.addWidget(self._combo_ds_model)
        layout.addWidget(sec4)

        # ── Buttons ──
        self._btn_gen = QPushButton("🚀 生成方案")
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

        self._status_lbl = QLabel("就绪")
        self._status_lbl.setStyleSheet(
            "font-size: 12px; color: #9CA3AF; background: transparent;")
        layout.addWidget(self._status_lbl)

        layout.addStretch()
        scroll.setWidget(inner)
        outer = QVBoxLayout(left)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        return left

    # ── Right Panel ──────────────────────────

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
            "QTabBar::tab:selected { background: #FFFFFF; color: #F97316;"
            " border-bottom: 2px solid #F97316; }")

        self._text_style = (
            "QTextEdit { border: none; padding: 20px; font-size: 14px;"
            " background: #FFFFFF; color: #1E1E2E;"
            " font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif; }")

        # Tabs A, B, C
        self._tab_a = QTextEdit()
        self._tab_a.setReadOnly(True)
        self._tab_a.setPlaceholderText("方案 A 将显示在这里...")
        self._tab_a.setStyleSheet(self._text_style)
        self._tabs.addTab(self._tab_a, "方案 A")

        self._tab_b = QTextEdit()
        self._tab_b.setReadOnly(True)
        self._tab_b.setPlaceholderText("方案 B 将显示在这里...")
        self._tab_b.setStyleSheet(self._text_style)
        self._tabs.addTab(self._tab_b, "方案 B")

        self._tab_c = QTextEdit()
        self._tab_c.setReadOnly(True)
        self._tab_c.setPlaceholderText("方案 C 将显示在这里...")
        self._tab_c.setStyleSheet(self._text_style)
        self._tabs.addTab(self._tab_c, "方案 C")

        # JSON Raw tab
        self._tab_json = QTextEdit()
        self._tab_json.setReadOnly(True)
        self._tab_json.setPlaceholderText("原始 JSON 数据将显示在这里...")
        self._tab_json.setStyleSheet(
            "QTextEdit { border: none; padding: 20px; font-size: 12px;"
            " background: #FAFAFA; color: #1E1E2E;"
            " font-family: 'Consolas', 'Courier New', monospace; }")
        self._tabs.addTab(self._tab_json, "JSON Raw")

        rl.addWidget(self._tabs)

        # Bottom bar
        bar = QWidget()
        bar.setStyleSheet("background: #FFFFFF; border-top: 1px solid #E5E7EB;")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(16, 10, 16, 10)

        bar_layout.addWidget(self._status_lbl)
        bar_layout.addStretch()

        self._btn_export = QPushButton("📥 导出方案")
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

    def _make_label(self, text: str) -> QLabel:
        l = QLabel(text)
        l.setStyleSheet(self._LABEL_CSS)
        return l

    def _build_section_frame(self) -> QFrame:
        sec = QFrame()
        sec.setObjectName("section")
        sec.setStyleSheet(self._STYLE_SECTION_CSS)
        return sec

    def _make_section_title(self, text: str) -> QLabel:
        tl = QLabel(text)
        tl.setStyleSheet(
            "font-size: 13px; font-weight: 700; color: #1E1E2E; background: transparent;")
        return tl

    # ── Reference Image Upload ──────────────

    def _upload_ref_images(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self.main_window, "选择参考图片", "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)")
        if not paths:
            return

        # Clear existing
        for lbl in self._ref_thumb_labels:
            lbl.deleteLater()
        self._ref_thumb_labels.clear()
        self._ref_image_paths.clear()

        # Add new (max 5)
        for p in paths[:5]:
            self._ref_image_paths.append(p)
            thumb = QLabel()
            thumb.setFixedSize(64, 64)
            thumb.setScaledContents(True)
            thumb.setStyleSheet(
                "border: 1px solid #E5E7EB; border-radius: 6px;"
                " background: #F3F4F6;")
            from PySide6.QtGui import QPixmap
            pix = QPixmap(p)
            if not pix.isNull():
                thumb.setPixmap(pix.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                thumb.setToolTip(os.path.basename(p))
            else:
                thumb.setText("🖼️")
                thumb.setAlignment(Qt.AlignCenter)
            # Insert before stretch
            self._ref_thumb_layout.insertWidget(
                self._ref_thumb_layout.count() - 1, thumb)
            self._ref_thumb_labels.append(thumb)

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

        ds_model = self._combo_ds_model.currentText()
        category = self._combo_category.currentText()
        material = self._input_material.text().strip()
        color_desc = self._input_color.text().strip()
        brand_marks = self._input_brand.text().strip()
        platform = self._combo_platform.currentText()
        task_type = self._combo_task.currentText()
        style_direction = self._input_style.text().strip()

        # Reset state
        self._intent_data = None
        self._proposals_data = None

        # Clear all tabs
        self._tab_a.clear()
        self._tab_b.clear()
        self._tab_c.clear()
        self._tab_json.clear()
        self._tabs.setCurrentIndex(0)

        # UI state
        self._btn_gen.setVisible(False)
        self._btn_cancel.setVisible(True)
        self._progress_bar.setVisible(True)
        self._btn_export.setEnabled(False)
        self._phase_lbl.setText("")

        # Build style direction with ref image info
        full_style = style_direction
        if self._ref_image_paths:
            ref_names = [os.path.basename(p) for p in self._ref_image_paths]
            ref_info = f"用户上传了 {len(ref_names)} 张参考图: {', '.join(ref_names)}"
            if style_direction:
                full_style = f"{style_direction}（{ref_info}）"
            else:
                full_style = ref_info

        self._worker = EcommerceWorker(
            api_key=ds_key, base_url=DS_BASE_URL, ds_model=ds_model,
            product_name=product_name, category=category, material=material,
            color_desc=color_desc, brand_marks=brand_marks,
            platform=platform, task_type=task_type,
            style_direction=full_style,
        )
        self._worker.log.connect(self._on_log)
        self._worker.progress.connect(self._on_progress)
        self._worker.intent_ready.connect(self._on_intent)
        self._worker.proposals_ready.connect(self._on_proposals)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _cancel(self):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.quit()
            self._worker.wait(3000)
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

    # ── Phase 1 ──────────────────────────────

    def _on_intent(self, data: dict):
        self._intent_data = data
        self._tab_json.setPlainText(
            "=== Phase 1: 意图解析 (Intent Analysis) ===\n\n"
            + json.dumps(data, ensure_ascii=False, indent=2))
        self._tabs.setCurrentIndex(3)  # Show JSON Raw so user sees progress
        self._status_lbl.setText("✅ 意图解析完成，正在生成方案...")

    # ── Phase 2 ──────────────────────────────

    def _on_proposals(self, data: dict):
        self._proposals_data = data
        options = data.get("options", [])

        # Render each proposal
        tabs = [self._tab_a, self._tab_b, self._tab_c]
        labels = ["方案 A", "方案 B", "方案 C"]
        for i, tab in enumerate(tabs):
            if i < len(options):
                tab.setMarkdown(self._fmt_proposal_markdown(
                    options[i], labels[i]))
            else:
                tab.setMarkdown(f"*（{labels[i]} 未生成）*")

        # Also show full JSON
        self._tab_json.setPlainText(json.dumps(data, ensure_ascii=False, indent=2))
        self._tabs.setCurrentIndex(0)  # Switch to 方案 A

    def _on_finished(self, success: bool, msg: str):
        self._reset_ui()
        if success:
            self._btn_export.setEnabled(True)
            self._status_lbl.setText(f"✅ {msg}")
        else:
            QMessageBox.critical(self.main_window, "生成失败", msg)

    # ── Markdown Formatting ──────────────────

    def _fmt_proposal_markdown(self, p: dict, label: str) -> str:
        cs = p.get("全局色彩资产", {})
        bg = cs.get("主背景色系", "")
        struct = cs.get("排版结构色", "")
        accent = cs.get("强调点缀色", "")

        def color_swatch(hex_code: str) -> str:
            """Extract HEX and render as inline color block."""
            import re
            m = re.search(r"#[0-9A-Fa-f]{6}", hex_code)
            if not m:
                return hex_code
            h = m.group(0)
            return (
                f'<span style="display:inline-block;width:14px;height:14px;'
                f'background:{h};border-radius:3px;border:1px solid #CCC;'
                f'vertical-align:middle;"></span> {hex_code}'
            )

        layout = p.get("版式语言与排版哲学", {})
        font = layout.get("视觉字体建议", {}) if isinstance(layout, dict) else {}
        product = p.get("产品信息", {})
        notes = p.get("下游执行注意事项", {})

        lines = [
            f"# {label}: {p.get('风格名称', '')}",
            "",
            f"> {p.get('视觉风格与光影', '')}",
            "",
            "---",
            "## 📋 基本信息",
            "",
            f"| 项目 | 内容 |",
            f"|------|------|",
            f"| **目标平台** | {p.get('目标平台', '')} |",
            f"| **任务类型** | {p.get('任务类型', '')} |",
            f"| **期望图片数量** | {p.get('期望图片数量', '')} |",
            f"| **设计风格标签** | {p.get('设计风格标签', '')} |",
            "",
            f"**文案语调指引**: {p.get('文案语调指引', '')}",
            "",
            "---",
            "## 🎨 全局色彩资产",
            "",
            f"- **主背景色系**: {color_swatch(bg)}",
            f"- **排版结构色**: {color_swatch(struct)}",
            f"- **强调点缀色**: {color_swatch(accent)}",
            "",
            "---",
            "## 🌍 美学世界观与核心材质库",
            "",
        ]

        world = p.get("美学世界观与核心材质库", {})
        if isinstance(world, dict):
            lines.append(f"**世界观设定**: {world.get('世界观设定', '')}")
            lines.append("")
            lines.append(f"**可用环境与道具池**: {world.get('可用环境与道具池', '')}")
        lines.append("")

        lines += [
            "---",
            "## 📐 版式语言与排版哲学",
            "",
        ]
        if isinstance(layout, dict):
            lines.append(f"### 信息层级与首屏钩子")
            lines.append(f"{layout.get('信息层级与首屏钩子', '')}")
            lines.append("")
            lines.append(f"### 排版规范与图文关系")
            lines.append(f"{layout.get('排版规范与图文关系', '')}")
            lines.append("")
            if font:
                lines.append("### 视觉字体建议")
                lines.append(f"- **字体气质**: {font.get('字体气质', '')}")
                lines.append(f"- **粗细与层级搭配**: {font.get('粗细与层级搭配', '')}")
                lines.append(f"- **推荐字体色彩**: {font.get('推荐字体色彩', '')}")
        lines.append("")

        lines += [
            "---",
            "## 📦 产品信息",
            "",
            f"| 项目 | 内容 |",
            f"|------|------|",
            f"| **产品名称** | {product.get('产品名称', p.get('产品名称', ''))} |",
            f"| **适用人群** | {product.get('适用人群', '')} |",
            f"| **核心购买动机** | {product.get('核心购买动机', '')} |",
            "",
        ]
        concerns = product.get("主要购买顾虑", [])
        if isinstance(concerns, list):
            for i, c in enumerate(concerns, 1):
                lines.append(f"- **顾虑 {i}**: {c}")
        lines.append("")

        lines += [
            "### 营销心智与卖点池",
            f"{product.get('营销心智与卖点池', '')}",
            "",
            f"**产品参数**: {p.get('产品参数', '未明确')}",
            "",
            "---",
            "## ⚙️ 下游执行注意事项",
            "",
        ]
        if isinstance(notes, dict):
            lines.append(f"**平台适配提醒**: {notes.get('平台适配提醒', '')}")
            lines.append("")
            lines.append(f"**任务类型约束**: {notes.get('任务类型约束', '')}")
            lines.append("")
            lines.append(f"**图组分配建议**: {notes.get('图组分配建议', '')}")
            lines.append("")
            lines.append(f"**产品保真底线**: {notes.get('产品保真底线', '')}")
            lines.append("")
            lines.append(f"**色彩使用规范**: {notes.get('色彩使用规范', '')}")
            lines.append("")
            lines.append(f"**字体使用指引**: {notes.get('字体使用指引', '')}")
            lines.append("")
            lines.append(f"**禁忌提醒**: {notes.get('禁忌提醒', '')}")
        lines.append("")

        lines += [
            "---",
            "## 📝 用户需求原文",
            "",
            f"> {p.get('用户需求原文', '无')}",
            "",
        ]
        return "\n".join(lines)

    # ── Export ────────────────────────────────

    def _export(self):
        if not self._proposals_data:
            return

        path, fmt = QFileDialog.getSaveFileName(
            self.main_window, "导出方案", "",
            "Markdown (*.md);;JSON (*.json)")
        if not path:
            return

        try:
            if path.endswith(".json"):
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(self._proposals_data, f, ensure_ascii=False, indent=2)
            else:
                options = self._proposals_data.get("options", [])
                diagnostic = self._proposals_data.get("_system_diagnostic_log", {})
                lines = [
                    "# 电商套图AI规划方案",
                    "",
                    f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    "",
                    "---",
                    "",
                    "## 系统诊断日志",
                    "",
                ]
                for k, v in diagnostic.items():
                    lines.append(f"**{k}**: {v}")
                lines.append("")
                lines.append("---")
                labels = ["## 方案 A", "## 方案 B", "## 方案 C"]
                for i, opt in enumerate(options):
                    lines.append("")
                    lines.append(labels[i] if i < len(labels) else f"## 方案 {i+1}")
                    lines.append("")
                    lines.append(self._fmt_proposal_markdown(
                        opt, ["方案 A", "方案 B", "方案 C"][i] if i < 3 else f"方案 {i+1}"))
                with open(path, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines))

            self._status_lbl.setText(f"✅ 已导出到: {os.path.basename(path)}")
            QMessageBox.information(self.main_window, "导出成功", f"方案已导出到:\n{path}")
        except Exception as e:
            QMessageBox.critical(self.main_window, "导出失败", str(e))
