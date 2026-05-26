"""文件夹批量出图插件 —— 完全独立的功能模块

与 batch_draw.py 互补：
  - batch_draw:      从 Excel 表格读取提示词和参考图
  - folder_batch_draw: 从文件夹逐张读取参考图，按提示词分组批量生成

每张图片独立提交一次 API 任务，共用所属组的提示词。
输出按提示词分文件夹存放。

删除此文件不会影响主程序及其他插件。
"""

import os
import re
import threading
from typing import List

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QFrame, QScrollArea,
    QLabel, QPushButton, QLineEdit, QSpinBox,
    QFileDialog, QMessageBox,
)
from PySide6.QtCore import Qt, QThread, Signal

from plugin_base import BasePlugin
from plugins._noova_api import NoovaAPI, MODEL_CONFIG, MAX_CONCURRENCY
from plugins._design import COMBO_STYLE, NoScrollComboBox as QComboBox

IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}
GROUP_COUNT = 10

# Unicode 圆形数字 ①~⑩
CIRCLED_NUMBERS = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨", "⑩"]


def sanitize_folder_name(prompt: str, fallback: str = "group") -> str:
    safe = re.sub(r'[<>:"/\\|?*]', '', prompt)
    safe = re.sub(r'\s+', '_', safe.strip())
    safe = safe.strip('. ')
    safe = safe[:64]
    return safe if safe else fallback


def make_unique_subdir(base_dir: str, name: str) -> str:
    candidate = os.path.join(base_dir, name)
    if not os.path.exists(candidate):
        return candidate
    i = 2
    while True:
        candidate = os.path.join(base_dir, f"{name}_{i}")
        if not os.path.exists(candidate):
            return candidate
        i += 1


def scan_folder_images(folder: str) -> List[str]:
    result = []
    try:
        for fname in sorted(os.listdir(folder)):
            if os.path.splitext(fname)[1].lower() in IMAGE_EXTENSIONS:
                result.append(os.path.join(folder, fname))
    except OSError:
        pass
    return result


# ═══════════════════════════════════════════
#  后台工作线程
# ═══════════════════════════════════════════
class FolderBatchDrawWorker(QThread):
    log_msg = Signal(str)
    progress_update = Signal(int, int)
    finished_task = Signal(bool)

    def __init__(self, api_key: str, groups: List[dict], output_dir: str,
                 model: str, aspect_ratio: str, image_size: str,
                 poll_interval: int, concurrency: int):
        super().__init__()
        self.api_key = api_key
        self.groups = groups
        self.output_dir = output_dir
        self.model = model
        self.aspect_ratio = aspect_ratio
        self.image_size = image_size
        self.poll_interval = poll_interval
        self.concurrency = concurrency
        self.is_running = True
        self._executor = None
        self._lock = threading.Lock()
        self._completed = 0
        self._total = 0

    # ---- 单张图片处理 ----

    def _process_image(self, task: dict):
        """处理单张图片：编码 → 提交 API → 轮询 → 下载"""
        if not self.is_running:
            return

        prompt = task["prompt"]
        image_path = task["image_path"]
        group_dir = task["group_dir"]
        group_idx = task["group_idx"]
        api = NoovaAPI(self.api_key)

        with self._lock:
            self._completed += 1
            idx = self._completed
        fname = os.path.basename(image_path)

        self.log_msg.emit(
            f"\n[{idx}/{self._total}] 组{group_idx} | {fname}")
        self.log_msg.emit(f"  提示词: {prompt}")

        # 1. 编码
        try:
            b64 = api.local_file_to_base64(image_path, self.log_msg.emit)
        except Exception as e:
            self.log_msg.emit(f"  ❌ 编码失败: {e}")
            self.progress_update.emit(self._completed, self._total)
            return

        if not self.is_running:
            return

        # 2. 提交
        try:
            task_id, _ = api.create_draw_task(
                self.model, prompt, self.aspect_ratio, self.image_size, [b64])

            # 3. 轮询
            result_data = api.poll_task_result(
                task_id, self.poll_interval, self.log_msg.emit,
                cancel_check=lambda: not self.is_running)
            status = str((result_data.get("data") or {}).get("status") or "")

            if status == "succeeded":
                results = (result_data.get("data") or {}).get("results", [])
                if results:
                    final_img_url = results[0].get("url")
                    os.makedirs(group_dir, exist_ok=True)
                    safe_basename = re.sub(r'[<>:"/\\|?*]', '', fname)
                    filename = f"{safe_basename}_{task_id}.png"
                    save_path = os.path.join(group_dir, filename)
                    api.download_image(final_img_url, save_path)
                    self.log_msg.emit(f"  ✅ 已保存: {save_path}")
            else:
                self.log_msg.emit(f"  ❌ 生成失败，状态: {status}")
        except Exception as e:
            self.log_msg.emit(f"  ❌ 处理异常: {e}")

        self.progress_update.emit(self._completed, self._total)

    # ---- 主入口 ----

    def run(self):
        try:
            # 过滤有效组
            valid_groups = [g for g in self.groups
                            if g.get("prompt", "").strip() and g.get("folder", "").strip()]

            if not valid_groups:
                self.log_msg.emit("没有有效的任务组（提示词和文件夹均需填写）。")
                self.finished_task.emit(False)
                return

            # 展开为图片级任务
            all_tasks = []
            for gi, g in enumerate(valid_groups):
                prompt = g["prompt"].strip()
                folder = g["folder"].strip()
                safe_name = sanitize_folder_name(prompt, f"group_{gi + 1}")
                group_dir = make_unique_subdir(self.output_dir, safe_name)

                images = scan_folder_images(folder)
                if not images:
                    self.log_msg.emit(
                        f"⚠️ 组{gi + 1} ({prompt}): 文件夹中无图片，跳过")
                    continue

                self.log_msg.emit(
                    f"组{gi + 1} ({prompt}): 发现 {len(images)} 张图片 → 输出至 {group_dir}")
                for img_path in images:
                    all_tasks.append({
                        "prompt": prompt,
                        "image_path": img_path,
                        "group_dir": group_dir,
                        "group_idx": gi + 1,
                    })

            self._total = len(all_tasks)
            if self._total == 0:
                self.log_msg.emit("没有找到任何有效图片。")
                self.finished_task.emit(False)
                return

            self.log_msg.emit(
                f"\n总计 {self._total} 个图片任务 | 并发: {self.concurrency} | "
                f"轮询间隔: {self.poll_interval}s\n")

            if self.concurrency == 1:
                for task in all_tasks:
                    if not self.is_running:
                        break
                    self._process_image(task)
            else:
                from concurrent.futures import ThreadPoolExecutor, as_completed
                with ThreadPoolExecutor(max_workers=self.concurrency) as executor:
                    self._executor = executor
                    futures = [executor.submit(self._process_image, t)
                               for t in all_tasks]
                    for future in as_completed(futures):
                        if not self.is_running:
                            for f in futures:
                                f.cancel()
                            break
                        try:
                            future.result()
                        except Exception:
                            pass

            self.log_msg.emit("\n🎉 全部图片任务处理完毕！")
            self.finished_task.emit(True)
        except Exception as e:
            self.log_msg.emit(f"\n系统发生错误: {e}")
            self.finished_task.emit(False)

    def stop(self):
        self.is_running = False
        if self._executor:
            self._executor.shutdown(wait=False, cancel_futures=True)
            self._executor = None


# ═══════════════════════════════════════════
#  插件入口
# ═══════════════════════════════════════════
class FolderBatchDrawPlugin(BasePlugin):
    plugin_id = "folder_batch_draw"
    name = "文件夹批量出图"
    icon = "📁"
    color = "#8B5CF6"
    description = ("从文件夹逐张读取参考图，按提示词分组批量生成。\n"
                   "每组一张图片 = 一次 API 调用，输出按组分文件夹存放。")


    def __init__(self):
        super().__init__()
        self._worker = None
        self.output_path = ""
        self.group_prompts: List[QLineEdit] = []
        self.group_folder_labels: List[QLabel] = []
        self.group_folder_paths: List[str] = [""] * GROUP_COUNT
        self.group_cards: List[QFrame] = []

    # ---- 工作区 UI ----

    def create_workspace(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background-color: #F9FAFB;")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        outer = QVBoxLayout(content)
        outer.setContentsMargins(56, 44, 56, 52)

        # --- 顶栏 ---
        top_bar = QHBoxLayout()
        back_btn = QPushButton("← 返回首页")
        back_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; color: #6B7280;"
            " font-size: 14px; padding: 6px 0; }"
            "QPushButton:hover { color: #6366F1; }")
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.clicked.connect(lambda: self.main_window.switch_page(0))
        top_bar.addWidget(back_btn)
        top_bar.addStretch()
        outer.addLayout(top_bar)
        outer.addSpacing(8)

        # --- 标题区 ---
        title = QLabel(f"{self.icon} {self.name}")
        title.setStyleSheet(
            "font-size: 28px; font-weight: 700; color: #1E1E2E; background: transparent;")
        subtitle = QLabel("每组填写提示词并选择参考图文件夹，每张图片独立生成，结果按组输出")
        subtitle.setStyleSheet("font-size: 14px; color: #6B7280; background: transparent;")
        outer.addWidget(title)
        outer.addWidget(subtitle)
        outer.addSpacing(28)

        # --- 主内容区：左右分栏 ---
        body = QHBoxLayout()
        body.setSpacing(24)

        # === 左栏：设置 ===
        left_col = QVBoxLayout()
        left_col.setSpacing(16)

        # 设置卡片
        settings_card = QFrame()
        settings_card.setStyleSheet(
            "QFrame#SettingsCard { background: #FFFFFF; border-radius: 14px; "
            "border: 1px solid #ECEDF0; }")
        settings_card.setObjectName("SettingsCard")
        settings_card.setFixedWidth(340)
        sf = QFormLayout(settings_card)
        sf.setContentsMargins(24, 22, 24, 22)
        sf.setSpacing(12)
        sf.setVerticalSpacing(14)

        sf_title = QLabel("⚙️ 生成设置")
        sf_title.setStyleSheet(
            "font-size: 15px; font-weight: bold; color: #1A1A1A; "
            "background: transparent; padding-bottom: 4px;")
        sf.addRow(sf_title)

        self.input_api = QLineEdit()
        self.input_api.setPlaceholderText("sk-...")
        self.input_api.setEchoMode(QLineEdit.Password)
        self.input_api.setText(os.environ.get("NOOVA_API_KEY", ""))
        self.input_api.setStyleSheet(
            "QLineEdit { border: 1px solid #E5E7EB; border-radius: 10px;"
            " padding: 10px 14px; font-size: 14px; background: #FAFAFA; }"
            "QLineEdit:focus { border: 1px solid #6366F1; background: #FFFFFF; }")

        self.combo_model = QComboBox()
        self.combo_model.addItems(list(MODEL_CONFIG.keys()))
        self.combo_model.setStyleSheet(COMBO_STYLE)

        self.combo_ar = QComboBox()
        self.combo_ar.setStyleSheet(COMBO_STYLE)
        self.combo_size = QComboBox()
        self.combo_size.setStyleSheet(COMBO_STYLE)

        self.spin_poll = QSpinBox()
        self.spin_poll.setMinimum(20)
        self.spin_poll.setMaximum(9999)
        self.spin_poll.setValue(20)
        self.spin_poll.setSuffix(" 秒")

        self.spin_concurrency = QSpinBox()
        self.spin_concurrency.setMinimum(1)
        self.spin_concurrency.setMaximum(MAX_CONCURRENCY)
        self.spin_concurrency.setValue(1)
        self.spin_concurrency.setSuffix(" 个")

        self.combo_model.currentTextChanged.connect(self._on_model_changed)
        self._on_model_changed(self.combo_model.currentText())

        sf.addRow(QLabel("API Key"), self.input_api)
        sf.addRow(QLabel("模型"), self.combo_model)
        sf.addRow(QLabel("比例"), self.combo_ar)
        sf.addRow(QLabel("画质"), self.combo_size)
        sf.addRow(QLabel("轮询间隔"), self.spin_poll)
        sf.addRow(QLabel("并发数"), self.spin_concurrency)

        left_col.addWidget(settings_card)

        # 输出目录卡片
        out_card = QFrame()
        out_card.setStyleSheet(
            "QFrame#OutCard { background: #FFFFFF; border-radius: 14px; "
            "border: 1px solid #ECEDF0; }")
        out_card.setObjectName("OutCard")
        out_card.setFixedWidth(340)
        out_inner = QVBoxLayout(out_card)
        out_inner.setContentsMargins(24, 18, 24, 18)
        out_inner.setSpacing(10)

        out_label = QLabel("📂 输出目录")
        out_label.setStyleSheet(
            "font-size: 15px; font-weight: bold; color: #1A1A1A; background: transparent;")
        out_inner.addWidget(out_label)

        out_row = QHBoxLayout()
        self.btn_output = QPushButton("选择目录...")
        self.btn_output.setStyleSheet("""
            QPushButton { background: #F3F4F6; border: 1px solid #E5E7EB;
                border-radius: 8px; padding: 9px 14px; font-size: 13px; color: #333; }
            QPushButton:hover { background: #E5E7EB; }
        """)
        self.btn_output.setCursor(Qt.PointingHandCursor)
        self.btn_output.clicked.connect(self._select_output_dir)
        self.output_label = QLabel("未选择")
        self.output_label.setStyleSheet(
            "color: #999; font-size: 12px; background: transparent;")
        self.output_label.setWordWrap(True)
        out_row.addWidget(self.btn_output)
        out_row.addWidget(self.output_label, 1)
        out_inner.addLayout(out_row)

        left_col.addWidget(out_card)
        left_col.addStretch()

        body.addLayout(left_col)

        # === 右栏：提示词组 ===
        right_col = QVBoxLayout()
        right_col.setSpacing(10)

        groups_header = QHBoxLayout()
        groups_title = QLabel("📋 提示词组")
        groups_title.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #1A1A1A; background: transparent;")
        groups_hint = QLabel(f"最多 {GROUP_COUNT} 组")
        groups_hint.setStyleSheet("font-size: 12px; color: #BBB; background: transparent;")
        groups_header.addWidget(groups_title)
        groups_header.addWidget(groups_hint)
        groups_header.addStretch()
        right_col.addLayout(groups_header)
        right_col.addSpacing(4)

        # 每组的卡片
        for i in range(GROUP_COUNT):
            group_card = self._build_group_card(i)
            self.group_cards.append(group_card)
            right_col.addWidget(group_card)

        right_col.addStretch()
        body.addLayout(right_col, 1)

        outer.addLayout(body)
        outer.addSpacing(28)

        # --- 底部启动按钮 ---
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.btn_start = QPushButton("🚀 开始执行任务")
        self.btn_start.setStyleSheet("""
            QPushButton {
                background-color: #8B5CF6; color: #FFFFFF; border-radius: 12px;
                padding: 14px 48px; font-size: 16px; font-weight: bold; border: none;
            }
            QPushButton:hover { background-color: #7C3AED; }
            QPushButton:disabled { background-color: #CCCCCC; }
        """)
        self.btn_start.setCursor(Qt.PointingHandCursor)
        self.btn_start.clicked.connect(self._start_task)
        btn_row.addWidget(self.btn_start)
        btn_row.addStretch()
        outer.addLayout(btn_row)

        scroll.setWidget(content)
        wrapped = QVBoxLayout(page)
        wrapped.setContentsMargins(0, 0, 0, 0)
        wrapped.addWidget(scroll)
        return page

    def _build_group_card(self, index: int) -> QFrame:
        """构建单组卡片"""
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame#GroupCard_{index} {{
                background: #FFFFFF;
                border: 1px solid #EEEEEE;
                border-left: 3px solid #E5E7EB;
                border-radius: 10px;
            }}
        """)
        card.setObjectName(f"GroupCard_{index}")
        inner = QVBoxLayout(card)
        inner.setContentsMargins(16, 12, 16, 12)
        inner.setSpacing(8)

        # 顶行：徽章 + 提示词
        top_row = QHBoxLayout()
        top_row.setSpacing(10)
        badge = QLabel(CIRCLED_NUMBERS[index])
        badge.setStyleSheet(
            f"font-size: 18px; color: {self.color}; "
            "background: transparent; font-weight: bold;")
        badge.setFixedWidth(28)
        top_row.addWidget(badge)

        prompt_input = QLineEdit()
        prompt_input.setPlaceholderText(f"输入提示词...")
        prompt_input.setStyleSheet("""
            QLineEdit {
                border: 1px solid #E5E7EB; border-radius: 8px;
                padding: 9px 12px; font-size: 14px; background: #FAFAFA;
            }
            QLineEdit:focus { border: 1px solid #8B5CF6; background: #FFFFFF; }
        """)
        self.group_prompts.append(prompt_input)
        top_row.addWidget(prompt_input, 1)
        inner.addLayout(top_row)

        # 底行：文件夹选择
        bot_row = QHBoxLayout()
        bot_row.setSpacing(10)
        bot_row.addSpacing(38)  # 对齐徽章宽度

        btn_folder = QPushButton("📁 选择参考图文件夹")
        btn_folder.setStyleSheet("""
            QPushButton { background: #F8F9FA; border: 1px dashed #D1D5DB;
                border-radius: 8px; padding: 7px 14px; font-size: 12px; color: #666; }
            QPushButton:hover { background: #F0F0FF; border-color: #8B5CF6; color: #8B5CF6; }
        """)
        btn_folder.setCursor(Qt.PointingHandCursor)
        btn_folder.clicked.connect(
            lambda checked=None, idx=index: self._select_folder(idx))
        bot_row.addWidget(btn_folder)

        folder_label = QLabel("未选择参考图")
        folder_label.setStyleSheet(
            "color: #BBB; font-size: 12px; background: transparent;")
        folder_label.setWordWrap(True)
        self.group_folder_labels.append(folder_label)
        bot_row.addWidget(folder_label, 1)
        inner.addLayout(bot_row)

        return card

    # ---- 事件处理 ----

    def _on_model_changed(self, model_name):
        config = MODEL_CONFIG.get(model_name, {})
        self.combo_ar.clear()
        self.combo_ar.addItems(config.get("ratios", []))
        self.combo_size.clear()
        self.combo_size.addItems(config.get("sizes", []))

    def _select_folder(self, index: int):
        folder = QFileDialog.getExistingDirectory(
            self.main_window, f"选择第{index + 1}组的参考图文件夹")
        if folder:
            # 统计图片数
            img_count = len(scan_folder_images(folder))
            info = f"{img_count} 张图"
            self.group_folder_paths[index] = folder
            self.group_folder_labels[index].setText(f"✅ {folder}  ({info})")
            self.group_folder_labels[index].setStyleSheet(
                "color: #10B981; font-size: 12px; background: transparent;")
            # 卡片左边框变紫
            card = self.group_cards[index]
            card.setStyleSheet(f"""
                QFrame#GroupCard_{index} {{
                    background: #FFFFFF;
                    border: 1px solid #E5E7EB;
                    border-left: 3px solid {self.color};
                    border-radius: 10px;
                }}
            """)

    def _select_output_dir(self):
        folder = QFileDialog.getExistingDirectory(self.main_window, "选择输出根目录")
        if folder:
            self.output_path = folder
            self.output_label.setText(f"✅ {folder}")
            self.output_label.setStyleSheet(
                "color: #10B981; font-size: 12px; background: transparent;")

    def _start_task(self):
        if self._worker and self._worker.isRunning():
            QMessageBox.information(self.main_window, "提示", "有任务正在运行，请先终止或等待完成")
            return

        api_key = self.input_api.text().strip()
        if not api_key:
            QMessageBox.warning(self.main_window, "提示", "请填写 API Key！")
            return

        groups = []
        for i in range(GROUP_COUNT):
            prompt = self.group_prompts[i].text().strip()
            folder = self.group_folder_paths[i]
            groups.append({"prompt": prompt, "folder": folder})

        valid = [g for g in groups if g["prompt"] and g["folder"]]
        if not valid:
            QMessageBox.warning(
                self.main_window, "提示",
                "请至少填写一组完整的提示词并选择参考图文件夹！")
            return

        if not self.output_path:
            QMessageBox.warning(self.main_window, "提示", "请选择输出目录！")
            return

        model = self.combo_model.currentText()
        ar = self.combo_ar.currentText()
        size = self.combo_size.currentText()
        poll_interval = self.spin_poll.value()
        concurrency = self.spin_concurrency.value()

        self._worker = FolderBatchDrawWorker(
            api_key, groups, self.output_path, model, ar, size,
            poll_interval, concurrency)
        self._worker.log_msg.connect(self.main_window.monitor_log)
        self._worker.progress_update.connect(self.main_window.monitor_progress)
        self._worker.finished_task.connect(self._on_worker_finished)

        mw = self.main_window
        mw.monitor_clear()
        mw.monitor_set_running(True)
        mw.stop_requested.connect(self._stop_task)
        mw.switch_to_monitor()

        self.btn_start.setDisabled(True)
        self._worker.start()

    def _on_worker_finished(self, success):
        self.main_window.monitor_set_running(False)
        self.btn_start.setDisabled(False)
        try:
            self.main_window.stop_requested.disconnect(self._stop_task)
        except TypeError:
            pass
        if success:
            QMessageBox.information(self.main_window, "完成", "所有图片任务已处理完毕！")

    def _stop_task(self):
        if self._worker and self._worker.isRunning():
            self._worker.stop()
