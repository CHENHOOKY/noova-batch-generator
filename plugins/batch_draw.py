"""批量出图插件 —— 完全独立的功能模块

包含:
  - ExcelProcessor: 解析 Excel，提取提示词与参考图
  - BatchDrawWorker: 并发任务处理线程
  - BatchDrawPlugin: 插件入口（卡片 + 工作区 UI + 任务调度）

API 通信层由 plugins._noova_api 共享提供。
删除此文件不会影响主程序及其他插件。
"""

import os
import re
import threading
from typing import List, Dict

import pandas as pd

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QFrame, QScrollArea,
    QLabel, QPushButton, QLineEdit, QSpinBox,
    QFileDialog, QMessageBox,
)
from PySide6.QtCore import Qt, QThread, Signal

from plugin_base import BasePlugin
from plugins._noova_api import NoovaAPI, MODEL_CONFIG, MAX_IMAGE_DIM, MAX_CONCURRENCY
from plugins._design import COMBO_STYLE, NoScrollComboBox as QComboBox


# ═══════════════════════════════════════════
#  Excel 解析层
# ═══════════════════════════════════════════
class ExcelProcessor:
    @staticmethod
    def extract_dispimg_from_zip(filepath: str, extract_dir: str) -> Dict[str, str]:
        dispimg_mapping = {}
        try:
            import zipfile
            from xml.etree import ElementTree as ET
            if not zipfile.is_zipfile(filepath):
                return dispimg_mapping

            with zipfile.ZipFile(filepath, 'r') as z:
                namelist = z.namelist()
                if 'xl/cellimages.xml' in namelist and 'xl/_rels/cellimages.xml.rels' in namelist:
                    rels_xml = z.read('xl/_rels/cellimages.xml.rels')
                    rels_root = ET.fromstring(rels_xml)
                    rels_map = {rel.attrib.get('Id'): rel.attrib.get('Target')
                                for rel in rels_root}

                    cellimg_xml = z.read('xl/cellimages.xml')
                    cellimg_root = ET.fromstring(cellimg_xml)

                    for pic in cellimg_root.iter():
                        if pic.tag.endswith('pic'):
                            name_attr = embed_attr = None
                            for elem in pic.iter():
                                if elem.tag.endswith('cNvPr'):
                                    name_attr = elem.attrib.get('name')
                                if elem.tag.endswith('blip'):
                                    for k, v in elem.attrib.items():
                                        if k.endswith('embed'):
                                            embed_attr = v

                            if name_attr and embed_attr and embed_attr in rels_map:
                                target = rels_map[embed_attr]
                                target_path = target[1:] if target.startswith(
                                    '/') else f"xl/{target}"
                                if target_path in namelist:
                                    ext = os.path.splitext(target_path)[1]
                                    safe_name = os.path.basename(name_attr)
                                    save_path = os.path.join(extract_dir,
                                                             f"{safe_name}{ext}")
                                    with open(save_path, 'wb') as f:
                                        f.write(z.read(target_path))
                                    dispimg_mapping[name_attr] = save_path
        except Exception as e:
            print(f"提取 cellimages 失败: {e}")
        return dispimg_mapping

    @staticmethod
    def extract_floating_images(filepath: str, extract_dir: str,
                                 log_callback=None) -> Dict[int, List[str]]:
        floating_mapping = {}
        try:
            import openpyxl
            wb = openpyxl.load_workbook(filepath, data_only=True)
            ws = wb.active
            for img in getattr(ws, '_images', []):
                row = img.anchor._from.row + 1
                img_path = os.path.join(extract_dir, f"float_row{row}_{id(img)}.png")
                saved = False

                if hasattr(img, 'image') and hasattr(img.image, 'save'):
                    img.image.save(img_path)
                    saved = True
                elif hasattr(img, '_data'):
                    with open(img_path, 'wb') as f:
                        f.write(img._data())
                    saved = True

                if saved:
                    if row not in floating_mapping:
                        floating_mapping[row] = []
                    floating_mapping[row].append(img_path)
        except Exception as e:
            if log_callback:
                log_callback(f"  -> 浮动图提取失败: {e}")
        return floating_mapping

    @staticmethod
    def parse_excel(filepath: str, output_dir: str, log_callback) -> List[Dict]:
        extract_dir = os.path.join(output_dir, ".noova_extracted_images")
        os.makedirs(extract_dir, exist_ok=True)

        log_callback("🔍 正在深度扫描并提取 Excel 内嵌图片(此过程可能需要几秒钟)...")
        dispimg_mapping = ExcelProcessor.extract_dispimg_from_zip(filepath, extract_dir)
        floating_mapping = ExcelProcessor.extract_floating_images(
            filepath, extract_dir, log_callback)

        if dispimg_mapping or floating_mapping:
            log_callback(
                f"✅ 成功提取内嵌图片: {len(dispimg_mapping)} 个内嵌公式图, "
                f"{sum(len(v) for v in floating_mapping.values())} 个常规悬浮图。")

        df = pd.read_excel(filepath)
        tasks = []
        for index, row in df.iterrows():
            row_num = index + 2
            prompt = str(row.iloc[0]).strip()
            if not prompt or prompt.lower() == 'nan':
                continue

            urls = []
            if len(row) > 1:
                for cell in row.iloc[1:10]:
                    val = str(cell).strip()
                    if not val or val.lower() == 'nan':
                        continue

                    match = re.search(r'DISPIMG\("([^"]+)"', val, re.IGNORECASE)
                    if match:
                        img_id = match.group(1)
                        if img_id in dispimg_mapping:
                            urls.append(dispimg_mapping[img_id])
                        else:
                            log_callback(
                                f"⚠️ 警告: 第 {row_num} 行未能从文件底层找到对应的图片 ID: {img_id}")
                    elif val.upper().startswith("=DISPIMG"):
                        continue
                    else:
                        urls.append(val)

            if row_num in floating_mapping:
                urls.extend(floating_mapping[row_num])

            tasks.append({"row_index": row_num, "prompt": prompt, "urls": urls})
        return tasks


# ═══════════════════════════════════════════
#  后台工作线程
# ═══════════════════════════════════════════
class BatchDrawWorker(QThread):
    log_msg = Signal(str)
    progress_update = Signal(int, int)
    finished_task = Signal(bool)

    def __init__(self, api_key, excel_path, output_dir, model, aspect_ratio,
                 image_size, poll_interval, concurrency):
        super().__init__()
        self.api_key = api_key
        self.excel_path = excel_path
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

    def _process_task(self, task):
        if not self.is_running:
            return
        row_num, prompt, raw_urls = task['row_index'], task['prompt'], task['urls']
        api = NoovaAPI(self.api_key)

        with self._lock:
            self._completed += 1
            idx = self._completed
        self.log_msg.emit(f"\n[{idx}/{self._total}] 正在处理第 {row_num} 行数据...")

        processed_urls = []
        for url in raw_urls:
            if not self.is_running:
                return
            if url.startswith("http"):
                processed_urls.append(url)
            else:
                fsize = os.path.getsize(url) if os.path.exists(url) else 0
                self.log_msg.emit(
                    f"  [第{row_num}行] 处理本地图片: {os.path.basename(url)} ({fsize} bytes)")
                try:
                    b64_url = api.local_file_to_base64(url, self.log_msg.emit)
                    processed_urls.append(b64_url)
                except Exception as e:
                    self.log_msg.emit(f"  [第{row_num}行] 图片编码失败: {str(e)}")

        if not self.is_running:
            return

        try:
            self.log_msg.emit(
                f"  [第{row_num}行] 提交绘画任务至 Noova API, 参考图: {len(processed_urls)} 张")
            task_id, _ = api.create_draw_task(
                self.model, prompt, self.aspect_ratio, self.image_size, processed_urls)

            result_data = api.poll_task_result(task_id, self.poll_interval,
                                               self.log_msg.emit,
                                               cancel_check=lambda: not self.is_running)
            status = str((result_data.get("data") or {}).get("status") or "")

            if status == "succeeded":
                results = (result_data.get("data") or {}).get("results", [])
                if results:
                    final_img_url = results[0].get("url")
                    safe_prompt = "".join(
                        [c for c in prompt[:10] if c.isalnum()]).rstrip()
                    filename = f"Row{row_num}_{safe_prompt}_{task_id}.png"
                    save_path = os.path.join(self.output_dir, filename)
                    api.download_image(final_img_url, save_path)
                    self.log_msg.emit(f"  [第{row_num}行] ✅ 图片已保存: {filename}")
            else:
                self.log_msg.emit(f"  [第{row_num}行] ❌ 生成失败，状态: {status}")
        except Exception as e:
            self.log_msg.emit(f"  [第{row_num}行] ❌ 处理异常: {str(e)}")

        self.progress_update.emit(self._completed, self._total)

    def run(self):
        try:
            self.log_msg.emit("开始解析 Excel 文件...")
            os.makedirs(self.output_dir, exist_ok=True)

            tasks = ExcelProcessor.parse_excel(self.excel_path, self.output_dir,
                                               self.log_msg.emit)
            self._total = len(tasks)
            self.log_msg.emit(f"成功解析到 {self._total} 个任务。")

            if self._total == 0:
                self.log_msg.emit("没有找到有效的任务数据，请检查 Excel 格式。")
                self.finished_task.emit(False)
                return

            self.log_msg.emit(f"并发数: {self.concurrency}")

            from concurrent.futures import ThreadPoolExecutor, as_completed
            with ThreadPoolExecutor(max_workers=self.concurrency) as executor:
                self._executor = executor
                futures = [executor.submit(self._process_task, t) for t in tasks]
                for future in as_completed(futures):
                    if not self.is_running:
                        for f in futures:
                            f.cancel()
                        break
                    try:
                        future.result()
                    except Exception:
                        pass

            self.log_msg.emit("\n🎉 全部任务处理完毕！")
            self._cleanup_temp()
            self.finished_task.emit(True)
        except Exception as e:
            self.log_msg.emit(f"\n系统发生错误: {str(e)}")
            self._cleanup_temp()
            self.finished_task.emit(False)

    def _cleanup_temp(self):
        import shutil
        extract_dir = os.path.join(self.output_dir, ".noova_extracted_images")
        if os.path.isdir(extract_dir):
            try:
                shutil.rmtree(extract_dir)
            except OSError:
                pass

    def stop(self):
        self.is_running = False
        if self._executor:
            self._executor.shutdown(wait=False, cancel_futures=True)
            self._executor = None


# ═══════════════════════════════════════════
#  插件入口
# ═══════════════════════════════════════════
class BatchDrawPlugin(BasePlugin):
    plugin_id = "batch_draw"
    name = "批量出图"
    icon = "🎨"
    color = "#6366F1"
    description = ("导入 Excel 表格，自动解析提示词与参考图，"
                   "批量调用 AI 模型生成高质量图片。\n"
                   "支持 gpt-image-2 / nano-banana 全系列模型。")

    def __init__(self):
        super().__init__()
        self._worker = None
        self.excel_path = ""
        self.output_path = ""

    # ---- 工作区 UI ----

    def create_workspace(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background-color: #F9FAFB;")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(56, 44, 56, 52)

        # 返回按钮
        back_btn = QPushButton("← 返回首页")
        back_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; color: #6B7280;"
            " font-size: 14px; padding: 6px 0; }"
            "QPushButton:hover { color: #6366F1; }")
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.clicked.connect(lambda: self.main_window.switch_page(0))
        layout.addWidget(back_btn)
        layout.addSpacing(16)

        # 标题
        title = QLabel(f"{self.icon} {self.name}")
        title.setStyleSheet(
            "font-size: 28px; font-weight: 700; color: #1E1E2E; background: transparent;")
        subtitle = QLabel("导入 Excel 文件，自动解析提示词并批量调用 AI 生成图片")
        subtitle.setStyleSheet("font-size: 14px; color: #6B7280; background: transparent;")
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(32)

        # === 设置表单 ===
        form_card = QFrame()
        form_card.setStyleSheet(
            "QFrame { background: #FFFFFF; border-radius: 14px; border: 1px solid #ECEDF0; }")
        form_layout = QFormLayout(form_card)
        form_layout.setContentsMargins(32, 28, 32, 28)
        form_layout.setSpacing(16)
        form_layout.setVerticalSpacing(18)

        self._api_status_label = QLabel()
        self._update_api_status()
        self._api_status_label.setStyleSheet(
            "font-size: 13px; background: transparent; padding: 6px 0;")

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
        self.spin_concurrency.setSuffix(" 个任务")

        self.combo_model.currentTextChanged.connect(self._on_model_changed)
        self._on_model_changed(self.combo_model.currentText())

        form_layout.addRow(QLabel("🔑 API Key:"), self._api_status_label)
        form_layout.addRow(QLabel("🤖 选择模型:"), self.combo_model)
        form_layout.addRow(QLabel("📏 图像比例:"), self.combo_ar)
        form_layout.addRow(QLabel("🖼️ 图像画质:"), self.combo_size)
        form_layout.addRow(QLabel("⏱️ 轮询间隔:"), self.spin_poll)
        form_layout.addRow(QLabel("🔀 并发数量:"), self.spin_concurrency)

        layout.addWidget(form_card)
        layout.addSpacing(24)

        # === 文件选择 ===
        file_card = QFrame()
        file_card.setStyleSheet(
            "QFrame { background: #FFFFFF; border-radius: 14px; border: 1px solid #ECEDF0; }")
        file_inner = QVBoxLayout(file_card)
        file_inner.setContentsMargins(32, 24, 32, 24)
        file_inner.setSpacing(16)

        file_title = QLabel("📂 文件设置")
        file_title.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #1A1A1A; background: transparent;")
        file_inner.addWidget(file_title)

        excel_row = QHBoxLayout()
        self.btn_excel = QPushButton("选择 Excel 文件...")
        self.btn_excel.setStyleSheet("""
            QPushButton { background: #F3F4F6; border: 1px solid #E5E7EB; border-radius: 10px;
                padding: 12px 20px; font-size: 14px; color: #333; }
            QPushButton:hover { background: #E5E7EB; }
        """)
        self.btn_excel.setCursor(Qt.PointingHandCursor)
        self.btn_excel.clicked.connect(self._select_excel)
        self.excel_label = QLabel("未选择文件")
        self.excel_label.setStyleSheet("color: #999; font-size: 13px; background: transparent;")
        excel_row.addWidget(self.btn_excel)
        excel_row.addWidget(self.excel_label, 1)
        file_inner.addLayout(excel_row)

        output_row = QHBoxLayout()
        self.btn_output = QPushButton("选择输出目录...")
        self.btn_output.setStyleSheet("""
            QPushButton { background: #F3F4F6; border: 1px solid #E5E7EB; border-radius: 10px;
                padding: 12px 20px; font-size: 14px; color: #333; }
            QPushButton:hover { background: #E5E7EB; }
        """)
        self.btn_output.setCursor(Qt.PointingHandCursor)
        self.btn_output.clicked.connect(self._select_output)
        self.output_label = QLabel("未选择目录")
        self.output_label.setStyleSheet("color: #999; font-size: 13px; background: transparent;")
        output_row.addWidget(self.btn_output)
        output_row.addWidget(self.output_label, 1)
        file_inner.addLayout(output_row)

        layout.addWidget(file_card)
        layout.addSpacing(24)

        # === 启动按钮 ===
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.btn_start = QPushButton("🚀 开始执行任务")
        self.btn_start.setStyleSheet("""
            QPushButton {
                background-color: #6366F1; color: #FFFFFF; border-radius: 12px;
                padding: 14px 40px; font-size: 16px; font-weight: bold; border: none;
            }
            QPushButton:hover { background-color: #4F46E5; }
            QPushButton:disabled { background-color: #CCCCCC; }
        """)
        self.btn_start.setCursor(Qt.PointingHandCursor)
        self.btn_start.clicked.connect(self._start_task)
        btn_row.addWidget(self.btn_start)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        layout.addStretch()

        scroll.setWidget(content)
        wrapped = QVBoxLayout(page)
        wrapped.setContentsMargins(0, 0, 0, 0)
        wrapped.addWidget(scroll)
        return page

    # ---- 事件处理 ----

    def _on_model_changed(self, model_name):
        if model_name not in MODEL_CONFIG:
            return
        config = MODEL_CONFIG[model_name]
        self.combo_ar.clear()
        self.combo_ar.addItems(config["ratios"])
        self.combo_size.clear()
        self.combo_size.addItems(config["sizes"])

    def _update_api_status(self):
        if self.main_window and self.main_window.settings_manager.has_visual_key():
            self._api_status_label.setText("✅ 已配置（来自全局设置）")
            self._api_status_label.setStyleSheet(
                "font-size: 13px; color: #10B981; background: transparent; padding: 6px 0;")
        else:
            self._api_status_label.setText("⚠️ 未配置，请点击侧边栏 ⚙️ 设置进行配置")
            self._api_status_label.setStyleSheet(
                "font-size: 13px; color: #F59E0B; background: transparent; padding: 6px 0;")

    def on_activate(self):
        self._update_api_status()

    def _select_excel(self):
        file, _ = QFileDialog.getOpenFileName(
            self.main_window, "选择包含提示词的 Excel 文件", "",
            "Excel Files (*.xlsx *.xls)")
        if file:
            self.excel_path = file
            self.excel_label.setText(f"✅ {os.path.basename(file)}")
            self.excel_label.setStyleSheet(
                "color: #333; font-size: 13px; background: transparent;")

    def _select_output(self):
        folder = QFileDialog.getExistingDirectory(self.main_window, "选择保存目录")
        if folder:
            self.output_path = folder
            self.output_label.setText(f"✅ {folder}")
            self.output_label.setStyleSheet(
                "color: #333; font-size: 13px; background: transparent;")

    def _start_task(self):
        if self._worker and self._worker.isRunning():
            QMessageBox.information(self.main_window, "提示", "有任务正在运行，请先终止或等待完成")
            return
        api_key = self.main_window.settings_manager.get_visual_key()
        if not api_key:
            QMessageBox.warning(self.main_window, "提示",
                "未配置视觉模型 API Key！请点击侧边栏 ⚙️ 设置进行配置")
            return
        if not self.excel_path:
            QMessageBox.warning(self.main_window, "提示", "请选择需要处理的 Excel 文件！")
            return
        if not self.output_path:
            QMessageBox.warning(self.main_window, "提示", "请选择图片保存的输出目录！")
            return

        model = self.combo_model.currentText()
        ar = self.combo_ar.currentText()
        size = self.combo_size.currentText()
        poll_interval = self.spin_poll.value()
        concurrency = self.spin_concurrency.value()

        self._worker = BatchDrawWorker(
            api_key, self.excel_path, self.output_path, model, ar, size,
            poll_interval, concurrency)
        self._worker.log_msg.connect(self._on_worker_log)
        self._worker.progress_update.connect(self._on_worker_progress)
        self._worker.finished_task.connect(self._on_worker_finished)

        # 切换到监控台
        mw = self.main_window
        mw.monitor_clear()
        mw.monitor_set_running(True)
        mw.stop_requested.connect(self._stop_task)
        mw.switch_to_monitor()

        self.btn_start.setDisabled(True)
        self._worker.start()

    def _on_worker_log(self, text):
        self.main_window.monitor_log(text)

    def _on_worker_progress(self, current, total):
        self.main_window.monitor_progress(current, total)

    def _on_worker_finished(self, success):
        self.main_window.monitor_set_running(False)
        self.btn_start.setDisabled(False)
        try:
            self.main_window.stop_requested.disconnect(self._stop_task)
        except TypeError:
            pass
        if success:
            QMessageBox.information(self.main_window, "完成", "所有任务已处理完毕！")

    def stop(self):
        if self._worker and self._worker.isRunning():
            self._worker.stop()

    def _stop_task(self):
        self.stop()
