"""PPT 大师 —— UI 组件（SlideCard, OutlineConfirmDialog）"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QScrollArea,
    QLabel, QPushButton, QTextEdit, QDialog, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal

_SLIDE_TYPE_META: dict[str, tuple[str, str]] = {
    "cover":  ("封面", "#7C3AED"),
    "content": ("内容", "#2563EB"),
    "ending":  ("结尾", "#D97706"),
}
_SLIDE_STATUS_ICONS: dict[str, str] = {
    "waiting":  "⏳",
    "generating": "🔄",
    "done":     "✅",
    "failed":   "❌",
}


class SlideCard(QFrame):
    """单张幻灯片预览卡片 — 状态 / 页码 / 类型 / 标题"""
    clicked = Signal(str)

    def __init__(self, page_num: int, slide_type: str, title: str,
                 content_preview: str = ""):
        super().__init__()
        self._page_num = page_num
        self._slide_type = slide_type
        self._title = title
        self._svg_path = ""
        self._status = "waiting"

        type_label, type_color = _SLIDE_TYPE_META.get(slide_type, ("内容", "#6B7280"))

        self.setStyleSheet(
            "SlideCard { background: #FAFBFC; border: 1px solid #E5E7EB;"
            " border-radius: 10px; }"
            "SlideCard:hover { border-color: #6366F1; background: #F4F4FF; }")
        self.setFixedHeight(56)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        self._status_lbl = QLabel(_SLIDE_STATUS_ICONS["waiting"])
        self._status_lbl.setFixedWidth(24)
        self._status_lbl.setStyleSheet("font-size: 16px; background: transparent;")
        layout.addWidget(self._status_lbl)

        num_lbl = QLabel(f"{page_num:02d}")
        num_lbl.setFixedWidth(28)
        num_lbl.setStyleSheet(
            "font-size: 14px; font-weight: 700; color: #9CA3AF; background: transparent;")
        layout.addWidget(num_lbl)

        badge = QLabel(type_label)
        badge.setFixedWidth(40)
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet(
            f"font-size: 11px; font-weight: 600; color: white;"
            f" background-color: {type_color}; border-radius: 6px; padding: 2px 6px;")
        layout.addWidget(badge)

        text_col = QVBoxLayout()
        text_col.setSpacing(1)
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            "font-size: 13px; font-weight: 600; color: #1E1E2E; background: transparent;")
        title_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        text_col.addWidget(title_lbl)

        if content_preview:
            preview = content_preview[:60] + ("..." if len(content_preview) > 60 else "")
            cp_lbl = QLabel(preview)
            cp_lbl.setStyleSheet("font-size: 11px; color: #9CA3AF; background: transparent;")
            text_col.addWidget(cp_lbl)

        layout.addLayout(text_col, 1)

    def set_status(self, status: str, svg_path: str = ""):
        self._status = status
        icon = _SLIDE_STATUS_ICONS.get(status, "⏳")
        self._status_lbl.setText(icon)
        if status == "done":
            self._svg_path = svg_path
            self.setCursor(Qt.PointingHandCursor)
            self.setStyleSheet(
                "SlideCard { background: #F0FDF4; border: 1px solid #BBF7D0;"
                " border-radius: 10px; }"
                "SlideCard:hover { border-color: #10B981; background: #DCFCE7; }")
        elif status == "failed":
            self._svg_path = ""
            self.setCursor(Qt.ArrowCursor)
            self.setStyleSheet(
                "SlideCard { background: #FFF1F2; border: 1px solid #FECDD3;"
                " border-radius: 10px; }"
                "SlideCard:hover { border-color: #EF4444; background: #FFE4E6; }")
        elif status == "generating":
            self.setCursor(Qt.ArrowCursor)
            self.setStyleSheet(
                "SlideCard { background: #EFF6FF; border: 1px solid #BFDBFE;"
                " border-radius: 10px; }")

    def mouseReleaseEvent(self, event):
        if self._status == "done" and self._svg_path:
            self.clicked.emit(self._svg_path)
        super().mouseReleaseEvent(event)


class OutlineConfirmDialog:
    """显示大纲确认弹窗。返回 (action, feedback) 元组。
    action: "confirm" | "regenerate" | "cancel"
    feedback: 用户输入的修改建议文本"""

    @staticmethod
    def show(parent: QWidget, outline: dict, project_dir: str = "") -> tuple[str, str]:
        dlg = QDialog(parent)
        dlg.setWindowTitle("确认 PPT 大纲")
        dlg.setMinimumSize(520, 560)
        dlg.resize(560, 680)
        dlg.setStyleSheet(
            "QDialog { background: #FFFFFF; font-family: 'Microsoft YaHei',"
            " 'PingFang SC', sans-serif; }")

        root = QVBoxLayout(dlg)
        root.setContentsMargins(24, 24, 24, 16)
        root.setSpacing(14)

        ppt_title = outline.get("title", "未命名演示文稿")
        subtitle = outline.get("subtitle", "")
        header = QLabel(f"📋  {ppt_title}")
        header.setStyleSheet(
            "font-size: 20px; font-weight: 700; color: #1E1E2E; background: transparent;")
        root.addWidget(header)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setStyleSheet("font-size: 13px; color: #6B7280; background: transparent;")
            root.addWidget(sub)

        slides = outline.get("slides", [])
        stats = QLabel(f"共 {len(slides)} 页幻灯片")
        stats.setStyleSheet(
            "font-size: 13px; color: #6366F1; font-weight: 600; background: transparent;")
        root.addWidget(stats)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            "QScrollArea { border: 1px solid #E5E7EB; border-radius: 10px;"
            " background: #FAFAFA; }")
        scroll_widget = QWidget()
        scroll_widget.setStyleSheet("background: transparent;")
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(12, 12, 12, 12)
        scroll_layout.setSpacing(8)

        for i, slide in enumerate(slides):
            stype = slide.get("type", "content")
            title = slide.get("title", f"Slide {i + 1}")
            content = slide.get("content", [])
            stype_label, stype_color = _SLIDE_TYPE_META.get(stype, ("内容", "#6B7280"))

            row = QFrame()
            row.setStyleSheet(
                f"QFrame {{ background: #FFFFFF; border: 1px solid #ECEDF0;"
                f" border-left: 4px solid {stype_color}; border-radius: 8px; }}")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(12, 10, 12, 10)
            rl.setSpacing(10)

            num = QLabel(f"{i + 1:02d}")
            num.setFixedWidth(28)
            num.setStyleSheet(
                "font-size: 14px; font-weight: 700; color: #9CA3AF; background: transparent;")
            rl.addWidget(num)

            badge = QLabel(stype_label)
            badge.setFixedWidth(40)
            badge.setAlignment(Qt.AlignCenter)
            badge.setStyleSheet(
                f"font-size: 11px; font-weight: 600; color: white;"
                f" background-color: {stype_color}; border-radius: 6px; padding: 2px 6px;")
            rl.addWidget(badge)

            text_col = QVBoxLayout()
            text_col.setSpacing(2)
            t = QLabel(title)
            t.setStyleSheet(
                "font-size: 14px; font-weight: 600; color: #1E1E2E; background: transparent;")
            text_col.addWidget(t)
            if content:
                c_preview = " · ".join(content[:3])
                if len(c_preview) > 100:
                    c_preview = c_preview[:100] + "..."
                c = QLabel(c_preview)
                c.setWordWrap(True)
                c.setStyleSheet("font-size: 12px; color: #6B7280; background: transparent;")
                text_col.addWidget(c)
            rl.addLayout(text_col, 1)

            scroll_layout.addWidget(row)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        root.addWidget(scroll, 1)

        fb_label = QLabel("修改建议（可选）：")
        fb_label.setStyleSheet(
            "font-size: 13px; color: #6B7280; background: transparent; font-weight: 600;")
        root.addWidget(fb_label)
        feedback_input = QTextEdit()
        feedback_input.setPlaceholderText("输入修改建议，例如：增加案例、调整颜色风格、减少文字密度...")
        feedback_input.setMaximumHeight(72)
        feedback_input.setAcceptRichText(False)
        feedback_input.setStyleSheet(
            "QTextEdit { border: 1px solid #D1D5DB; border-radius: 8px;"
            " padding: 8px 12px; font-size: 13px; color: #1E1E2E;"
            " font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif;"
            " background: #FFFFFF; }"
            "QTextEdit:focus { border-color: #6366F1; }")
        root.addWidget(feedback_input)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        cancel_btn = QPushButton("取消生成")
        cancel_btn.setStyleSheet(
            "QPushButton { background: #F3F4F6; border: 1px solid #E5E7EB;"
            " border-radius: 10px; padding: 12px 24px; font-size: 14px;"
            " color: #6B7280; font-weight: 600; }"
            "QPushButton:hover { background: #E5E7EB; color: #1E1E2E; }")
        cancel_btn.setCursor(Qt.PointingHandCursor)

        regen_btn = QPushButton("重新生成大纲")
        regen_btn.setStyleSheet(
            "QPushButton { background: #FEF3C7; border: 1px solid #FCD34D;"
            " border-radius: 10px; padding: 12px 24px; font-size: 14px;"
            " color: #92400E; font-weight: 600; }"
            "QPushButton:hover { background: #FDE68A; }")
        regen_btn.setCursor(Qt.PointingHandCursor)

        confirm_btn = QPushButton("确认并继续生成 →")
        confirm_btn.setStyleSheet(
            "QPushButton { background: #6366F1; border: none;"
            " border-radius: 10px; padding: 12px 28px; font-size: 14px;"
            " color: white; font-weight: 700; }"
            "QPushButton:hover { background: #4F46E5; }")
        confirm_btn.setCursor(Qt.PointingHandCursor)

        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()
        btn_row.addWidget(regen_btn)
        btn_row.addWidget(confirm_btn)
        root.addLayout(btn_row)

        result = {"action": "cancel", "feedback": ""}

        def _on_feedback_changed():
            if feedback_input.toPlainText().strip():
                regen_btn.setText("按建议重新生成")
            else:
                regen_btn.setText("重新生成大纲")

        feedback_input.textChanged.connect(_on_feedback_changed)

        def _do_cancel():
            result["action"] = "cancel"
            result["feedback"] = feedback_input.toPlainText().strip()
            dlg.reject()

        def _do_regen():
            result["action"] = "regenerate"
            result["feedback"] = feedback_input.toPlainText().strip()
            dlg.reject()

        def _do_confirm():
            result["action"] = "confirm"
            result["feedback"] = ""
            dlg.accept()

        cancel_btn.clicked.connect(_do_cancel)
        regen_btn.clicked.connect(_do_regen)
        confirm_btn.clicked.connect(_do_confirm)

        dlg.exec()
        return result["action"], result["feedback"]
