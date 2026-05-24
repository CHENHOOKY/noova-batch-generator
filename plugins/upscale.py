"""图像放大插件 —— 基于 ONNX Runtime + Real-ESRGAN 深度超分模型

本地 AI 超分，纯 CPU 运行，无需 GPU。模型约 4.87 MB，首次自动下载。
选择图片文件夹 → 逐张超分放大 → 保持原文件名输出。
Real-ESRGAN 与 ComfyUI 同系列，4x 全通道 RGB 超分，效果远超 ESPCN。

删除此文件不会影响主程序及其他插件。
"""

import os
import urllib.request
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QScrollArea,
    QLabel, QPushButton, QComboBox, QFileDialog, QMessageBox,
    QProgressBar, QTextEdit,
)
from PySide6.QtCore import Qt, QThread, Signal

from plugin_base import BasePlugin

SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"}

# ONNX 模型信息 (Real-ESRGAN-General-x4v3, Qualcomm AI Hub)
MODEL_FILENAME = "real_esrgan_general_x4v3.onnx"
MODEL_URL = (
    "https://qaihub-public-assets.s3.us-west-2.amazonaws.com/"
    "qai-hub-models/models/real_esrgan_general_x4v3/"
    "releases/v0.54.0/real_esrgan_general_x4v3-onnx-float.zip"
)
TILE_SIZE = 128       # 模型固定输入大小
TILE_OVERLAP = 16     # 分块重叠像素（用于边缘平滑）
SCALE_FACTOR = 4      # 模型固定放大倍数


def scan_images(folder: str) -> list[str]:
    """扫描文件夹中所有支持的图片文件，按文件名排序"""
    result = []
    try:
        for fname in sorted(os.listdir(folder)):
            if os.path.splitext(fname)[1].lower() in SUPPORTED_EXTS:
                result.append(os.path.join(folder, fname))
    except OSError:
        pass
    return result


def find_or_download_model(log_callback=None) -> str | None:
    """查找或下载 ONNX 模型文件（Qualcomm Real-ESRGAN, ZIP 包）"""
    model_dir = Path(__file__).parent.parent / "models"
    model_path = model_dir / MODEL_FILENAME

    if model_path.exists() and model_path.stat().st_size > 1000:
        return str(model_path)

    model_dir.mkdir(parents=True, exist_ok=True)
    if log_callback:
        log_callback(f"正在下载 AI 超分模型 ({MODEL_FILENAME}, ~4.5 MB)...")
    try:
        import io, zipfile

        req = urllib.request.Request(
            MODEL_URL, headers={'User-Agent': 'NoovaApp/2.0'})
        with urllib.request.urlopen(req, timeout=60) as resp:
            zip_data = resp.read()

        if len(zip_data) < 10000:
            if log_callback:
                log_callback("[FAIL] 模型文件下载无效")
            return None

        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
            # ZIP 内结构: real_esrgan_general_x4v3-onnx-float/*.onnx + *.data
            for name in zf.namelist():
                basename = Path(name).name
                if basename:
                    # 解压到 models/ 目录
                    dest = model_dir / basename
                    with zf.open(name) as src, open(dest, 'wb') as dst:
                        dst.write(src.read())
                    if log_callback:
                        log_callback(f"  解压: {basename}")

        if log_callback:
            log_callback(f"[OK] 模型下载完成 (~{len(zip_data) // 1024} KB)")

        # 清理旧版 ESPCN 模型
        old_model = model_dir / "super-resolution-10.onnx"
        if old_model.exists():
            old_model.unlink(missing_ok=True)
        return str(model_path)
    except Exception as e:
        if log_callback:
            log_callback(f"[FAIL] 模型下载失败: {e}")
        if model_path.exists():
            model_path.unlink(missing_ok=True)
        return None


class UpscaleWorker(QThread):
    """后台批量 AI 超分工作线程（分块 ONNX 推理）"""

    log_msg = Signal(str)
    progress_update = Signal(int, int)
    finished_task = Signal(bool)

    def __init__(self, image_files: list[str], output_dir: str,
                 output_format: str = "png"):
        super().__init__()
        self.image_files = image_files
        self.output_dir = output_dir
        self.output_format = output_format
        self.is_running = True

    def stop(self):
        self.is_running = False

    def _process_tiled(self, sess, input_name, output_name, rgb_image):
        """分块处理 RGB 图像：切成 128x128 块 → ONNX 推理 → 拼接为 4x 放大结果

        rgb_image: H×W×3 float32, range [0,1], RGB order
        返回: (H*4)×(W*4)×3 float32, range [0,1]
        """
        h, w = rgb_image.shape[:2]
        tile = TILE_SIZE
        overlap = TILE_OVERLAP
        stride = tile - overlap

        # 小图 padding 到至少 TILE_SIZE
        pad_h = max(0, tile - h)
        pad_w = max(0, tile - w)
        padded = np.pad(rgb_image, ((0, pad_h), (0, pad_w), (0, 0)),
                        mode='reflect')
        ph, pw = padded.shape[:2]

        out_h, out_w = h * SCALE_FACTOR, w * SCALE_FACTOR
        out_tile = tile * SCALE_FACTOR

        result = np.zeros((ph * SCALE_FACTOR, pw * SCALE_FACTOR, 3),
                          dtype=np.float32)
        weight = np.zeros((ph * SCALE_FACTOR, pw * SCALE_FACTOR, 3),
                          dtype=np.float32)

        mask = np.ones((out_tile, out_tile, 1), dtype=np.float32)
        fade = overlap * SCALE_FACTOR
        if fade > 0:
            for i in range(fade):
                alpha = (i + 1) / (fade + 1)
                mask[i, :, 0] *= alpha
                mask[-1 - i, :, 0] *= alpha
                mask[:, i, 0] *= alpha
                mask[:, -1 - i, 0] *= alpha

        for y in range(0, ph, stride):
            for x in range(0, pw, stride):
                if not self.is_running:
                    return result[:out_h, :out_w]

                y0 = min(y, ph - tile)
                x0 = min(x, pw - tile)

                patch = padded[y0:y0 + tile, x0:x0 + tile]  # (128,128,3)
                # HWC → NCHW: (1, 3, 128, 128)
                patch_nchw = np.transpose(patch, (2, 0, 1))[np.newaxis, :, :, :]

                out = sess.run([output_name], {input_name: patch_nchw})
                # NCHW → HWC: (512, 512, 3)
                out_patch = np.transpose(out[0][0], (1, 2, 0))

                out_y0 = y0 * SCALE_FACTOR
                out_x0 = x0 * SCALE_FACTOR
                result[out_y0:out_y0 + out_tile,
                       out_x0:out_x0 + out_tile] += out_patch * mask
                weight[out_y0:out_y0 + out_tile,
                       out_x0:out_x0 + out_tile] += mask

        weight[weight < 1e-6] = 1.0
        result /= weight
        return result[:out_h, :out_w]

    def run(self):
        total = len(self.image_files)
        if total == 0:
            self.log_msg.emit("没有找到可处理的图片文件。")
            self.finished_task.emit(False)
            return

        try:
            # 加载模型
            model_path = find_or_download_model(self.log_msg.emit)
            if not model_path:
                self.log_msg.emit("无法获取 AI 超分模型，请检查网络连接后重试")
                self.finished_task.emit(False)
                return

            self.log_msg.emit("正在加载 AI 超分模型...")
            sess = ort.InferenceSession(
                model_path,
                providers=['CPUExecutionProvider'])
            inp = sess.get_inputs()[0]
            out = sess.get_outputs()[0]
            self.log_msg.emit(
                f"模型已加载 (Real-ESRGAN, {SCALE_FACTOR}x 放大, "
                f"分块 {TILE_SIZE}x{TILE_SIZE})")

            os.makedirs(self.output_dir, exist_ok=True)
            self.progress_update.emit(0, total)

            for idx, img_path in enumerate(self.image_files):
                if not self.is_running:
                    self.log_msg.emit("任务已取消")
                    self.finished_task.emit(False)
                    return

                fname = os.path.basename(img_path)
                self.log_msg.emit(f"[{idx + 1}/{total}] {fname}")

                try:
                    # 读取图像（使用 numpy 绕过 cv2.imread 的 Unicode 路径问题）
                    raw = np.fromfile(img_path, dtype=np.uint8)
                    if len(raw) == 0:
                        self.log_msg.emit(f"  [FAIL] 无法读取图像文件（空文件）")
                        self.progress_update.emit(idx + 1, total)
                        continue
                    img = cv2.imdecode(raw, cv2.IMREAD_COLOR)
                    if img is None:
                        self.log_msg.emit(f"  [FAIL] 无法解码图像文件")
                        self.progress_update.emit(idx + 1, total)
                        continue

                    h, w = img.shape[:2]
                    self.log_msg.emit(
                        f"  原始: {w}x{h} → AI {SCALE_FACTOR}x 超分")

                    # BGR → RGB，归一化到 [0, 1]
                    img_rgb = cv2.cvtColor(
                        img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0

                    # AI 超分全通道 RGB
                    result_rgb = self._process_tiled(
                        sess, inp.name, out.name, img_rgb)

                    # 还原到 [0, 255] uint8 BGR
                    new_h, new_w = h * SCALE_FACTOR, w * SCALE_FACTOR
                    result_rgb = np.clip(
                        result_rgb * 255.0, 0, 255).astype(np.uint8)
                    result_bgr = cv2.cvtColor(result_rgb, cv2.COLOR_RGB2BGR)

                    # 保存（使用 numpy 绕过 cv2.imwrite 的 Unicode 路径问题）
                    out_path = os.path.join(self.output_dir, fname)
                    if self.output_format == "jpg":
                        ok, buf = cv2.imencode('.jpg', result_bgr,
                                               [cv2.IMWRITE_JPEG_QUALITY, 95])
                    elif self.output_format == "webp":
                        ok, buf = cv2.imencode('.webp', result_bgr,
                                               [cv2.IMWRITE_WEBP_QUALITY, 95])
                    else:
                        ok, buf = cv2.imencode('.png', result_bgr,
                                               [cv2.IMWRITE_PNG_COMPRESSION, 3])
                    if ok:
                        buf.tofile(out_path)
                    else:
                        raise RuntimeError("图像编码失败")

                    self.log_msg.emit(
                        f"  [OK] {w}x{h} → {new_w}x{new_h}，已保存")
                except Exception as e:
                    self.log_msg.emit(f"  [FAIL] 处理异常: {e}")

                self.progress_update.emit(idx + 1, total)

            self.log_msg.emit(
                f"\n全部完成！共处理 {total} 张图片，输出至 {self.output_dir}")
            self.finished_task.emit(True)

        except Exception as e:
            self.log_msg.emit(f"系统错误: {e}")
            self.finished_task.emit(False)


class UpscalePlugin(BasePlugin):
    """图像放大插件 —— ONNX AI 超分模型，零 GPU 依赖"""

    plugin_id = "upscale"
    name = "图像放大"
    icon = "🔍"
    color = "#10B981"
    description = ("AI 深度学习图像超分放大，基于 Real-ESRGAN 模型。\n"
                   "与 ComfyUI 同系列，纯 CPU 运行，模型约 4.87 MB，首次自动下载。")

    def __init__(self):
        super().__init__()
        self._worker: UpscaleWorker | None = None
        self._input_folder: str = ""
        self._output_dir: str = ""
        self._image_files: list[str] = []

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

        # 顶栏
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

        # 标题
        title = QLabel(f"{self.icon} {self.name}")
        title.setStyleSheet(
            "font-size: 28px; font-weight: 700; color: #1E1E2E; background: transparent;")
        subtitle = QLabel(
            "AI 深度学习超分模型 (Real-ESRGAN)，与 ComfyUI 同系列，纯 CPU 运行，模型约 4.87 MB，首次自动下载")
        subtitle.setStyleSheet("font-size: 14px; color: #6B7280; background: transparent;")
        outer.addWidget(title)
        outer.addWidget(subtitle)
        outer.addSpacing(24)

        # 主区域：左设置 + 右日志
        main_row = QHBoxLayout()
        main_row.setSpacing(24)

        # ===== 左侧：设置面板 =====
        left_panel = QFrame()
        left_panel.setFixedWidth(380)
        left_panel.setStyleSheet(
            "QFrame#SettingsPanel { background-color: #FFFFFF; border: 1px solid #ECEDF0; "
            "border-radius: 14px; }")
        left_panel.setObjectName("SettingsPanel")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(24, 24, 24, 24)
        left_layout.setSpacing(18)

        ss = "font-size: 14px; font-weight: bold; color: #333; background: transparent;"

        # 图片文件夹
        l1 = QLabel("📁 图片文件夹"); l1.setStyleSheet(ss)
        left_layout.addWidget(l1)

        src_row = QHBoxLayout()
        self._folder_label = QLabel("未选择")
        self._folder_label.setStyleSheet(
            "color: #AAA; font-size: 12px; background: transparent; "
            "padding: 8px 12px; border: 1px solid #EEE; border-radius: 8px;")
        self._folder_label.setWordWrap(True)
        self._folder_label.setMinimumHeight(40)
        src_row.addWidget(self._folder_label, 1)

        src_btn = QPushButton("选择")
        src_btn.setFixedWidth(64)
        src_btn.setStyleSheet(
            "QPushButton { background-color: #F3F4F6; border: 1px solid #E5E7EB; "
            "border-radius: 8px; padding: 8px; color: #555; font-size: 13px; }"
            "QPushButton:hover { background-color: #E5E7EB; }")
        src_btn.setCursor(Qt.PointingHandCursor)
        src_btn.clicked.connect(self._pick_input_folder)
        src_row.addWidget(src_btn)
        left_layout.addLayout(src_row)

        # 输出目录
        l2 = QLabel("📂 输出目录"); l2.setStyleSheet(ss)
        left_layout.addWidget(l2)

        out_row = QHBoxLayout()
        self._output_label = QLabel("未选择")
        self._output_label.setStyleSheet(
            "color: #AAA; font-size: 12px; background: transparent; "
            "padding: 8px 12px; border: 1px solid #EEE; border-radius: 8px;")
        self._output_label.setWordWrap(True)
        self._output_label.setMinimumHeight(40)
        out_row.addWidget(self._output_label, 1)

        out_btn = QPushButton("选择")
        out_btn.setFixedWidth(64)
        out_btn.setStyleSheet(
            "QPushButton { background-color: #F3F4F6; border: 1px solid #E5E7EB; "
            "border-radius: 8px; padding: 8px; color: #555; font-size: 13px; }"
            "QPushButton:hover { background-color: #E5E7EB; }")
        out_btn.setCursor(Qt.PointingHandCursor)
        out_btn.clicked.connect(self._pick_output_dir)
        out_row.addWidget(out_btn)
        left_layout.addLayout(out_row)

        # 放大倍数（固定 4x + 可选二次缩放）
        l3 = QLabel("📏 放大倍数"); l3.setStyleSheet(ss)
        left_layout.addWidget(l3)

        self._scale_combo = QComboBox()
        self._scale_combo.addItems([
            f"AI 超分 4x（原始）",
            f"AI 超分 4x → 二次缩放至 2x",
            f"AI 超分 4x → 二次缩放至 3x",
        ])
        self._scale_combo.setCurrentIndex(0)
        self._scale_combo.setStyleSheet(
            "QComboBox { padding: 10px; border: 1px solid #E5E7EB; border-radius: 8px; "
            "font-size: 14px; background-color: #FFFFFF; }"
            "QComboBox:focus { border: 1px solid #10B981; }")
        left_layout.addWidget(self._scale_combo)

        # 输出格式
        l4 = QLabel("🎨 输出格式"); l4.setStyleSheet(ss)
        left_layout.addWidget(l4)

        self._format_combo = QComboBox()
        self._format_combo.addItems(["png", "jpg", "webp"])
        self._format_combo.setCurrentIndex(0)
        self._format_combo.setStyleSheet(
            "QComboBox { padding: 10px; border: 1px solid #E5E7EB; border-radius: 8px; "
            "font-size: 14px; background-color: #FFFFFF; }"
            "QComboBox:focus { border: 1px solid #10B981; }")
        left_layout.addWidget(self._format_combo)

        left_layout.addSpacing(8)

        # 按钮区
        btn_row = QHBoxLayout()
        self._btn_start = QPushButton("🚀 开始 AI 放大")
        self._btn_start.setStyleSheet(
            "QPushButton { background-color: #10B981; color: white; border: none; "
            "border-radius: 10px; padding: 12px 20px; font-size: 15px; font-weight: bold; }"
            "QPushButton:hover { background-color: #059669; }"
            "QPushButton:disabled { background-color: #D1D5DB; }")
        self._btn_start.setCursor(Qt.PointingHandCursor)
        self._btn_start.clicked.connect(self._start_upscale)
        btn_row.addWidget(self._btn_start, 1)

        self._btn_cancel = QPushButton("终止")
        self._btn_cancel.setStyleSheet(
            "QPushButton { background-color: #FEE2E2; color: #EF4444; "
            "border: 1px solid #FECACA; border-radius: 10px; padding: 12px 16px; "
            "font-size: 14px; }"
            "QPushButton:hover { background-color: #FECACA; }")
        self._btn_cancel.setCursor(Qt.PointingHandCursor)
        self._btn_cancel.clicked.connect(self._cancel)
        self._btn_cancel.setVisible(False)
        btn_row.addWidget(self._btn_cancel)
        left_layout.addLayout(btn_row)

        # 进度条
        self._progress_bar = QProgressBar()
        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(False)
        self._progress_bar.setStyleSheet(
            "QProgressBar { border: none; background-color: #EEEEF2;"
            " border-radius: 6px; height: 8px; }"
            "QProgressBar::chunk { background-color: #10B981; border-radius: 6px; }")
        left_layout.addWidget(self._progress_bar)

        self._info_label = QLabel("")
        self._info_label.setStyleSheet(
            "font-size: 13px; color: #888; background: transparent;")
        self._info_label.setWordWrap(True)
        left_layout.addWidget(self._info_label)

        left_layout.addStretch()
        main_row.addWidget(left_panel)

        # ===== 右侧：日志区域 =====
        right_panel = QFrame()
        right_panel.setStyleSheet(
            "QFrame#LogPanel { background-color: #FFFFFF; border: 1px solid #ECEDF0; "
            "border-radius: 14px; }")
        right_panel.setObjectName("LogPanel")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(20, 20, 20, 20)
        right_layout.setSpacing(12)

        log_header = QHBoxLayout()
        log_lbl = QLabel("📋 处理日志")
        log_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #1E1E2E; background: transparent;")
        log_header.addWidget(log_lbl)
        log_header.addStretch()

        self._btn_open_output = QPushButton("📂 打开输出目录")
        self._btn_open_output.setStyleSheet(
            "QPushButton { background: #F3F4F6; border: 1px solid #E5E7EB; "
            "border-radius: 8px; padding: 8px 14px; font-size: 12px; color: #333; }"
            "QPushButton:hover { background: #E5E7EB; }")
        self._btn_open_output.setCursor(Qt.PointingHandCursor)
        self._btn_open_output.clicked.connect(self._open_output_dir)
        self._btn_open_output.setVisible(False)
        log_header.addWidget(self._btn_open_output)
        right_layout.addLayout(log_header)

        self._log_area = QTextEdit()
        self._log_area.setReadOnly(True)
        self._log_area.setStyleSheet(
            "QTextEdit { border: 1px solid #ECEDF0; border-radius: 10px; "
            "padding: 10px; background-color: #FAFAFA; font-size: 13px; }")
        right_layout.addWidget(self._log_area, 1)

        main_row.addWidget(right_panel, 1)
        outer.addLayout(main_row)
        outer.addStretch()

        scroll.setWidget(content)
        wrap = QVBoxLayout(page)
        wrap.setContentsMargins(0, 0, 0, 0)
        wrap.addWidget(scroll)

        return page

    # ═══════════════════════════════════════
    #  事件处理
    # ═══════════════════════════════════════

    def _pick_input_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self._workspace, "选择图片文件夹")
        if folder:
            self._input_folder = folder
            self._image_files = scan_images(folder)
            count = len(self._image_files)
            self._folder_label.setText(f"{folder}  ({count} 张图片)")
            self._folder_label.setStyleSheet(
                "color: #10B981; font-size: 12px; font-weight: 500; background: transparent; "
                "padding: 8px 12px; border: 1px solid #10B981; border-radius: 8px;")

    def _pick_output_dir(self):
        folder = QFileDialog.getExistingDirectory(
            self._workspace, "选择输出目录")
        if folder:
            self._output_dir = folder
            self._output_label.setText(folder)
            self._output_label.setStyleSheet(
                "color: #10B981; font-size: 12px; font-weight: 500; background: transparent; "
                "padding: 8px 12px; border: 1px solid #10B981; border-radius: 8px;")

    # ═══════════════════════════════════════
    #  任务控制
    # ═══════════════════════════════════════

    def _start_upscale(self):
        if not self._input_folder or not self._image_files:
            QMessageBox.warning(self._workspace, "提示",
                                "请先选择包含图片的文件夹")
            return
        if not self._output_dir:
            QMessageBox.warning(self._workspace, "提示", "请先选择输出目录")
            return
        if self._worker and self._worker.isRunning():
            QMessageBox.information(self._workspace, "提示",
                                    "有任务正在运行，请先终止或等待完成")
            return

        fmt = self._format_combo.currentText()

        self._worker = UpscaleWorker(
            self._image_files.copy(), self._output_dir, fmt)
        self._worker.log_msg.connect(self._log)
        self._worker.progress_update.connect(self._on_progress)
        self._worker.finished_task.connect(self._on_finished)

        # 连接共享监视器停止信号
        mw = self.main_window
        if mw:
            try:
                mw.stop_requested.connect(self._cancel)
            except (TypeError, RuntimeError):
                pass

        self._btn_start.setVisible(False)
        self._btn_cancel.setVisible(True)
        self._progress_bar.setVisible(True)
        self._progress_bar.setValue(0)
        self._log_area.clear()
        self._info_label.setText("")

        self._worker.start()

    def _cancel(self):
        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(100)
        # 断开共享监视器
        mw = self.main_window
        if mw:
            try:
                mw.stop_requested.disconnect(self._cancel)
            except (TypeError, RuntimeError):
                pass
        self._reset_ui()

    def _log(self, text: str):
        self._log_area.append(text)
        sb = self._log_area.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_progress(self, current: int, total: int):
        self._progress_bar.setMaximum(total)
        self._progress_bar.setValue(current)
        self._info_label.setText(f"处理进度：{current} / {total}")

    def _on_finished(self, success: bool):
        # 断开共享监视器
        mw = self.main_window
        if mw:
            try:
                mw.stop_requested.disconnect(self._cancel)
            except (TypeError, RuntimeError):
                pass
        self._reset_ui()
        if success:
            self._btn_open_output.setVisible(True)
            self._info_label.setText("AI 超分完成！")

    def _open_output_dir(self):
        if self._output_dir and os.path.exists(self._output_dir):
            os.startfile(self._output_dir)

    def _reset_ui(self):
        self._btn_start.setVisible(True)
        self._btn_cancel.setVisible(False)
        self._progress_bar.setVisible(False)
