"""设置对话框 — 集中管理视觉/文本 API Key"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QComboBox, QWidget, QScrollArea,
)
from PySide6.QtCore import Qt

from plugins._design import (
    C_BG, C_PRIMARY, C_TEXT, C_TEXT_SUB, C_CARD_BG, C_CARD_BDR,
    INPUT_STYLE, COMBO_STYLE,
)
from config.settings_manager import SettingsManager


class SettingsDialog(QDialog):
    def __init__(self, settings_manager: SettingsManager, parent=None):
        super().__init__(parent)
        self._sm = settings_manager
        self.setWindowTitle("设置")
        self.setMinimumSize(560, 520)
        self.resize(580, 580)
        self.setStyleSheet(f"QDialog {{ background-color: {C_BG}; }}")
        self._build_ui()
        self._load_current()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content = QWidget()
        content.setStyleSheet(f"background: {C_BG};")
        lo = QVBoxLayout(content)
        lo.setContentsMargins(32, 24, 32, 24)
        lo.setSpacing(14)

        # 标题
        title = QLabel("⚙️ 全局设置")
        title.setStyleSheet(
            f"font-size: 20px; font-weight: 700; color: {C_TEXT};"
            f" padding: 0 0 4px 0; background: transparent;")
        lo.addWidget(title)

        # ── 视觉模型 API ──
        lo.addWidget(self._section_header("视觉模型 API（批量出图 / 图片生成）"))
        lo.addWidget(self._build_vis_section())

        lo.addSpacing(8)

        # ── 文本模型 API ──
        lo.addWidget(self._section_header("文本模型 API（PPT / 脚本 / 文案生成）"))
        lo.addWidget(self._build_text_section())

        lo.addSpacing(16)

        # ── 按钮行 ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_row.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.setStyleSheet(self._btn_style(False))
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("保存")
        save_btn.setStyleSheet(self._btn_style(True))
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(save_btn)

        lo.addLayout(btn_row)

        scroll.setWidget(content)
        root.addWidget(scroll)

    # ── 视觉 API 区域 ──────────────────────────

    def _build_vis_section(self) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background: {C_CARD_BG}; border: 1px solid {C_CARD_BDR};"
            f" border-radius: 14px; }}")
        lo = QVBoxLayout(card)
        lo.setContentsMargins(20, 16, 20, 16)
        lo.setSpacing(10)

        url_lbl = QLabel("Base URL: https://noova.cn")
        url_lbl.setStyleSheet(
            f"font-size: 12px; color: {C_TEXT_SUB}; background: transparent;")
        lo.addWidget(url_lbl)

        key_lbl = QLabel("API Key")
        key_lbl.setStyleSheet(
            f"font-size: 13px; font-weight: 600; color: {C_TEXT}; background: transparent;")
        lo.addWidget(key_lbl)

        self._vis_key_input = QLineEdit()
        self._vis_key_input.setPlaceholderText("输入 Noova API Key（sk-...）")
        self._vis_key_input.setEchoMode(QLineEdit.Password)
        self._vis_key_input.setStyleSheet(INPUT_STYLE)
        self._vis_key_input.setMinimumHeight(38)
        lo.addWidget(self._vis_key_input)

        lo.addWidget(self._key_hint("用于批量出图、绘本魔法师等图片生成插件"))

        model_lbl = QLabel("可用模型")
        model_lbl.setStyleSheet(
            f"font-size: 13px; font-weight: 600; color: {C_TEXT}; background: transparent;")
        lo.addWidget(model_lbl)

        self._vis_model_combo = QComboBox()
        self._vis_model_combo.addItems(self._sm.visual_models)
        self._vis_model_combo.setStyleSheet(COMBO_STYLE)
        lo.addWidget(self._vis_model_combo)

        return card

    # ── 文本 API 区域 ──────────────────────────

    def _build_text_section(self) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background: {C_CARD_BG}; border: 1px solid {C_CARD_BDR};"
            f" border-radius: 14px; }}")
        lo = QVBoxLayout(card)
        lo.setContentsMargins(20, 16, 20, 16)
        lo.setSpacing(10)

        url_lbl = QLabel("Base URL: https://apic.dpdns.org")
        url_lbl.setStyleSheet(
            f"font-size: 12px; color: {C_TEXT_SUB}; background: transparent;")
        lo.addWidget(url_lbl)

        key_lbl = QLabel("API Key")
        key_lbl.setStyleSheet(
            f"font-size: 13px; font-weight: 600; color: {C_TEXT}; background: transparent;")
        lo.addWidget(key_lbl)

        self._txt_key_input = QLineEdit()
        self._txt_key_input.setPlaceholderText("输入文本 API Key（sk-...）")
        self._txt_key_input.setEchoMode(QLineEdit.Password)
        self._txt_key_input.setStyleSheet(INPUT_STYLE)
        self._txt_key_input.setMinimumHeight(38)
        lo.addWidget(self._txt_key_input)

        lo.addWidget(self._key_hint("用于 PPT 策略师、分镜生成、电商规划师等文本生成插件"))

        model_lbl = QLabel("可用模型")
        model_lbl.setStyleSheet(
            f"font-size: 13px; font-weight: 600; color: {C_TEXT}; background: transparent;")
        lo.addWidget(model_lbl)

        self._txt_model_combo = QComboBox()
        self._txt_model_combo.addItems(self._sm.text_models)
        self._txt_model_combo.setStyleSheet(COMBO_STYLE)
        lo.addWidget(self._txt_model_combo)

        return card

    # ── 辅助 ──────────────────────────────────

    def _section_header(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"font-size: 14px; font-weight: 600; color: {C_PRIMARY};"
            f" padding: 2px 0 0 0; background: transparent;")
        return lbl

    def _key_hint(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(
            f"font-size: 11px; color: {C_TEXT_SUB}; background: transparent;"
            f" padding: 0 0 0 2px; font-style: italic;")
        return lbl

    def _btn_style(self, primary: bool) -> str:
        if primary:
            return (
                f"QPushButton {{ background-color: {C_PRIMARY}; color: #FFFFFF;"
                f" border: none; border-radius: 10px; padding: 10px 28px;"
                f" font-size: 14px; font-weight: 600; }}"
                f"QPushButton:hover {{ background-color: #5558E6; }}"
            )
        return (
            f"QPushButton {{ background-color: #F3F4F6; color: {C_TEXT};"
            f" border: 1px solid #E5E7EB; border-radius: 10px; padding: 10px 28px;"
            f" font-size: 14px; }}"
            f"QPushButton:hover {{ background-color: #E5E7EB; }}"
        )

    # ── 数据 ──────────────────────────────────

    def _load_current(self):
        self._vis_key_input.setText(self._sm.get_visual_key())
        self._txt_key_input.setText(self._sm.get_text_key())

    def _on_save(self):
        self._sm.set_visual_key(self._vis_key_input.text().strip())
        self._sm.set_text_key(self._txt_key_input.text().strip())
        self._sm.save()
        self.accept()
