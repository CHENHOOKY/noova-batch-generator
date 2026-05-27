"""PPT 大师 —— 插件主类"""

import os
import subprocess
import sys

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QScrollArea,
    QLabel, QPushButton, QFileDialog, QMessageBox,
    QProgressBar, QTextEdit, QLineEdit, QSpinBox, QSplitter,
)
from PySide6.QtCore import Qt

from plugin_base import BasePlugin
from plugins._design import NoScrollComboBox as QComboBox
from plugins.ppt_master.config import (
    C_PRIMARY, C_PRIMARY_HOVER, C_TEXT, C_TEXT_SUB, C_CARD_BG, C_CARD_BDR,
    C_LOG_BG, C_DANGER, C_SEP,
    DS_BASE_URL, DS_MODELS,
    DESIGN_SCHEMES, INDUSTRY_PALETTES, LAYOUT_TEMPLATES,
    CANVAS_OPTIONS, CANVAS_VIEWBOX,
    _PPT_PROJECTS_DIR,
)
from plugins.ppt_master.worker import PPTGenerateWorker, _check_critical_deps, _install_deps
from plugins.ppt_master.widgets import SlideCard, OutlineConfirmDialog


def _open_file_or_dir(path: str):
    """跨平台文件/目录打开"""
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.run(["open", path])
    else:
        subprocess.run(["xdg-open", path])


class PPTMasterPlugin(BasePlugin):
    """PPT 大师 —— DeepSeek AI 一键生成原生 PPTX"""

    plugin_id = "ppt_master"
    name = "PPT 大师"
    icon = "📊"
    color = "#6366F1"
    description = ("DeepSeek AI 驱动的 PPT 生成工具。\n"
                   "输入主题 → AI 自动生成大纲和幻灯片 → 导出原生 PPTX。")

    def __init__(self):
        super().__init__()
        self._worker: PPTGenerateWorker | None = None
        self._last_output_path = ""

        self._stored_outline: dict | None = None
        self._stored_project_dir: str = ""
        self._stored_worker_params: dict = {}
        self._slide_cards: dict[int, SlideCard] = {}
        self._slide_list_layout: QVBoxLayout | None = None
        self._slide_placeholder: QLabel | None = None
        self._phase: str = ""

        self._model_combo: QComboBox | None = None
        self._api_status_label: QLabel | None = None

        self._prompt_input: QTextEdit | None = None
        self._prompt_count: QLabel | None = None
        self._custom_style_input: QTextEdit | None = None
        self._ref_style_input: QLineEdit | None = None
        self._output_dir_input: QLineEdit | None = None
        self._page_spin: QSpinBox | None = None
        self._canvas_combo: QComboBox | None = None
        self._ref_items_layout: QVBoxLayout | None = None
        self._ref_rows: list[tuple[QLineEdit, QPushButton]] = []
        self._log_area: QTextEdit | None = None
        self._progress_bar: QProgressBar | None = None
        self._start_btn: QPushButton | None = None
        self._cancel_btn: QPushButton | None = None
        self._open_btn: QPushButton | None = None

    # ═══════════════════════════════════════
    #  主工作区
    # ═══════════════════════════════════════

    def create_workspace(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet(
            "background-color: #F9FAFB;"
            "font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif;")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        outer = QVBoxLayout(content)
        outer.setContentsMargins(56, 44, 56, 52)
        outer.setSpacing(0)

        top_bar = QHBoxLayout()
        back_btn = QPushButton("← 返回首页")
        back_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none;"
            " color: " + C_TEXT_SUB + "; font-size: 14px; padding: 6px 0; }"
            "QPushButton:hover { color: " + C_PRIMARY + "; }")
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.clicked.connect(lambda: self.main_window.switch_page(0))
        top_bar.addWidget(back_btn)
        top_bar.addStretch()
        outer.addLayout(top_bar)
        outer.addSpacing(8)

        title = QLabel(self.icon + "  " + self.name)
        title.setStyleSheet(
            "font-size: 28px; font-weight: 700; color: " + C_TEXT
            + "; background: transparent;")
        subtitle = QLabel("输入主题，DeepSeek AI 自动生成大纲和幻灯片 → 导出原生 PPTX")
        subtitle.setStyleSheet(
            "font-size: 14px; color: " + C_TEXT_SUB
            + "; background: transparent; margin-bottom: 2px;")
        outer.addWidget(title)
        outer.addWidget(subtitle)
        outer.addSpacing(20)

        main_row = QHBoxLayout()
        main_row.setSpacing(24)
        main_row.addWidget(self._build_left_panel())
        main_row.addWidget(self._build_right_panel(), 1)
        outer.addLayout(main_row)
        outer.addStretch()

        scroll.setWidget(content)
        wrap = QVBoxLayout(page)
        wrap.setContentsMargins(0, 0, 0, 0)
        wrap.addWidget(scroll)
        return page

    # ═══════════════════════════════════════
    #  左侧面板
    # ═══════════════════════════════════════

    def _build_left_panel(self) -> QFrame:
        card = QFrame()
        card.setFixedWidth(400)
        card.setStyleSheet(
            "QFrame { background-color: " + C_CARD_BG
            + "; border: 1px solid " + C_CARD_BDR
            + "; border-radius: 14px; }")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(0)

        layout.addWidget(self._build_api_section())
        layout.addWidget(self._make_sep())
        layout.addWidget(self._build_prompt_section())
        layout.addWidget(self._make_sep())
        layout.addWidget(self._build_design_section())
        layout.addWidget(self._make_sep())
        layout.addWidget(self._build_output_section())
        layout.addWidget(self._make_sep())
        layout.addWidget(self._build_ref_section())
        layout.addSpacing(16)
        layout.addLayout(self._build_action_row())

        return card

    def _make_sep(self) -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(
            "QFrame { border: none; border-top: 1px solid " + C_SEP
            + "; background: transparent; margin: 14px 0; }")
        sep.setFixedHeight(1)
        return sep

    def _section_header(self, emoji: str, text: str) -> QLabel:
        lbl = QLabel(f"{emoji}  {text}")
        lbl.setStyleSheet(
            "font-size: 14px; font-weight: 700; color: " + C_TEXT
            + "; background: transparent; margin-bottom: 10px;")
        return lbl

    # ── API 设置 ──

    def _build_api_section(self) -> QWidget:
        wrapper = QWidget()
        wrapper.setStyleSheet("background: transparent;")
        wl = QVBoxLayout(wrapper)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setSpacing(8)

        wl.addWidget(self._section_header("⚙️", "API 设置"))

        self._api_status_label = QLabel()
        self._update_api_status()
        self._api_status_label.setStyleSheet(
            "font-size: 13px; background: transparent; padding: 2px 0;")
        wl.addWidget(self._api_status_label)

        mrow = QHBoxLayout()
        mrow.setSpacing(10)
        ml_col = QVBoxLayout()
        ml_col.setSpacing(4)
        ml_lbl = QLabel("模型")
        ml_lbl.setStyleSheet(
            "font-size: 12px; font-weight: 600; color: " + C_TEXT_SUB
            + "; background: transparent;")
        ml_col.addWidget(ml_lbl)
        self._model_combo = QComboBox()
        self._model_combo.addItems(DS_MODELS)
        self._model_combo.setCurrentIndex(0)
        self._combo_style(self._model_combo)
        ml_col.addWidget(self._model_combo)
        mrow.addLayout(ml_col, 1)
        wl.addLayout(mrow)

        return wrapper

    # ── 提示词 ──

    def _build_prompt_section(self) -> QWidget:
        wrapper = QWidget()
        wrapper.setStyleSheet("background: transparent;")
        wl = QVBoxLayout(wrapper)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setSpacing(8)
        wl.addWidget(self._section_header("📝", "提示词"))

        self._prompt_input = QTextEdit()
        self._prompt_input.setPlaceholderText(
            "请输入 PPT 主题...\n\n"
            "例如：请生成一份 2024 年度工作总结报告，包含项目回顾、数据分析、"
            "明年规划三个部分，风格简约商务。")
        self._prompt_input.setMinimumHeight(120)
        self._prompt_input.setMaximumHeight(180)
        self._prompt_input.setStyleSheet(
            "QTextEdit { border: 1px solid #E5E7EB; border-radius: 10px;"
            " padding: 12px 14px; font-size: 14px; background: " + C_LOG_BG
            + "; color: " + C_TEXT + "; line-height: 1.6; }"
            "QTextEdit:focus { border: 1px solid " + C_PRIMARY
            + "; background: " + C_CARD_BG + "; }")
        self._prompt_input.textChanged.connect(self._on_prompt_changed)
        wl.addWidget(self._prompt_input)

        self._prompt_count = QLabel("已输入 0 字")
        self._prompt_count.setStyleSheet(
            "font-size: 11px; color: #9CA3AF; background: transparent; padding: 0 4px;")
        self._prompt_count.setAlignment(Qt.AlignRight)
        wl.addWidget(self._prompt_count)
        return wrapper

    def _on_prompt_changed(self):
        text = self._prompt_input.toPlainText()
        self._prompt_count.setText(f"已输入 {len(text)} 字")

    # ── 设计选项 ──

    def _build_design_section(self) -> QWidget:
        wrapper = QWidget()
        wrapper.setStyleSheet("background: transparent;")
        wl = QVBoxLayout(wrapper)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setSpacing(10)
        wl.addWidget(self._section_header("🎨", "设计选项"))

        cst_lbl = QLabel("自定义风格（描述你想要的视觉风格）")
        cst_lbl.setStyleSheet(
            "font-size: 12px; font-weight: 600; color: " + C_TEXT_SUB
            + "; background: transparent;")
        wl.addWidget(cst_lbl)
        self._custom_style_input = QTextEdit()
        self._custom_style_input.setPlaceholderText(
            "例如：极简商务风、赛博朋克、学术答辩、渐变深色...")
        self._custom_style_input.setMaximumHeight(80)
        self._custom_style_input.setStyleSheet(
            "QTextEdit { border: 1px solid #E5E7EB; border-radius: 10px;"
            " padding: 8px 12px; font-size: 13px; background: " + C_LOG_BG
            + "; color: " + C_TEXT + "; }"
            "QTextEdit:focus { border: 1px solid " + C_PRIMARY
            + "; background: " + C_CARD_BG + "; }")
        wl.addWidget(self._custom_style_input)

        ref_lbl = QLabel("参考样式 PPTX（可选，上传参考 PPT 自动提取配色和字体风格）")
        ref_lbl.setStyleSheet(
            "font-size: 12px; font-weight: 600; color: " + C_TEXT_SUB
            + "; background: transparent;")
        wl.addWidget(ref_lbl)
        ref_row = QHBoxLayout()
        ref_row.setSpacing(8)
        self._ref_style_input = QLineEdit()
        self._ref_style_input.setPlaceholderText("选择参考 PPTX 文件...")
        self._ref_style_input.setReadOnly(True)
        self._input_style(self._ref_style_input)
        ref_row.addWidget(self._ref_style_input, 1)
        ref_btn = QPushButton("选择文件")
        ref_btn.setFixedWidth(75)
        self._small_btn_style(ref_btn)
        ref_btn.clicked.connect(lambda: self._pick_ref_style())
        ref_row.addWidget(ref_btn)
        wl.addLayout(ref_row)

        row = QHBoxLayout()
        row.setSpacing(10)
        pg_col = QVBoxLayout()
        pg_col.setSpacing(4)
        pg_lbl = QLabel("预计页数")
        pg_lbl.setStyleSheet(
            "font-size: 12px; font-weight: 600; color: " + C_TEXT_SUB
            + "; background: transparent;")
        pg_col.addWidget(pg_lbl)
        self._page_spin = QSpinBox()
        self._page_spin.setRange(0, 50)
        self._page_spin.setValue(0)
        self._page_spin.setSpecialValueText("自动")
        self._page_spin.setStyleSheet(
            "QSpinBox { border: 1px solid #E5E7EB; border-radius: 10px;"
            " padding: 10px 12px; font-size: 14px;"
            " background: " + C_CARD_BG + "; }"
            "QSpinBox:focus { border: 1px solid " + C_PRIMARY + "; }")
        pg_col.addWidget(self._page_spin)
        row.addLayout(pg_col, 1)
        cv_col = QVBoxLayout()
        cv_col.setSpacing(4)
        cv_lbl = QLabel("画布格式")
        cv_lbl.setStyleSheet(
            "font-size: 12px; font-weight: 600; color: " + C_TEXT_SUB
            + "; background: transparent;")
        cv_col.addWidget(cv_lbl)
        self._canvas_combo = QComboBox()
        for key, label, _ in CANVAS_OPTIONS:
            self._canvas_combo.addItem(label, key)
        self._canvas_combo.setCurrentIndex(0)
        self._combo_style(self._canvas_combo)
        cv_col.addWidget(self._canvas_combo)
        row.addLayout(cv_col, 2)
        wl.addLayout(row)
        return wrapper

    def _pick_ref_style(self):
        path, _ = QFileDialog.getOpenFileName(
            self._workspace, "选择参考样式 PPTX",
            filter="PPTX Files (*.pptx);;All Files (*)")
        if path and self._ref_style_input:
            self._ref_style_input.setText(path)

    # ── 输出目录 ──

    def _build_output_section(self) -> QWidget:
        wrapper = QWidget()
        wrapper.setStyleSheet("background: transparent;")
        wl = QVBoxLayout(wrapper)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setSpacing(8)
        wl.addWidget(self._section_header("📂", "输出目录"))

        row = QHBoxLayout()
        row.setSpacing(8)
        self._output_dir_input = QLineEdit()
        self._output_dir_input.setText(str(_PPT_PROJECTS_DIR))
        self._input_style(self._output_dir_input)
        row.addWidget(self._output_dir_input, 1)

        pick_btn = QPushButton("选择")
        pick_btn.setFixedWidth(60)
        self._small_btn_style(pick_btn)
        pick_btn.clicked.connect(self._pick_output_dir)
        row.addWidget(pick_btn)
        wl.addLayout(row)

        hint = QLabel("生成的项目将保存在此目录")
        hint.setStyleSheet(
            "font-size: 11px; color: #9CA3AF; background: transparent; padding: 0 4px;")
        wl.addWidget(hint)
        return wrapper

    def _pick_output_dir(self):
        path = QFileDialog.getExistingDirectory(
            self._workspace, "选择输出目录", str(_PPT_PROJECTS_DIR))
        if path:
            self._output_dir_input.setText(path)

    # ── 参考文件 ──

    def _build_ref_section(self) -> QWidget:
        wrapper = QWidget()
        wrapper.setStyleSheet("background: transparent;")
        wl = QVBoxLayout(wrapper)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setSpacing(8)
        wl.addWidget(self._section_header("📎", "参考文件（可选）"))

        hint = QLabel("内容参考: PDF/DOCX/XLSX/TXT/MD/CSV | 图片将自动提取文字 | 样式参考: PPTX/PNG/JPG")
        hint.setStyleSheet(
            "font-size: 11px; color: #9CA3AF; background: transparent; padding: 0 4px;")
        wl.addWidget(hint)

        self._ref_items_layout = QVBoxLayout()
        self._ref_items_layout.setSpacing(6)
        self._add_ref_row()
        wl.addLayout(self._ref_items_layout)

        row = QHBoxLayout()
        row.setSpacing(8)
        add_btn = QPushButton("+ 添加文件")
        self._small_btn_style(add_btn)
        add_btn.clicked.connect(self._add_ref_row)
        row.addWidget(add_btn)
        rm_btn = QPushButton("- 移除")
        self._small_btn_style(rm_btn)
        rm_btn.clicked.connect(self._remove_ref_row)
        row.addWidget(rm_btn)
        row.addStretch()
        wl.addLayout(row)
        return wrapper

    def _add_ref_row(self):
        row = QHBoxLayout()
        row.setSpacing(6)
        inp = QLineEdit()
        inp.setPlaceholderText("PDF / DOCX / XLSX / TXT / MD / PPTX / PNG / JPG 等文件路径")
        self._input_style(inp)
        row.addWidget(inp, 1)
        btn = QPushButton("选择文件")
        btn.setFixedWidth(75)
        self._small_btn_style(btn)
        btn.clicked.connect(lambda: self._pick_ref_file(inp))
        row.addWidget(btn)
        self._ref_items_layout.addLayout(row)
        self._ref_rows.append((inp, btn))

    def _remove_ref_row(self):
        if len(self._ref_rows) <= 1:
            return
        item = self._ref_items_layout.takeAt(self._ref_items_layout.count() - 1)
        if item:
            self._clear_layout(item)
        if self._ref_rows:
            self._ref_rows.pop()

    def _pick_ref_file(self, inp: QLineEdit):
        path, _ = QFileDialog.getOpenFileName(
            self._workspace, "选择参考文件",
            filter="All Supported (*.pdf *.docx *.pptx *.xlsx *.xlsm *.txt *.md *.csv *.png *.jpg *.jpeg *.webp *.bmp);;Documents (*.pdf *.docx *.pptx *.xlsx *.xlsm *.txt *.md *.csv);;Style Reference (*.pptx *.png *.jpg *.jpeg *.webp *.bmp);;All Files (*)")
        if path:
            inp.setText(path)

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())

    # ── 操作区 ──

    def _build_action_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)
        self._start_btn = QPushButton("🚀 生成 PPT")
        self._start_btn.setStyleSheet(
            "QPushButton { background-color: " + C_PRIMARY
            + "; color: white; border: none;"
            " border-radius: 10px; padding: 13px 24px;"
            " font-size: 15px; font-weight: 700; }"
            "QPushButton:hover { background-color: " + C_PRIMARY_HOVER + "; }"
            "QPushButton:disabled { background-color: #D1D5DB; }")
        self._start_btn.setCursor(Qt.PointingHandCursor)
        self._start_btn.clicked.connect(self._start_generate)
        row.addWidget(self._start_btn, 1)

        self._cancel_btn = QPushButton("⏹ 终止")
        self._cancel_btn.setStyleSheet(
            "QPushButton { background-color: #FEE2E2; color: " + C_DANGER
            + "; border: 1px solid #FECACA; border-radius: 10px;"
            " padding: 13px 18px; font-size: 14px; font-weight: 600; }"
            "QPushButton:hover { background-color: #FECACA; }")
        self._cancel_btn.setCursor(Qt.PointingHandCursor)
        self._cancel_btn.clicked.connect(self._cancel_generate)
        self._cancel_btn.setVisible(False)
        row.addWidget(self._cancel_btn)
        return row

    # ═══════════════════════════════════════
    #  右侧日志面板
    # ═══════════════════════════════════════

    def _build_right_panel(self) -> QFrame:
        panel = QFrame()
        panel.setStyleSheet(
            "QFrame { background-color: " + C_CARD_BG
            + "; border: 1px solid " + C_CARD_BDR
            + "; border-radius: 14px; }")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        header_row = QHBoxLayout()
        header_lbl = QLabel("📋 生成预览")
        header_lbl.setStyleSheet(
            "font-size: 16px; font-weight: 700; color: " + C_TEXT
            + "; background: transparent;")
        header_row.addWidget(header_lbl)
        header_row.addStretch()
        self._open_btn = QPushButton("📂 打开输出目录")
        self._open_btn.setStyleSheet(
            "QPushButton { background: #F3F4F6; border: 1px solid #E5E7EB;"
            " border-radius: 8px; padding: 8px 14px; font-size: 12px; color: #333; }"
            "QPushButton:hover { background: #E5E7EB; }")
        self._open_btn.setCursor(Qt.PointingHandCursor)
        self._open_btn.clicked.connect(self._open_output)
        self._open_btn.setVisible(False)
        header_row.addWidget(self._open_btn)
        layout.addLayout(header_row)

        splitter = QSplitter(Qt.Vertical)
        splitter.setStyleSheet("QSplitter::handle { background: #E5E7EB; height: 2px; }")

        slide_panel = QFrame()
        slide_panel.setStyleSheet(
            "QFrame { background: #FAFBFC; border: 1px solid #ECEDF0; border-radius: 10px; }")
        sp_layout = QVBoxLayout(slide_panel)
        sp_layout.setContentsMargins(12, 10, 12, 10)
        sp_layout.setSpacing(6)

        slide_header = QLabel("幻灯片预览")
        slide_header.setStyleSheet(
            "font-size: 13px; font-weight: 700; color: #6B7280; background: transparent;")
        sp_layout.addWidget(slide_header)

        slide_scroll = QScrollArea()
        slide_scroll.setWidgetResizable(True)
        slide_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        slide_list_widget = QWidget()
        slide_list_widget.setStyleSheet("background: transparent;")
        self._slide_list_layout = QVBoxLayout(slide_list_widget)
        self._slide_list_layout.setContentsMargins(0, 0, 0, 0)
        self._slide_list_layout.setSpacing(6)

        self._slide_placeholder = QLabel(
            "点击「生成 PPT」开始\n生成后在此预览每页幻灯片")
        self._slide_placeholder.setAlignment(Qt.AlignCenter)
        self._slide_placeholder.setStyleSheet(
            "font-size: 13px; color: #9CA3AF; background: transparent; padding: 40px 0;")
        self._slide_list_layout.addWidget(self._slide_placeholder)
        self._slide_list_layout.addStretch()

        slide_scroll.setWidget(slide_list_widget)
        sp_layout.addWidget(slide_scroll, 1)
        splitter.addWidget(slide_panel)

        log_panel = QFrame()
        log_panel.setStyleSheet(
            "QFrame { background: #FAFBFC; border: 1px solid #ECEDF0; border-radius: 10px; }")
        lp_layout = QVBoxLayout(log_panel)
        lp_layout.setContentsMargins(12, 10, 12, 10)
        lp_layout.setSpacing(6)

        log_sub_header = QLabel("生成日志")
        log_sub_header.setStyleSheet(
            "font-size: 13px; font-weight: 700; color: #6B7280; background: transparent;")
        lp_layout.addWidget(log_sub_header)

        self._log_area = QTextEdit()
        self._log_area.setReadOnly(True)
        self._log_area.setStyleSheet(
            "QTextEdit { border: 1px solid #E5E7EB; border-radius: 8px; padding: 10px;"
            " background-color: " + C_LOG_BG
            + "; font-size: 12px; color: " + C_TEXT
            + "; font-family: 'Consolas', 'Courier New', monospace; }")
        lp_layout.addWidget(self._log_area, 1)
        splitter.addWidget(log_panel)

        total_h = 600
        splitter.setSizes([int(total_h * 0.55), int(total_h * 0.45)])
        layout.addWidget(splitter, 1)

        self._progress_bar = QProgressBar()
        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(False)
        self._progress_bar.setStyleSheet(
            "QProgressBar { border: none; background-color: #EEEEF2;"
            " border-radius: 6px; height: 10px; }"
            "QProgressBar::chunk { background-color: " + C_PRIMARY
            + "; border-radius: 6px; }")
        layout.addWidget(self._progress_bar)

        return panel

    # ═══════════════════════════════════════
    #  样式快捷方法
    # ═══════════════════════════════════════

    def _input_style(self, w: QLineEdit):
        w.setStyleSheet(
            "QLineEdit { border: 1px solid #E5E7EB; border-radius: 10px;"
            " padding: 10px 14px; font-size: 14px; background: " + C_LOG_BG
            + "; color: " + C_TEXT + "; }"
            "QLineEdit:focus { border: 1px solid " + C_PRIMARY
            + "; background: " + C_CARD_BG + "; }")

    def _combo_style(self, w: QComboBox):
        w.setStyleSheet(
            "QComboBox { padding: 10px 12px; border: 1px solid #E5E7EB;"
            " border-radius: 10px; font-size: 14px;"
            " background-color: " + C_CARD_BG + "; }"
            "QComboBox:focus { border: 1px solid " + C_PRIMARY + "; }"
            "QComboBox:hover { border: 1px solid #D1D5DB; }"
            "QComboBox::drop-down { border: none; }"
            "QComboBox QAbstractItemView { border: 1px solid " + C_CARD_BDR
            + "; border-radius: 8px; padding: 4px;"
            " selection-background-color: #F4F4FF; }")

    def _small_btn_style(self, w: QPushButton):
        w.setStyleSheet(
            "QPushButton { background-color: #F3F4F6;"
            " border: 1px solid #E5E7EB; border-radius: 8px;"
            " padding: 7px 12px; color: #555; font-size: 13px; }"
            "QPushButton:hover { background-color: #E5E7EB; }")
        w.setCursor(Qt.PointingHandCursor)

    def _update_api_status(self):
        if self.main_window and self.main_window.settings_manager.has_text_key():
            self._api_status_label.setText("✅ API Key 已配置（来自全局设置）")
            self._api_status_label.setStyleSheet(
                "font-size: 13px; color: #10B981; background: transparent; padding: 2px 0;")
        else:
            self._api_status_label.setText("⚠️ 未配置 API Key，请点击侧边栏 ⚙️ 设置进行配置")
            self._api_status_label.setStyleSheet(
                "font-size: 13px; color: #F59E0B; background: transparent; padding: 2px 0;")

    def on_activate(self):
        self._update_api_status()

    # ═══════════════════════════════════════
    #  操作逻辑
    # ═══════════════════════════════════════

    def _start_generate(self, revision_notes: str = "", previous_outline: dict = None):
        api_key = self.main_window.settings_manager.get_text_key()
        if not api_key:
            QMessageBox.warning(
                self._workspace, "提示",
                "未配置文本模型 API Key！请点击侧边栏 ⚙️ 设置进行配置")
            return

        prompt = self._prompt_input.toPlainText().strip()
        if not prompt:
            QMessageBox.warning(self._workspace, "提示", "请输入 PPT 主题/提示词")
            return

        missing = _check_critical_deps()
        if missing:
            reply = QMessageBox.question(
                self._workspace, "缺少依赖",
                f"需要安装以下依赖包才能生成 PPTX:\n"
                f"  {', '.join(missing)}\n\n"
                f"是否自动安装？",
                QMessageBox.Yes | QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
            self._log_append("正在安装依赖...")
            ok = _install_deps(log_fn=self._log_append)
            if not ok:
                QMessageBox.critical(
                    self._workspace, "安装失败",
                    "依赖安装失败，请手动运行:\n"
                    f"pip install {' '.join(missing)}")
                return
            self._log_append("[OK] 依赖安装完成\n")

        base_url = self.main_window.settings_manager.get_text_base_url()
        model = self._model_combo.currentText().strip()
        if not model:
            model = DS_MODELS[0]
        page_count = self._page_spin.value()
        canvas_key = self._canvas_combo.currentData()
        viewbox = CANVAS_VIEWBOX.get(canvas_key, "0 0 1280 720")

        scheme = DESIGN_SCHEMES[1]
        industry = INDUSTRY_PALETTES[0]
        layout = LAYOUT_TEMPLATES[0]
        custom_style = self._custom_style_input.toPlainText().strip()

        output_dir = self._output_dir_input.text().strip()
        if not output_dir:
            output_dir = str(_PPT_PROJECTS_DIR)

        file_paths = []
        if self._ref_style_input:
            ref_style = self._ref_style_input.text().strip()
            if ref_style and os.path.isfile(ref_style):
                file_paths.append(ref_style)
        for inp, _ in self._ref_rows:
            t = inp.text().strip()
            if t and os.path.isfile(t):
                file_paths.append(t)

        self._stored_worker_params = {
            "api_key": api_key, "base_url": base_url, "model": model,
            "prompt": prompt, "page_count": page_count,
            "canvas_key": canvas_key, "viewbox": viewbox,
            "output_dir": output_dir,
            "scheme": scheme, "industry": industry, "layout": layout,
            "custom_style": custom_style,
            "file_paths": file_paths,
            "revision_notes": revision_notes,
            "previous_outline": previous_outline,
        }

        self._start_btn.setVisible(False)
        self._cancel_btn.setVisible(True)
        self._progress_bar.setVisible(True)
        self._progress_bar.setValue(0)
        self._open_btn.setVisible(False)
        self._log_area.clear()
        self._clear_slide_list()

        self._disconnect_worker()
        self._connect_monitor()
        self._phase = "outline"
        self._worker = PPTGenerateWorker(
            api_key, base_url, model, prompt,
            page_count, canvas_key, viewbox,
            output_dir,
            scheme, industry, layout,
            custom_style,
            file_paths,
            phase="outline",
            revision_notes=revision_notes,
            previous_outline=previous_outline)
        self._worker.log_msg.connect(self._log_append)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.outline_ready.connect(self._on_outline_ready)
        self._worker.start()

    def stop(self):
        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(100)

    def _cancel_generate(self):
        self.stop()
        self._disconnect_monitor()
        self._phase = ""
        self._stored_outline = None
        self._stored_project_dir = ""
        self._reset_ui()

    def _disconnect_worker(self):
        if self._worker is None:
            return
        for sig in [self._worker.log_msg, self._worker.progress,
                     self._worker.finished, self._worker.outline_ready,
                     self._worker.slide_started, self._worker.slide_completed]:
            try:
                sig.disconnect()
            except (TypeError, RuntimeError):
                pass
        self._worker = None

    def _log_append(self, text: str):
        self._log_area.append(text)
        sb = self._log_area.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_progress(self, current: int, total: int, stage: str):
        self._progress_bar.setMaximum(total)
        self._progress_bar.setValue(current)
        self._progress_bar.setFormat(
            f"{stage}  %v/%m" if total > 0 else stage)

    def _on_finished(self, success: bool, output_path: str):
        self._disconnect_monitor()
        if self._phase == "outline":
            if not success:
                self._reset_ui()
                self._phase = ""
            return
        if self._phase == "svg_export":
            self._reset_ui()
            self._phase = ""
            self._stored_outline = None
            self._stored_project_dir = ""
            if success and output_path:
                self._open_btn.setVisible(True)
                self._last_output_path = output_path
            return

    def _connect_monitor(self):
        mw = self.main_window
        if mw:
            try:
                mw.stop_requested.connect(self._cancel_generate)
            except (TypeError, RuntimeError):
                pass

    def _disconnect_monitor(self):
        mw = self.main_window
        if mw:
            try:
                mw.stop_requested.disconnect(self._cancel_generate)
            except (TypeError, RuntimeError):
                pass

    def _reset_ui(self):
        self._start_btn.setVisible(True)
        self._cancel_btn.setVisible(False)
        self._progress_bar.setVisible(False)

    def _open_output(self):
        if self._last_output_path and os.path.exists(self._last_output_path):
            _open_file_or_dir(os.path.dirname(self._last_output_path))

    # ═══════════════════════════════════════
    #  两阶段流程
    # ═══════════════════════════════════════

    def _clear_slide_list(self):
        self._slide_cards.clear()
        if self._slide_list_layout:
            while self._slide_list_layout.count():
                item = self._slide_list_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            self._slide_placeholder = QLabel("生成大纲后将在此预览每页幻灯片")
            self._slide_placeholder.setAlignment(Qt.AlignCenter)
            self._slide_placeholder.setStyleSheet(
                "font-size: 13px; color: #9CA3AF; background: transparent; padding: 40px 0;")
            self._slide_list_layout.addWidget(self._slide_placeholder)
            self._slide_list_layout.addStretch()

    def _populate_slide_list(self, outline: dict):
        self._clear_slide_list()
        slides = outline.get("slides", [])
        for i, slide in enumerate(slides):
            page_num = i + 1
            stype = slide.get("type", "content")
            title = slide.get("title", f"Slide {page_num}")
            content = slide.get("content", [])
            preview = content[0] if content else ""
            card = SlideCard(page_num, stype, title, preview)
            card.clicked.connect(self._open_svg)
            self._slide_cards[page_num] = card
            self._slide_list_layout.addWidget(card)
        self._slide_list_layout.addStretch()

    def _open_svg(self, svg_path: str):
        if svg_path and os.path.isfile(svg_path):
            _open_file_or_dir(svg_path)

    def _on_outline_ready(self, outline: dict, project_dir: str):
        if self._phase != "outline":
            return
        self._stored_outline = outline
        self._stored_project_dir = project_dir

        self._populate_slide_list(outline)

        action, revision_notes = OutlineConfirmDialog.show(self._workspace, outline, project_dir)

        if action == "confirm":
            self._start_phase2()
        elif action == "regenerate":
            prev_outline = self._stored_outline
            self._stored_outline = None
            self._stored_project_dir = ""
            self._clear_slide_list()
            self._start_generate(revision_notes=revision_notes, previous_outline=prev_outline)
        else:
            self._phase = ""
            self._stored_outline = None
            self._stored_project_dir = ""
            self._clear_slide_list()
            self._reset_ui()

    def _start_phase2(self):
        self._phase = "svg_export"
        self._start_btn.setVisible(False)
        self._cancel_btn.setVisible(True)
        self._progress_bar.setVisible(True)
        self._progress_bar.setValue(0)
        self._open_btn.setVisible(False)
        self._disconnect_worker()
        self._connect_monitor()
        params = self._stored_worker_params
        self._worker = PPTGenerateWorker(
            params["api_key"], params["base_url"], params["model"],
            params["prompt"], params["page_count"],
            params["canvas_key"], params["viewbox"],
            params["output_dir"],
            params["scheme"], params["industry"], params["layout"],
            params["custom_style"],
            params["file_paths"],
            phase="svg_export",
            outline=self._stored_outline,
            project_dir=self._stored_project_dir,
            revision_notes="",
            previous_outline=None)
        self._worker.log_msg.connect(self._log_append)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.slide_started.connect(self._on_slide_started)
        self._worker.slide_completed.connect(self._on_slide_completed)
        self._worker.start()

    def _on_slide_started(self, page_num: int, title: str, slide_type: str):
        card = self._slide_cards.get(page_num)
        if card:
            card.set_status("generating")

    def _on_slide_completed(self, page_num: int, title: str,
                            svg_path: str, success: bool):
        card = self._slide_cards.get(page_num)
        if card:
            if success:
                card.set_status("done", svg_path)
            else:
                card.set_status("failed")
