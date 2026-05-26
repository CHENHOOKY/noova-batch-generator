"""分镜脚本生成器 —— UI 组件（AssetGridItem, EpisodeNavBar, StoryboardEpisodeView, PromptReviewDialog, RegenerateDialog）"""

import os
import shutil
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QMenu,
    QFrame, QScrollArea, QLabel, QPushButton, QTextEdit,
    QDialog, QCheckBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QSizePolicy, QApplication, QFileDialog, QMessageBox,
)
from PySide6.QtCore import Qt, Signal, QThread, QPoint
from PySide6.QtGui import QPixmap

from plugins._noova_api import NoovaAPI, MODEL_CONFIG
from plugins._design import NoScrollComboBox as QComboBox, COMBO_STYLE, INPUT_STYLE
from plugins.storyboard_generator.config import (
    DEFAULT_IMAGE_MODEL, DEFAULT_IMAGE_SIZE, DEFAULT_ASPECT_RATIO,
)

_ASSET_TYPE_LABELS: dict[str, str] = {
    "character": "角色",
    "scene": "场景",
    "prop": "道具",
}
_ASSET_TYPE_COLORS: dict[str, str] = {
    "character": "#8B5CF6",
    "scene": "#10B981",
    "prop": "#F59E0B",
}


class AssetGridItem(QFrame):
    """单张素材图片的预览卡片"""

    clicked = Signal(str, str)  # (asset_id, filepath)

    def __init__(self, asset_id: str, asset_name: str,
                 asset_type: str, view_label: str = "", prompt: str = "", parent=None):
        super().__init__(parent)
        self._asset_id = asset_id
        self._asset_type = asset_type
        self._prompt = prompt
        self._filepath = ""
        self._status = "waiting"

        type_label = _ASSET_TYPE_LABELS.get(asset_type, "")
        type_color = _ASSET_TYPE_COLORS.get(asset_type, "#6B7280")

        self.setFixedSize(160, 180)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self.setStyleSheet(
            "AssetGridItem { background: #FAFBFC; border: 1px solid #E5E7EB;"
            " border-radius: 10px; }"
            "AssetGridItem:hover { border-color: #6366F1; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Image area
        self._img_lbl = QLabel()
        self._img_lbl.setFixedSize(144, 100)
        self._img_lbl.setAlignment(Qt.AlignCenter)
        self._img_lbl.setStyleSheet(
            "background: #F3F4F6; border-radius: 8px;"
            "font-size: 28px; color: #D1D5DB;")
        self._img_lbl.setText("⏳" if asset_type == "character" else
                              "🏠" if asset_type == "scene" else "📦")
        layout.addWidget(self._img_lbl, 0, Qt.AlignCenter)

        # Type badge + ID
        badge_row = QHBoxLayout()
        badge_row.setSpacing(4)
        badge = QLabel(type_label)
        badge.setStyleSheet(
            f"font-size: 10px; font-weight: 700; color: white;"
            f" background: {type_color}; border-radius: 4px; padding: 1px 6px;")
        badge.setFixedHeight(18)
        badge_row.addWidget(badge)

        id_lbl = QLabel(asset_id.split("_")[0] if "_" in asset_id else asset_id)
        id_lbl.setStyleSheet(
            "font-size: 11px; font-weight: 700; color: #374151; background: transparent;")
        badge_row.addWidget(id_lbl)
        badge_row.addStretch()
        layout.addLayout(badge_row)

        # Name
        name_lbl = QLabel(asset_name)
        name_lbl.setWordWrap(True)
        name_lbl.setStyleSheet(
            "font-size: 12px; font-weight: 600; color: #1E1E2E; background: transparent;")
        name_lbl.setMaximumHeight(30)
        layout.addWidget(name_lbl)

        if view_label:
            v = QLabel(view_label)
            v.setStyleSheet(
                "font-size: 10px; color: #9CA3AF; background: transparent;")
            layout.addWidget(v)

    def _on_context_menu(self, pos: QPoint):
        if self._status != "done" or not self._filepath:
            return
        menu = QMenu(self)
        download_action = menu.addAction("📥 下载图片")
        action = menu.exec_(self.mapToGlobal(pos))
        if action == download_action:
            self._download()

    def _download(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "保存图片", self._filepath.split("/")[-1].split("\\")[-1],
            "PNG (*.png);;JPEG (*.jpg *.jpeg);;所有文件 (*)")
        if path:
            try:
                shutil.copy2(self._filepath, path)
            except Exception as e:
                QMessageBox.critical(self, "错误", f"下载失败: {e}")

    def set_prompt(self, prompt: str):
        self._prompt = prompt

    def set_status(self, status: str, filepath: str = ""):
        self._status = status
        self._filepath = filepath
        if status == "done" and filepath:
            pix = QPixmap(filepath)
            if not pix.isNull():
                self._img_lbl.setPixmap(pix.scaled(
                    144, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self.setCursor(Qt.PointingHandCursor)
            self.setStyleSheet(
                "AssetGridItem { background: #F0FDF4; border: 1px solid #BBF7D0;"
                " border-radius: 10px; }"
                "AssetGridItem:hover { border-color: #10B981; }")
            self._img_lbl.setText("")
        elif status == "generating":
            self._img_lbl.setText("🔄")
            self.setStyleSheet(
                "AssetGridItem { background: #EFF6FF; border: 1px solid #BFDBFE;"
                " border-radius: 10px; }")
        elif status == "failed":
            self._img_lbl.setText("❌")
            self.setStyleSheet(
                "AssetGridItem { background: #FFF1F2; border: 1px solid #FECDD3;"
                " border-radius: 10px; }")

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self._status == "done" and self._filepath:
                self.clicked.emit(self._asset_id, self._filepath)
        super().mouseReleaseEvent(event)


class EpisodeNavBar(QWidget):
    """分集导航按钮栏"""
    episode_selected = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._buttons: list[QPushButton] = []
        self._active_idx = -1
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self._btn_layout = layout
        layout.addStretch()

    def set_episodes(self, count: int):
        for btn in self._buttons:
            btn.deleteLater()
        self._buttons.clear()
        self._active_idx = -1

        base_style = (
            "QPushButton { background: #F3F4F6; border: 1px solid #E5E7EB;"
            " border-radius: 8px; padding: 8px 16px; font-size: 13px;"
            " color: #6B7280; font-weight: 600; }"
            "QPushButton:hover { background: #E5E7EB; color: #1E1E2E; }"
        )
        active_style = (
            "QPushButton { background: #6366F1; border: none;"
            " border-radius: 8px; padding: 8px 16px; font-size: 13px;"
            " color: white; font-weight: 700; }"
        )

        for i in range(count):
            btn = QPushButton(f"E{i + 1:02d}")
            btn.setStyleSheet(base_style)
            btn.setCursor(Qt.PointingHandCursor)

            def make_slot(idx):
                return lambda: self._select(idx)
            btn.clicked.connect(make_slot(i))
            self._buttons.append(btn)
            self._btn_layout.insertWidget(self._btn_layout.count() - 1, btn)

        if count > 0:
            self._select(0)
            self._buttons[0].setStyleSheet(active_style)
            self._active_idx = 0

    def _select(self, idx: int):
        if idx == self._active_idx:
            return
        base_style = (
            "QPushButton { background: #F3F4F6; border: 1px solid #E5E7EB;"
            " border-radius: 8px; padding: 8px 16px; font-size: 13px;"
            " color: #6B7280; font-weight: 600; }"
            "QPushButton:hover { background: #E5E7EB; color: #1E1E2E; }"
        )
        active_style = (
            "QPushButton { background: #6366F1; border: none;"
            " border-radius: 8px; padding: 8px 16px; font-size: 13px;"
            " color: white; font-weight: 700; }"
        )
        if self._active_idx >= 0 and self._active_idx < len(self._buttons):
            self._buttons[self._active_idx].setStyleSheet(base_style)
        self._active_idx = idx
        self._buttons[idx].setStyleSheet(active_style)
        self.episode_selected.emit(idx + 1)


class StoryboardEpisodeView(QWidget):
    """单集分镜脚本完整展示"""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: #FFFFFF; }")

        content = QWidget()
        content.setStyleSheet("background: #FFFFFF;")
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(20, 16, 20, 16)
        self._content_layout.setSpacing(16)
        self._content_layout.addStretch()

        scroll.setWidget(content)
        layout.addWidget(scroll)

    def load_storyboard(self, sb_data: dict, ep_title: str = ""):
        # Clear existing content (except stretch)
        while self._content_layout.count() > 1:
            item = self._content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Title
        title = QLabel(sb_data.get("title", ep_title))
        title.setStyleSheet(
            "font-size: 18px; font-weight: 700; color: #1E1E2E; background: transparent;")
        title.setWordWrap(True)
        self._content_layout.insertWidget(self._content_layout.count() - 1, title)

        # Asset slot table
        slots = sb_data.get("asset_slots", [])
        if slots:
            slot_section = QLabel("📎 素材槽位分配")
            slot_section.setStyleSheet(
                "font-size: 14px; font-weight: 700; color: #6366F1;"
                " background: transparent; margin-top: 8px;")
            self._content_layout.insertWidget(
                self._content_layout.count() - 1, slot_section)

            table = QTableWidget(len(slots), 3)
            table.setHorizontalHeaderLabels(["插槽", "资产", "用途"])
            table.horizontalHeader().setStretchLastSection(True)
            table.horizontalHeader().setSectionResizeMode(
                0, QHeaderView.ResizeToContents)
            table.horizontalHeader().setSectionResizeMode(
                1, QHeaderView.ResizeToContents)
            table.setMaximumHeight(30 * len(slots) + 28)
            table.setStyleSheet(
                "QTableWidget { border: 1px solid #E5E7EB; border-radius: 8px;"
                " background: #FAFAFA; gridline-color: #F0F0F3; }"
                "QHeaderView::section { background: #F3F4F6; font-weight: 600;"
                " padding: 4px 8px; border: none; }")
            for i, slot in enumerate(slots):
                table.setItem(i, 0, QTableWidgetItem(slot.get("slot", "")))
                table.setItem(i, 1, QTableWidgetItem(slot.get("asset_id", "")))
                table.setItem(i, 2, QTableWidgetItem(slot.get("purpose", "")))
            self._content_layout.insertWidget(
                self._content_layout.count() - 1, table)

        # Shots
        shots = sb_data.get("shots", [])
        if shots:
            shots_section = QLabel("🎥 分镜时间轴")
            shots_section.setStyleSheet(
                "font-size: 14px; font-weight: 700; color: #6366F1;"
                " background: transparent; margin-top: 8px;")
            self._content_layout.insertWidget(
                self._content_layout.count() - 1, shots_section)

            for shot in shots:
                shot_frame = QFrame()
                shot_frame.setStyleSheet(
                    "QFrame { background: #FAFBFC; border: 1px solid #E5E7EB;"
                    " border-radius: 10px; }")
                sl = QVBoxLayout(shot_frame)
                sl.setContentsMargins(14, 10, 14, 10)
                sl.setSpacing(6)

                header = QLabel(
                    f"<b>{shot.get('time_range', '?')}</b>  "
                    f"<span style='color:#8B5CF6;'>{shot.get('shot_type', '')}</span>  ·  "
                    f"<span style='color:#059669;'>{shot.get('camera_movement', '')}</span>")
                header.setStyleSheet(
                    "font-size: 14px; background: transparent; color: #1E1E2E;")
                header.setTextFormat(Qt.RichText)
                sl.addWidget(header)

                details = (
                    f"画面：{shot.get('visual_content', '')}\n"
                    f"动作：{shot.get('subject_action', '')}\n"
                    f"光影：{shot.get('lighting_and_atmosphere', '')}"
                )
                det_lbl = QLabel(details)
                det_lbl.setWordWrap(True)
                det_lbl.setStyleSheet(
                    "font-size: 12px; color: #6B7280; background: transparent;"
                    " line-height: 1.5;")
                sl.addWidget(det_lbl)

                self._content_layout.insertWidget(
                    self._content_layout.count() - 1, shot_frame)

        # Audio
        audio = sb_data.get("audio", {})
        if audio:
            audio_section = QLabel("🔊 音频设计")
            audio_section.setStyleSheet(
                "font-size: 14px; font-weight: 700; color: #6366F1;"
                " background: transparent; margin-top: 8px;")
            self._content_layout.insertWidget(
                self._content_layout.count() - 1, audio_section)

            audio_text = (
                f"BGM：{audio.get('bgm', '')}\n"
                f"SFX：{audio.get('sfx', '')}"
            )
            if audio.get("dialogue"):
                audio_text += f"\n对白：{audio['dialogue']}"
            al = QLabel(audio_text)
            al.setWordWrap(True)
            al.setStyleSheet(
                "font-size: 13px; color: #374151; background: transparent;"
                " padding: 10px; background: #FEF3C7; border-radius: 8px;")
            self._content_layout.insertWidget(
                self._content_layout.count() - 1, al)

        # End frame
        end_frame = sb_data.get("end_frame", "")
        if end_frame:
            ef_section = QLabel("🔗 尾帧描述（衔接下一集）")
            ef_section.setStyleSheet(
                "font-size: 14px; font-weight: 700; color: #D97706;"
                " background: transparent; margin-top: 8px;")
            self._content_layout.insertWidget(
                self._content_layout.count() - 1, ef_section)
            efl = QLabel(end_frame)
            efl.setWordWrap(True)
            efl.setStyleSheet(
                "font-size: 13px; color: #92400E; background: #FFFBEB;"
                " padding: 10px; border: 1px solid #FCD34D; border-radius: 8px;")
            self._content_layout.insertWidget(
                self._content_layout.count() - 1, efl)

        # Full prompt
        full_prompt = sb_data.get("seedance_full_prompt", "")
        if full_prompt:
            fp_section = QLabel("📋 Seedance 2.0 完整提示词")
            fp_section.setStyleSheet(
                "font-size: 14px; font-weight: 700; color: #6366F1;"
                " background: transparent; margin-top: 8px;")
            self._content_layout.insertWidget(
                self._content_layout.count() - 1, fp_section)

            fp_edit = QTextEdit()
            fp_edit.setPlainText(full_prompt)
            fp_edit.setReadOnly(True)
            fp_edit.setMaximumHeight(200)
            fp_edit.setStyleSheet(
                "QTextEdit { border: 1px solid #E5E7EB; border-radius: 8px;"
                " padding: 10px; font-size: 13px; color: #1E1E2E;"
                " background: #FAFAFA; font-family: 'Microsoft YaHei', monospace; }")
            self._content_layout.insertWidget(
                self._content_layout.count() - 1, fp_edit)

            copy_btn = QPushButton("📋 复制提示词到剪贴板")
            copy_btn.setStyleSheet(
                "QPushButton { background: #6366F1; border: none;"
                " border-radius: 8px; padding: 10px 20px; font-size: 13px;"
                " color: white; font-weight: 600; }"
                "QPushButton:hover { background: #4F46E5; }")
            copy_btn.setCursor(Qt.PointingHandCursor)
            copy_btn.clicked.connect(
                lambda: QApplication.clipboard().setText(full_prompt))
            self._content_layout.insertWidget(
                self._content_layout.count() - 1, copy_btn)


class PromptReviewDialog(QDialog):
    """素材提示词审核/编辑弹窗"""

    def __init__(self, tasks: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("审核出图提示词")
        self.setMinimumSize(700, 500)
        self.resize(750, 600)
        self.setStyleSheet(
            "QDialog { background: #FFFFFF; font-family: 'Microsoft YaHei',"
            " 'PingFang SC', sans-serif; }")
        self._tasks = tasks
        self._approved_tasks: list = []

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 16)
        root.setSpacing(12)

        header = QLabel(f"共 {len(tasks)} 张素材图待生成，可修改提示词或取消不需要的项")
        header.setStyleSheet(
            "font-size: 15px; font-weight: 600; color: #1E1E2E; background: transparent;")
        root.addWidget(header)

        # Table
        self._table = QTableWidget(len(tasks), 4)
        self._table.setHorizontalHeaderLabels(["生成", "资产ID", "类型", "提示词"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self._table.setColumnWidth(0, 50)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._table.setStyleSheet(
            "QTableWidget { border: 1px solid #E5E7EB; border-radius: 10px;"
            " background: #FAFAFA; gridline-color: #F0F0F3; }"
            "QHeaderView::section { background: #F3F4F6; font-weight: 600;"
            " padding: 6px 10px; border: none; }")
        root.addWidget(self._table, 1)

        # Populate rows
        self._checkboxes: list[QCheckBox] = []
        self._prompt_edits: list[QTextEdit] = []
        for i, task in enumerate(tasks):
            cb = QCheckBox()
            cb.setChecked(True)
            self._table.setCellWidget(i, 0, cb)
            self._checkboxes.append(cb)

            self._table.setItem(i, 1, QTableWidgetItem(task.asset_id))

            type_lbl = _ASSET_TYPE_LABELS.get(task.asset_type, task.asset_type)
            view = f" · {task.view}" if task.view else ""
            self._table.setItem(i, 2, QTableWidgetItem(f"{type_lbl}{view}"))

            prompt_edit = QTextEdit()
            prompt_edit.setPlainText(task.prompt)
            prompt_edit.setMaximumHeight(80)
            prompt_edit.setStyleSheet(
                "QTextEdit { border: 1px solid #E5E7EB; border-radius: 6px;"
                " padding: 6px 8px; font-size: 12px; color: #1E1E2E;"
                " background: #FFFFFF; }"
                "QTextEdit:focus { border-color: #6366F1; }")
            self._table.setCellWidget(i, 3, prompt_edit)
            self._prompt_edits.append(prompt_edit)

            self._table.setRowHeight(i, 90)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        skip_btn = QPushButton("跳过出图（直接生成分镜）")
        skip_btn.setStyleSheet(
            "QPushButton { background: #F3F4F6; border: 1px solid #E5E7EB;"
            " border-radius: 10px; padding: 12px 24px; font-size: 14px;"
            " color: #6B7280; font-weight: 600; }"
            "QPushButton:hover { background: #E5E7EB; color: #1E1E2E; }")
        skip_btn.setCursor(Qt.PointingHandCursor)
        skip_btn.clicked.connect(lambda: self._done(skip_all=True))
        btn_row.addWidget(skip_btn)

        btn_row.addStretch()

        select_all_btn = QPushButton("全选")
        select_all_btn.setStyleSheet(
            "QPushButton { background: #E0E7FF; border: none;"
            " border-radius: 8px; padding: 8px 16px; font-size: 13px;"
            " color: #4338CA; font-weight: 600; }"
            "QPushButton:hover { background: #C7D2FE; }")
        select_all_btn.setCursor(Qt.PointingHandCursor)
        select_all_btn.clicked.connect(
            lambda: [cb.setChecked(True) for cb in self._checkboxes])
        btn_row.addWidget(select_all_btn)

        confirm_btn = QPushButton("🚀 开始生成素材图")
        confirm_btn.setStyleSheet(
            "QPushButton { background: #6366F1; border: none;"
            " border-radius: 10px; padding: 12px 28px; font-size: 14px;"
            " color: white; font-weight: 700; }"
            "QPushButton:hover { background: #4F46E5; }")
        confirm_btn.setCursor(Qt.PointingHandCursor)
        confirm_btn.clicked.connect(lambda: self._done(skip_all=False))
        btn_row.addWidget(confirm_btn)

        root.addLayout(btn_row)

    def _done(self, skip_all: bool = False):
        self._approved_tasks = []
        if skip_all:
            self.reject()
            return
        for i, task in enumerate(self._tasks):
            if self._checkboxes[i].isChecked():
                edited_prompt = self._prompt_edits[i].toPlainText().strip()
                task.prompt = edited_prompt if edited_prompt else task.prompt
                self._approved_tasks.append(task)
        self.accept()

    def get_approved_tasks(self) -> list:
        return self._approved_tasks


# ──────────────────────────────────────────────
#  Regenerate Thread
# ──────────────────────────────────────────────

class _RegenerateWorker(QThread):
    """后台生成单张图片的 Worker"""
    log = Signal(str)
    finished = Signal(bool, str, str)  # (success, filepath, error_msg)

    def __init__(self, api: NoovaAPI, model: str, prompt: str,
                 aspect_ratio: str, image_size: str, save_path: str):
        super().__init__()
        self._api = api
        self._model = model
        self._prompt = prompt
        self._ratio = aspect_ratio
        self._size = image_size
        self._path = save_path
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            self.log.emit("生成中...")
            task_id, _ = self._api.create_draw_task(
                self._model, self._prompt, self._ratio, self._size, urls=[])
            self.log.emit(f"任务ID: {task_id[:16]}...")

            result = self._api.poll_task_result(
                task_id, 20,
                log_callback=self.log.emit,
                cancel_check=lambda: self._cancel)
            status = result.get("data", {}).get("status", "unknown")
            if status != "succeeded":
                self.finished.emit(False, "", f"任务状态: {status}")
                return
            img_url = result["data"]["results"][0]["url"]
            self._api.download_image(img_url, self._path)
            self.log.emit("✅ 重新生成完成")
            self.finished.emit(True, self._path, "")
        except Exception as e:
            self.finished.emit(False, "", str(e))


# ──────────────────────────────────────────────
#  Regenerate Dialog
# ──────────────────────────────────────────────

class RegenerateDialog(QDialog):
    """单张素材图重新生成弹窗"""

    def __init__(self, asset_id: str, asset_name: str, asset_type: str,
                 current_prompt: str, filepath: str,
                 noova_api: NoovaAPI, parent=None):
        super().__init__(parent)
        self._asset_id = asset_id
        self._filepath = filepath
        self._noova = noova_api
        self._worker: _RegenerateWorker | None = None
        self._new_filepath = ""

        self.setWindowTitle(f"重新生成 — {asset_name}")
        self.setMinimumSize(600, 560)
        self.resize(640, 600)
        self.setStyleSheet(
            "QDialog { background: #FFFFFF; font-family: 'Microsoft YaHei',"
            " 'PingFang SC', sans-serif; }")

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 16)
        root.setSpacing(14)

        # ── Image preview + download ──
        preview_row = QHBoxLayout()
        preview_row.setSpacing(12)

        self._preview = QLabel()
        self._preview.setFixedSize(180, 120)
        self._preview.setAlignment(Qt.AlignCenter)
        self._preview.setStyleSheet(
            "background: #F3F4F6; border: 1px solid #E5E7EB;"
            " border-radius: 10px;")
        if filepath and os.path.exists(filepath):
            pix = QPixmap(filepath)
            if not pix.isNull():
                self._preview.setPixmap(pix.scaled(
                    180, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        preview_row.addWidget(self._preview)

        info_col = QVBoxLayout()
        info_col.setSpacing(6)
        type_lbl = _ASSET_TYPE_LABELS.get(asset_type, "")
        info_col.addWidget(QLabel(f"<b>类型:</b> {type_lbl}"))
        info_col.addWidget(QLabel(f"<b>ID:</b> {asset_id}"))
        info_col.addWidget(QLabel(f"<b>名称:</b> {asset_name}"))
        info_col.addStretch()

        self._dl_btn = QPushButton("📥 下载当前图片")
        self._dl_btn.setStyleSheet(
            "QPushButton { background: #10B981; border: none;"
            " border-radius: 8px; padding: 8px 16px; font-size: 13px;"
            " color: white; font-weight: 600; }"
            "QPushButton:hover { background: #059669; }")
        self._dl_btn.setCursor(Qt.PointingHandCursor)
        self._dl_btn.clicked.connect(self._download_current)
        info_col.addWidget(self._dl_btn)

        preview_row.addLayout(info_col)
        preview_row.addStretch()
        root.addLayout(preview_row)

        # ── Prompt editor ──
        root.addWidget(QLabel("提示词（可编辑）:"))
        self._prompt_edit = QTextEdit()
        self._prompt_edit.setPlainText(current_prompt)
        self._prompt_edit.setMinimumHeight(120)
        self._prompt_edit.setMaximumHeight(180)
        self._prompt_edit.setStyleSheet(
            "QTextEdit { border: 1px solid #E5E7EB; border-radius: 10px;"
            " padding: 10px 12px; font-size: 13px; color: #1E1E2E;"
            " background: #FAFAFA; }"
            "QTextEdit:focus { border-color: #6366F1; background: #FFFFFF; }")
        root.addWidget(self._prompt_edit)

        # ── Model / Size / Ratio row ──
        model_row = QHBoxLayout()
        model_row.setSpacing(12)

        mc = QVBoxLayout(); mc.setSpacing(4)
        mc.addWidget(QLabel("出图模型"))
        self._combo_model = QComboBox()
        self._combo_model.addItems(list(MODEL_CONFIG.keys()))
        idx = self._combo_model.findText(DEFAULT_IMAGE_MODEL)
        if idx >= 0:
            self._combo_model.setCurrentIndex(idx)
        self._combo_model.setStyleSheet(COMBO_STYLE)
        self._combo_model.currentTextChanged.connect(self._on_model_changed)
        mc.addWidget(self._combo_model)
        model_row.addLayout(mc)

        sc = QVBoxLayout(); sc.setSpacing(4)
        sc.addWidget(QLabel("画质"))
        self._combo_size = QComboBox()
        self._combo_size.setStyleSheet(COMBO_STYLE)
        sc.addWidget(self._combo_size)
        model_row.addLayout(sc)

        rc = QVBoxLayout(); rc.setSpacing(4)
        rc.addWidget(QLabel("比例"))
        self._combo_ratio = QComboBox()
        self._combo_ratio.setStyleSheet(COMBO_STYLE)
        rc.addWidget(self._combo_ratio)
        model_row.addLayout(rc)

        self._on_model_changed(self._combo_model.currentText())
        root.addLayout(model_row)

        # ── Status label ──
        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet(
            "font-size: 12px; color: #6366F1; font-weight: 600; background: transparent;")
        root.addWidget(self._status_lbl)

        # ── Buttons ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        cancel_btn = QPushButton("取消")
        cancel_btn.setStyleSheet(
            "QPushButton { background: #F3F4F6; border: 1px solid #E5E7EB;"
            " border-radius: 10px; padding: 10px 24px; font-size: 14px;"
            " color: #6B7280; font-weight: 600; }"
            "QPushButton:hover { background: #E5E7EB; color: #1E1E2E; }")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        btn_row.addStretch()

        self._reg_btn = QPushButton("🔄 重新生成")
        self._reg_btn.setStyleSheet(
            "QPushButton { background: #6366F1; border: none;"
            " border-radius: 10px; padding: 10px 28px; font-size: 14px;"
            " color: white; font-weight: 700; }"
            "QPushButton:hover { background: #4F46E5; }"
            "QPushButton:disabled { background: #A5B4FC; }")
        self._reg_btn.setCursor(Qt.PointingHandCursor)
        self._reg_btn.clicked.connect(self._start_regenerate)
        btn_row.addWidget(self._reg_btn)

        root.addLayout(btn_row)

    def _on_model_changed(self, model_name: str):
        config = MODEL_CONFIG.get(model_name)
        if not config:
            return
        self._combo_size.clear()
        self._combo_size.addItems(config.get("sizes", ["1K"]))
        default_size = DEFAULT_IMAGE_SIZE if DEFAULT_IMAGE_SIZE in config.get("sizes", []) else config["sizes"][0]
        idx = self._combo_size.findText(default_size)
        if idx >= 0:
            self._combo_size.setCurrentIndex(idx)

        self._combo_ratio.clear()
        self._combo_ratio.addItems(config.get("ratios", ["16:9"]))
        default_ratio = DEFAULT_ASPECT_RATIO if DEFAULT_ASPECT_RATIO in config.get("ratios", []) else config["ratios"][0]
        idx = self._combo_ratio.findText(default_ratio)
        if idx >= 0:
            self._combo_ratio.setCurrentIndex(idx)

    def _download_current(self):
        current_file = self._new_filepath or self._filepath
        if not current_file or not os.path.exists(current_file):
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "保存图片", os.path.basename(current_file),
            "PNG (*.png);;所有文件 (*)")
        if path:
            try:
                shutil.copy2(current_file, path)
            except Exception as e:
                QMessageBox.critical(self, "错误", f"下载失败: {e}")

    def _start_regenerate(self):
        prompt = self._prompt_edit.toPlainText().strip()
        if not prompt:
            QMessageBox.warning(self, "提示", "提示词不能为空")
            return

        model = self._combo_model.currentText()
        size = self._combo_size.currentText()
        ratio = self._combo_ratio.currentText()

        # Save new image alongside original
        base, ext = os.path.splitext(self._filepath)
        self._new_filepath = f"{base}_v{datetime.now().strftime('%H%M%S')}{ext}"

        self._reg_btn.setEnabled(False)
        self._status_lbl.setText("⏳ 正在生成...")

        self._worker = _RegenerateWorker(
            self._noova, model, prompt, ratio, size, self._new_filepath)
        self._worker.log.connect(lambda msg: self._status_lbl.setText(msg))
        self._worker.finished.connect(self._on_regenerate_done)
        self._worker.start()

    def _on_regenerate_done(self, success: bool, filepath: str, error: str):
        self._reg_btn.setEnabled(True)
        if success:
            self._status_lbl.setText("✅ 生成成功！")
            # Replace old with new
            try:
                if os.path.exists(self._filepath):
                    backup = self._filepath + ".bak"
                    os.replace(self._filepath, backup)
                os.replace(filepath, self._filepath)
                self._new_filepath = ""
                # Clean up backup
                backup = self._filepath + ".bak"
                if os.path.exists(backup):
                    os.remove(backup)
            except Exception:
                pass
            # Update preview
            pix = QPixmap(self._filepath)
            if not pix.isNull():
                self._preview.setPixmap(pix.scaled(
                    180, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self._status_lbl.setText("✅ 重新生成完成，点击取消关闭")
            self._status_lbl.setStyleSheet(
                "font-size: 12px; color: #10B981; font-weight: 600; background: transparent;")
            # Signal: regenerate callback
            self._should_reload = True
        else:
            self._status_lbl.setText(f"❌ 失败: {error}")
            self._status_lbl.setStyleSheet(
                "font-size: 12px; color: #EF4444; font-weight: 600; background: transparent;")

    def should_reload(self) -> bool:
        return getattr(self, "_should_reload", False)
