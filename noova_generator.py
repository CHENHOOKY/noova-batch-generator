import os
import sys
import time
import threading
import requests
import pandas as pd
from typing import List, Dict, Tuple

# 引入 PySide6 核心组件
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QStackedWidget, QLineEdit,
    QComboBox, QFileDialog, QTextEdit, QProgressBar, QFormLayout,
    QGraphicsDropShadowEffect, QMessageBox, QSpinBox, QScrollArea, QGridLayout
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QIcon, QColor

# ==========================================
# 模块 1: API 通信与数据处理模块 (保持核心逻辑稳定)
# ==========================================
class NoovaAPI:
    BASE_URL = "https://noova.cn"
    
    def __init__(self, api_key: str):
        self.api_key = api_key.strip()
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def local_file_to_base64(self, filepath: str, log_callback=None) -> str:
        """将本地图片转为 base64 字符串，可直接作为 API 的 urls 参数"""
        import base64
        import io
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"本地文件不存在: {filepath}")

        try:
            from PIL import Image
            img = Image.open(filepath)
            fmt = img.format
            if log_callback:
                log_callback(f"  -> 图片格式: {fmt}, 尺寸: {img.size}")

            # 转为 RGB 模式
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGB")

            # 过大图片先缩放到 2K 以内
            max_dim = 2048
            w, h = img.size
            if max(w, h) > max_dim:
                ratio = max_dim / max(w, h)
                img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
                if log_callback:
                    log_callback(f"  -> 已缩放至: {img.size}")

            buf = io.BytesIO()
            img.save(buf, format="PNG")
            b64_str = base64.b64encode(buf.getvalue()).decode("utf-8")
            if log_callback:
                log_callback(f"  -> base64 编码完成, 长度: {len(b64_str)}")
            return b64_str
        except ImportError:
            # PIL 不可用，回退为直接读取文件二进制
            with open(filepath, "rb") as f:
                raw = f.read()
            return base64.b64encode(raw).decode("utf-8")

    def create_draw_task(self, model: str, prompt: str, aspect_ratio: str, image_size: str, urls: List[str]) -> Tuple[str, dict]:
        payload = {"model": model, "prompt": prompt, "imageSize": image_size, "aspectRatio": aspect_ratio}
        if urls: payload["urls"] = urls

        create_url = f"{self.BASE_URL}/v1/draw/completions"
        resp = requests.post(create_url, headers=self.headers, json=payload, timeout=60)
        resp.raise_for_status()
        try:
            created = resp.json()
        except Exception:
            raise RuntimeError(f"API 返回非 JSON 内容 (status={resp.status_code}): {resp.text[:500]}")
        data = created.get("data") or {}
        task_id = data.get("id")
        if not task_id:
            raise RuntimeError(f"未返回任务 ID: {created}")
        return task_id, created

    def poll_task_result(self, task_id: str, poll_interval: int, log_callback) -> dict:
        poll_url = f"{self.BASE_URL}/v1/draw/result"
        for _ in range(180):
            time.sleep(poll_interval)
            for retry in range(3):
                try:
                    resp = requests.post(poll_url, headers=self.headers, json={"id": task_id}, timeout=60)
                    resp.raise_for_status()
                    break
                except requests.exceptions.HTTPError as e:
                    if e.response is not None and e.response.status_code == 429:
                        wait = 2 ** (retry + 1)
                        log_callback(f"请求过于频繁，{wait}s 后重试...")
                        time.sleep(wait)
                        continue
                    raise
            else:
                raise RuntimeError("轮询请求连续失败：429 限流")

            try:
                current = resp.json()
            except Exception:
                raise RuntimeError(f"轮询 API 返回非 JSON 内容 (status={resp.status_code}): {resp.text[:500]}")

            data = current.get("data") or {}
            status = str(data.get("status") or "")
            progress = data.get("progress", 0)
            log_callback(f"任务状态: {status} (进度: {progress}%)")

            if status in {"succeeded", "failed", "violation", "cancelled"}:
                break
        return current

    def download_image(self, url: str, save_path: str):
        resp = requests.get(url, stream=True)
        resp.raise_for_status()
        with open(save_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

class ExcelProcessor:
    @staticmethod
    def extract_dispimg_from_zip(filepath: str, extract_dir: str) -> Dict[str, str]:
        """底层解压提取 WPS 等内嵌公式图片 (DISPIMG)"""
        dispimg_mapping = {}
        try:
            import zipfile
            from xml.etree import ElementTree as ET
            if not zipfile.is_zipfile(filepath): return dispimg_mapping
            
            with zipfile.ZipFile(filepath, 'r') as z:
                namelist = z.namelist()
                # 检查是否存在底层图片配置库
                if 'xl/cellimages.xml' in namelist and 'xl/_rels/cellimages.xml.rels' in namelist:
                    rels_xml = z.read('xl/_rels/cellimages.xml.rels')
                    rels_root = ET.fromstring(rels_xml)
                    # 建立 rId 到图片路径的映射
                    rels_map = {rel.attrib.get('Id'): rel.attrib.get('Target') for rel in rels_root}
                        
                    cellimg_xml = z.read('xl/cellimages.xml')
                    cellimg_root = ET.fromstring(cellimg_xml)
                    
                    for pic in cellimg_root.iter():
                        if pic.tag.endswith('pic'):
                            name_attr = embed_attr = None
                            for elem in pic.iter():
                                if elem.tag.endswith('cNvPr'): name_attr = elem.attrib.get('name')
                                if elem.tag.endswith('blip'):
                                    for k, v in elem.attrib.items():
                                        if k.endswith('embed'): embed_attr = v
                                            
                            if name_attr and embed_attr and embed_attr in rels_map:
                                target = rels_map[embed_attr]
                                target_path = target[1:] if target.startswith('/') else f"xl/{target}"
                                if target_path in namelist:
                                    ext = os.path.splitext(target_path)[1]
                                    save_path = os.path.join(extract_dir, f"{name_attr}{ext}")
                                    with open(save_path, 'wb') as f:
                                        f.write(z.read(target_path))
                                    dispimg_mapping[name_attr] = save_path
        except Exception as e:
            print(f"提取 cellimages 失败: {e}")
        return dispimg_mapping

    @staticmethod
    def extract_floating_images(filepath: str, extract_dir: str) -> Dict[int, List[str]]:
        """使用 openpyxl 提取常规的悬浮/插入图片，并映射到所在行"""
        floating_mapping = {}
        try:
            import openpyxl
            wb = openpyxl.load_workbook(filepath, data_only=True)
            ws = wb.active
            for img in getattr(ws, '_images', []):
                row = img.anchor._from.row + 1 # openpyxl 行索引从 0 开始，Excel 从 1 开始
                
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
            pass # 如果用户没装 Pillow 或表格里没有悬浮图，就静默跳过
        return floating_mapping

    @staticmethod
    def parse_excel(filepath: str, output_dir: str, log_callback) -> List[Dict]:
        import re
        
        # 准备图片提取缓存目录（自动建在你的输出文件夹里）
        extract_dir = os.path.join(output_dir, ".noova_extracted_images")
        os.makedirs(extract_dir, exist_ok=True)
        
        log_callback("🔍 正在深度扫描并提取 Excel 内嵌图片(此过程可能需要几秒钟)...")
        dispimg_mapping = ExcelProcessor.extract_dispimg_from_zip(filepath, extract_dir)
        floating_mapping = ExcelProcessor.extract_floating_images(filepath, extract_dir)
        
        if dispimg_mapping or floating_mapping:
            log_callback(f"✅ 成功提取内嵌图片: {len(dispimg_mapping)} 个内嵌公式图, {sum(len(v) for v in floating_mapping.values())} 个常规悬浮图。")

        df = pd.read_excel(filepath)
        tasks = []
        for index, row in df.iterrows():
            row_num = index + 2
            prompt = str(row.iloc[0]).strip()
            if not prompt or prompt.lower() == 'nan': continue
            
            urls = []
            # 1. 提取 WPS 的 DISPIMG 以及常规路径/URL
            if len(row) > 1:
                for cell in row.iloc[1:10]:
                    val = str(cell).strip()
                    if not val or val.lower() == 'nan': continue
                    
                    # 拦截并翻译 DISPIMG 公式
                    match = re.search(r'DISPIMG\("([^"]+)"', val, re.IGNORECASE)
                    if match:
                        img_id = match.group(1)
                        if img_id in dispimg_mapping:
                            urls.append(dispimg_mapping[img_id]) # 替换成提取出来的本地图片地址
                        else:
                            log_callback(f"⚠️ 警告: 第 {row_num} 行未能从文件底层找到对应的图片 ID: {img_id}")
                    elif val.upper().startswith("=DISPIMG"):
                        # 处理极个别正则未能捕获的残缺公式
                        continue
                    else:
                        urls.append(val)
                        
            # 2. 附加该行附带的悬浮图片
            if row_num in floating_mapping:
                urls.extend(floating_mapping[row_num])
                
            tasks.append({"row_index": row_num, "prompt": prompt, "urls": urls})
        return tasks

# ==========================================
# 模块 2: 后台多线程任务
# ==========================================
class WorkerThread(QThread):
    progress_update = Signal(int, int) # current, total
    log_msg = Signal(str)
    finished_task = Signal(bool)

    def __init__(self, api_key, excel_path, output_dir, model, aspect_ratio, image_size, poll_interval, concurrency):
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
                self.log_msg.emit(f"  [第{row_num}行] 处理本地图片: {os.path.basename(url)} ({fsize} bytes)")
                try:
                    b64_url = api.local_file_to_base64(url, self.log_msg.emit)
                    processed_urls.append(b64_url)
                except Exception as e:
                    self.log_msg.emit(f"  [第{row_num}行] 图片编码失败: {str(e)}")

        if not self.is_running:
            return

        try:
            self.log_msg.emit(f"  [第{row_num}行] 提交绘画任务至 Noova API, 参考图: {len(processed_urls)} 张")
            task_id, _ = api.create_draw_task(
                self.model, prompt, self.aspect_ratio, self.image_size, processed_urls
            )

            result_data = api.poll_task_result(task_id, self.poll_interval, self.log_msg.emit)
            status = str((result_data.get("data") or {}).get("status") or "")

            if status == "succeeded":
                results = (result_data.get("data") or {}).get("results", [])
                if results:
                    final_img_url = results[0].get("url")
                    safe_prompt = "".join([c for c in prompt[:10] if c.isalnum()]).rstrip()
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

            tasks = ExcelProcessor.parse_excel(self.excel_path, self.output_dir, self.log_msg.emit)
            self._total = len(tasks)
            self.log_msg.emit(f"成功解析到 {self._total} 个任务。")

            if self._total == 0:
                self.log_msg.emit("没有找到有效的任务数据，请检查 Excel 格式。")
                self.finished_task.emit(False)
                return

            self.log_msg.emit(f"并发数: {self.concurrency}")

            from concurrent.futures import ThreadPoolExecutor, as_completed
            with ThreadPoolExecutor(max_workers=self.concurrency) as executor:
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
            self.finished_task.emit(True)
        except Exception as e:
            self.log_msg.emit(f"\n系统发生错误: {str(e)}")
            self.finished_task.emit(False)

    def stop(self):
        self.is_running = False


# ==========================================
# 模块 3: UI 界面 (现代 Web 极简风格)
# ==========================================
class ModernWebUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Noova AI 批量出图助手")
        self.resize(1000, 700)
        self.setMinimumSize(900, 600)
        
        # 整体样式表
        self.setStyleSheet("""
            QMainWindow { background-color: #F9FAFB; }
            QWidget#Sidebar { background-color: #FFFFFF; border-right: 1px solid #EBEBEB; }
            QPushButton.NavBtn {
                text-align: left; padding: 12px 20px; border: none;
                border-radius: 8px; font-size: 14px; color: #555555; font-weight: 500;
            }
            QPushButton.NavBtn:hover { background-color: #F5F5F5; }
            QPushButton.NavBtn:checked { background-color: #EEEEFF; font-weight: bold; color: #6366F1; }

            QTextEdit { border: 1px solid #EBEBEB; border-radius: 12px; padding: 10px; background-color: #FAFAFA; font-size: 13px;}
            QProgressBar { border: none; background-color: #F0F0F0; border-radius: 4px; height: 8px; text-align: center; color: transparent; }
            QProgressBar::chunk { background-color: #6366F1; border-radius: 4px; }

            QLineEdit, QComboBox {
                padding: 10px; border: 1px solid #E5E7EB; border-radius: 8px; font-size: 14px; background-color: #FFFFFF;
            }
            QLineEdit:focus, QComboBox:focus { border: 1px solid #6366F1; }
            QSpinBox {
                padding: 10px; border: 1px solid #E5E7EB; border-radius: 8px; font-size: 14px; background-color: #FFFFFF;
            }
        """)

        # 主布局：左右分栏
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self._build_sidebar(main_layout)
        self._build_main_area(main_layout)

        # 状态数据
        self.excel_path = ""
        self.output_path = ""
        self.worker = None

    def _build_sidebar(self, parent_layout):
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(220)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(15, 30, 15, 30)
        side_layout.setSpacing(10)

        # Logo / Title
        logo_label = QLabel("✨ Noova AI")
        logo_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #1A1A1A; padding-left: 10px; padding-bottom: 20px;")
        side_layout.addWidget(logo_label)

        # 导航按钮
        self.nav_home = QPushButton("🏠 Noova应用")
        self.nav_home.setCheckable(True)
        self.nav_home.setChecked(True)
        self.nav_home.setProperty("class", "NavBtn")

        self.nav_running = QPushButton("🚀 运行监控台")
        self.nav_running.setCheckable(True)
        self.nav_running.setProperty("class", "NavBtn")
        self.nav_running.hide()

        side_layout.addWidget(self.nav_home)
        side_layout.addWidget(self.nav_running)
        side_layout.addStretch()

        # 版本信息
        ver_label = QLabel("v1.0.0 Desktop")
        ver_label.setStyleSheet("color: #AAAAAA; font-size: 12px; padding-left: 10px;")
        side_layout.addWidget(ver_label)

        parent_layout.addWidget(sidebar)

        # 按钮互斥逻辑
        self.nav_home.clicked.connect(lambda: self._switch_page(0))
        self.nav_running.clicked.connect(lambda: self._switch_page(2))

    def _build_main_area(self, parent_layout):
        self.stacked_widget = QStackedWidget()
        parent_layout.addWidget(self.stacked_widget, 1) # weight=1 占满剩余空间

        self._build_home_page()
        self._build_workspace_page()
        self._build_running_page()

    def _build_home_page(self):
        page = QWidget()
        page.setStyleSheet("background-color: #F9FAFB;")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(60, 50, 60, 50)

        # Hero 区域
        hero = QWidget()
        hero.setStyleSheet("""
            QWidget#Hero {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #1A1A2E, stop:0.5 #16213E, stop:1 #0F3460);
                border-radius: 20px;
            }
        """)
        hero.setObjectName("Hero")
        hero.setFixedHeight(180)
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(40, 35, 40, 35)

        hero_title = QLabel("你好，我是 Noova 助手")
        hero_title.setStyleSheet("font-size: 32px; font-weight: bold; color: #FFFFFF; background: transparent;")
        hero_sub = QLabel("AI 图像生成平台 · 批量处理 · 高效创作")
        hero_sub.setStyleSheet("font-size: 15px; color: rgba(255,255,255,0.7); background: transparent; margin-top: 4px;")
        hero_layout.addWidget(hero_title)
        hero_layout.addWidget(hero_sub)
        hero_layout.addStretch()

        layout.addWidget(hero)
        layout.addSpacing(40)

        # 分区标题
        sec_label = QLabel("功能服务")
        sec_label.setStyleSheet("font-size: 20px; font-weight: bold; color: #1A1A1A;")
        layout.addWidget(sec_label)
        layout.addSpacing(20)

        # 卡片网格
        card_grid = QGridLayout()
        card_grid.setSpacing(20)

        cards_data = [
            {"icon": "🎨", "color": "#6366F1", "title": "批量出图",
             "desc": "导入 Excel 表格，自动解析提示词与参考图，批量调用 AI 模型生成高质量图片。\n支持 gpt-image-2 / nano-banana 全系列模型。"},
            {"icon": "🖼️", "color": "#8B5CF6", "title": "图片编辑",
             "desc": "即将推出\nAI 智能编辑、风格迁移、背景替换等功能"},
            {"icon": "📦", "color": "#EC4899", "title": "资产管理",
             "desc": "即将推出\n统一管理所有生成的图片资产，支持批量导出"},
        ]

        for i, cd in enumerate(cards_data):
            card = self._create_card(cd["icon"], cd["color"], cd["title"], cd["desc"])
            if i == 0:
                card.clicked.connect(lambda: self._switch_page(1))
            card_grid.addWidget(card, i // 3, i % 3)

        layout.addLayout(card_grid)
        layout.addStretch()

        scroll.setWidget(content)
        wrapped = QVBoxLayout(page)
        wrapped.setContentsMargins(0, 0, 0, 0)
        wrapped.addWidget(scroll)
        self.stacked_widget.addWidget(page)

    def _create_card(self, icon, color, title, desc):
        card = QPushButton()
        card.setMinimumHeight(200)
        card.setCursor(Qt.PointingHandCursor)
        card.setStyleSheet(f"""
            QPushButton {{
                background-color: #FFFFFF;
                border: 1px solid #EEEEEE;
                border-radius: 16px;
                text-align: left;
                padding: 0px;
            }}
            QPushButton:hover {{
                border: 1px solid {color};
                background-color: #FAFAFE;
            }}
        """)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(16)
        shadow.setColor(QColor(0, 0, 0, 15))
        shadow.setOffset(0, 2)
        card.setGraphicsEffect(shadow)

        inner = QVBoxLayout(card)
        inner.setContentsMargins(28, 24, 28, 24)
        inner.setSpacing(12)

        # 图标行
        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet(f"font-size: 36px; background: transparent;")
        inner.addWidget(icon_lbl)

        # 标题
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(f"font-size: 18px; font-weight: bold; color: #1A1A1A; background: transparent;")
        inner.addWidget(title_lbl)

        # 描述
        desc_lbl = QLabel(desc)
        desc_lbl.setStyleSheet("font-size: 13px; color: #888888; line-height: 1.6; background: transparent;")
        desc_lbl.setWordWrap(True)
        inner.addWidget(desc_lbl)
        inner.addStretch()

        return card

    def _build_workspace_page(self):
        page = QWidget()
        page.setStyleSheet("background-color: #F9FAFB;")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(60, 40, 60, 50)

        # 返回按钮
        back_btn = QPushButton("← 返回首页")
        back_btn.setStyleSheet("background: transparent; border: none; color: #666; font-size: 14px; padding: 4px 0;")
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.clicked.connect(lambda: self._switch_page(0))
        layout.addWidget(back_btn)
        layout.addSpacing(16)

        # 标题区
        title = QLabel("🎨 批量出图")
        title.setStyleSheet("font-size: 28px; font-weight: bold; color: #1A1A1A; background: transparent;")
        subtitle = QLabel("导入 Excel 文件，自动解析提示词并批量调用 AI 生成图片")
        subtitle.setStyleSheet("font-size: 14px; color: #999; background: transparent;")
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(32)

        # === 设置表单卡片 ===
        form_card = QFrame()
        form_card.setStyleSheet("QFrame { background: #FFFFFF; border-radius: 16px; border: 1px solid #EEEEEE; }")
        form_layout = QFormLayout(form_card)
        form_layout.setContentsMargins(32, 28, 32, 28)
        form_layout.setSpacing(16)
        form_layout.setVerticalSpacing(18)

        self.input_api = QLineEdit()
        self.input_api.setPlaceholderText("在此粘贴您的 sk- 开头的 API Key")
        self.input_api.setEchoMode(QLineEdit.Password)
        self.input_api.setText(os.environ.get("NOOVA_API_KEY", ""))

        self.model_config = {
            "gpt-image-2": {
                "ratios": ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "5:4", "4:5", "21:9", "9:21", "1:2", "2:1"],
                "sizes": ["1K"],
            },
            "nano-banana-pro": {
                "ratios": ["auto", "1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "5:4", "4:5", "21:9"],
                "sizes": ["1K", "2K", "4K"],
            },
            "nano-banana-2": {
                "ratios": ["auto", "1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "5:4", "4:5", "21:9", "1:4", "4:1", "1:8", "8:1"],
                "sizes": ["1K", "2K", "4K"],
            },
            "nano-banana-fast": {
                "ratios": ["auto", "1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "5:4", "4:5", "21:9"],
                "sizes": ["1K", "2K", "4K"],
            },
            "nano-banana": {
                "ratios": ["auto", "1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "5:4", "4:5", "21:9"],
                "sizes": ["1K", "2K", "4K"],
            },
        }

        self.combo_model = QComboBox()
        self.combo_model.addItems(list(self.model_config.keys()))

        self.combo_ar = QComboBox()
        self.combo_size = QComboBox()

        self.spin_poll = QSpinBox()
        self.spin_poll.setMinimum(20)
        self.spin_poll.setMaximum(9999)
        self.spin_poll.setValue(20)
        self.spin_poll.setSuffix(" 秒")

        self.combo_model.currentTextChanged.connect(self._on_model_changed)
        self._on_model_changed(self.combo_model.currentText())

        form_layout.addRow(QLabel("🔑 API Key:"), self.input_api)
        form_layout.addRow(QLabel("🤖 选择模型:"), self.combo_model)
        form_layout.addRow(QLabel("📏 图像比例:"), self.combo_ar)
        form_layout.addRow(QLabel("🖼️ 图像画质:"), self.combo_size)
        form_layout.addRow(QLabel("⏱️ 轮询间隔:"), self.spin_poll)

        self.spin_concurrency = QSpinBox()
        self.spin_concurrency.setMinimum(1)
        self.spin_concurrency.setMaximum(10)
        self.spin_concurrency.setValue(1)
        self.spin_concurrency.setSuffix(" 个任务")
        form_layout.addRow(QLabel("🔀 并发数量:"), self.spin_concurrency)

        layout.addWidget(form_card)
        layout.addSpacing(24)

        # === 文件选择卡片 ===
        file_card = QFrame()
        file_card.setStyleSheet("QFrame { background: #FFFFFF; border-radius: 16px; border: 1px solid #EEEEEE; }")
        file_inner = QVBoxLayout(file_card)
        file_inner.setContentsMargins(32, 24, 32, 24)
        file_inner.setSpacing(16)

        file_title = QLabel("📂 文件设置")
        file_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #1A1A1A; background: transparent;")
        file_inner.addWidget(file_title)

        # Excel 选择行
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

        # 输出目录行
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
        self.stacked_widget.addWidget(page)

    def _build_running_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(60, 60, 60, 60)

        header = QHBoxLayout()
        title = QLabel("运行监控台")
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        
        self.btn_stop = QPushButton("⏹ 终止任务")
        self.btn_stop.setStyleSheet("background-color: #FF4D4F; color: white; border-radius: 8px; padding: 8px 16px; border:none;")
        self.btn_stop.clicked.connect(self._stop_task)
        self.btn_stop.hide()

        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.btn_stop)
        
        layout.addLayout(header)
        layout.addSpacing(20)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        layout.addWidget(self.log_area)

        self.stacked_widget.addWidget(page) # Index 2

    # --- 交互逻辑 ---
    def _on_model_changed(self, model_name):
        if model_name not in self.model_config:
            return
        config = self.model_config[model_name]
        self.combo_ar.clear()
        self.combo_ar.addItems(config["ratios"])
        self.combo_size.clear()
        self.combo_size.addItems(config["sizes"])

    def _switch_page(self, index):
        self.nav_home.setChecked(index == 0)
        self.nav_running.setChecked(index == 2)
        self.stacked_widget.setCurrentIndex(index)

    def _select_excel(self):
        file, _ = QFileDialog.getOpenFileName(self, "选择包含提示词的 Excel 文件", "", "Excel Files (*.xlsx *.xls)")
        if file:
            self.excel_path = file
            self.excel_label.setText(f"✅ {os.path.basename(file)}")
            self.excel_label.setStyleSheet("color: #333; font-size: 13px; background: transparent;")

    def _select_output(self):
        folder = QFileDialog.getExistingDirectory(self, "选择保存目录")
        if folder:
            self.output_path = folder
            self.output_label.setText(f"✅ {folder}")
            self.output_label.setStyleSheet("color: #333; font-size: 13px; background: transparent;")

    def _start_task(self):
        api_key = self.input_api.text().strip()
        if not api_key:
            QMessageBox.warning(self, "提示", "请在左侧【批量出图】工作台中填写 API Key！")
            self._switch_page(1)
            return
        if not self.excel_path:
            QMessageBox.warning(self, "提示", "请选择需要处理的 Excel 文件！")
            return
        if not self.output_path:
            QMessageBox.warning(self, "提示", "请选择图片保存的输出目录！")
            return

        # 获取参数
        model = self.combo_model.currentText()
        ar = self.combo_ar.currentText()
        size = self.combo_size.currentText()
        poll_interval = self.spin_poll.value()
        concurrency = self.spin_concurrency.value()

        # 初始化后台线程
        self.worker = WorkerThread(api_key, self.excel_path, self.output_path, model, ar, size, poll_interval, concurrency)
        self.worker.log_msg.connect(self._append_log)
        self.worker.progress_update.connect(self._update_progress)
        self.worker.finished_task.connect(self._task_finished)

        # 调整 UI 状态
        self.log_area.clear()
        self.progress_bar.setValue(0)
        self.btn_start.setDisabled(True)
        self.nav_running.show()
        self.btn_stop.show()
        self._switch_page(2) # 自动跳转到监控台

        self.worker.start()

    def _append_log(self, text):
        self.log_area.append(text)
        # 自动滚动到底部
        scrollbar = self.log_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _update_progress(self, current, total):
        pct = int((current / total) * 100)
        self.progress_bar.setValue(pct)

    def _stop_task(self):
        if self.worker and self.worker.isRunning():
            self._append_log("⚠️ 正在发送停止信号，等待当前网路请求完成即可终止...")
            self.worker.stop()
            self.btn_stop.setDisabled(True)

    def _task_finished(self, success):
        self.btn_start.setDisabled(False)
        self.btn_stop.hide()
        self.btn_stop.setDisabled(False)
        if success:
            QMessageBox.information(self, "完成", "所有任务已处理完毕！")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # 启用高分屏支持，让文字和图形更清晰
    app.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    window = ModernWebUI()
    window.show()
    sys.exit(app.exec())