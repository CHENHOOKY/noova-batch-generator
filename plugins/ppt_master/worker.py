"""PPT 大师 —— 后台生成 Worker"""

import io
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from plugins._utils import safe_traceback
from plugins.ppt_master.config import (
    _PPT_SCRIPTS_DIR, _PPT_PROJECTS_DIR,
)
from plugins.ppt_master.api_client import call_deepseek_with_retry
from plugins.ppt_master.parsers import (
    extract_json, parse_design_output, parse_spec_lock,
    extract_svg, validate_svg, sanitize_duplicate_attrs, sanitize_filename,
)
from plugins.ppt_master.prompts import (
    OUTLINE_SYSTEM, make_outline_user, make_svg_system, make_svg_user,
    make_strategist_user, _STRATEGIST_SYSTEM_CACHED,
)
from plugins.ppt_master.style_extractor import (
    read_file_text, extract_pptx_style, extract_image_style,
    extract_image_text, format_style_section,
)

_IMAGE_STYLE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def _check_critical_deps() -> list[str]:
    """检查关键依赖，返回缺失列表"""
    missing = []
    try:
        import pptx  # noqa: F401
    except ImportError:
        missing.append("python-pptx")
    try:
        import svglib  # noqa: F401
    except ImportError:
        missing.append("svglib")
    return missing


def _install_deps(log_fn=None) -> bool:
    """安装 ppt-master 核心依赖"""
    req_path = _PPT_SCRIPTS_DIR.parent / "requirements.txt"
    if not req_path.exists():
        cmd = [sys.executable, "-m", "pip", "install",
               "python-pptx>=0.6.21", "svglib>=1.5.0", "reportlab>=4.0.0"]
        if log_fn:
            log_fn("使用 fallback 安装: pip install python-pptx svglib reportlab")
    else:
        cmd = [sys.executable, "-m", "pip", "install", "-r", str(req_path)]
        if log_fn:
            log_fn(f"安装依赖: pip install -r {req_path.name}")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if log_fn:
            for line in proc.stdout.splitlines():
                line = line.strip()
                if line:
                    log_fn(line)
        if proc.returncode != 0:
            if log_fn:
                log_fn(f"安装警告:\n{proc.stderr[:1000]}")
        return True
    except Exception as e:
        if log_fn:
            log_fn(f"安装失败: {e}")
        return False


class PPTGenerateWorker(QThread):
    """后台两阶段 PPT 生成：大纲 → SVG → PPTX"""

    log_msg = Signal(str)
    progress = Signal(int, int, str)
    finished = Signal(bool, str)
    outline_ready = Signal(dict, str)
    slide_started = Signal(int, str, str)
    slide_completed = Signal(int, str, str, bool)

    def __init__(self, api_key: str = "", base_url: str = "", model: str = "",
                 prompt: str = "", page_count: int = 0,
                 canvas_key: str = "", viewbox: str = "",
                 output_dir: str = "",
                 design_scheme: tuple = None, industry: tuple = None,
                 layout: tuple = None,
                 custom_style: str = "",
                 file_paths: list[str] = None,
                 phase: str = "full",
                 outline: dict = None,
                 project_dir: str = "",
                 revision_notes: str = "",
                 previous_outline: dict = None):
        super().__init__()
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.prompt = prompt
        self.page_count = page_count
        self.canvas_key = canvas_key
        self.viewbox = viewbox
        self.output_dir = output_dir
        self.file_paths = file_paths or []
        self._phase = phase
        self._stored_outline = outline
        self._stored_project_dir = project_dir
        self.revision_notes = revision_notes
        self.previous_outline = previous_outline
        self.design_scheme_key = design_scheme[0] if design_scheme else ""
        self.design_scheme_label = design_scheme[1] if design_scheme else "通用"
        self.design_scheme_data = design_scheme[2] if design_scheme else {}
        self.industry_key = industry[0] if industry else ""
        self.industry_label = industry[1] if industry else ""
        self.industry_data = industry[2] if industry and industry[2] else {}
        self.layout_key = layout[0] if layout else ""
        self.layout_label = layout[1] if layout else ""
        self.custom_style = custom_style
        self._is_running = True
        self._project_dir: Path | None = None
        self._spec_lock: dict | None = None

    def stop(self):
        self._is_running = False

    def _log(self, text: str):
        self.log_msg.emit(text)

    def _create_project_dirs(self, ppt_title: str) -> Path:
        date_str = datetime.now().strftime("%Y%m%d")
        dir_name = f"{ppt_title}_{self.canvas_key}_{date_str}"
        dir_name = re.sub(r'[\\/:*?"<>|]', '_', dir_name)[:80]
        base = Path(self.output_dir) if self.output_dir else _PPT_PROJECTS_DIR
        self._project_dir = base / dir_name
        for d in ["svg_output", "svg_final", "exports", "images", "notes"]:
            (self._project_dir / d).mkdir(parents=True, exist_ok=True)
        self._log(f"  项目目录: {self._project_dir}")
        return self._project_dir

    def _generate_outline(self) -> dict:
        self._log("=" * 50)
        self._log("阶段 1/3: 生成 PPT 大纲...")
        self.progress.emit(0, 100, "outline")

        if self.revision_notes:
            self._log(f"  [修改建议] {self.revision_notes[:200]}")

        style_text = ""
        for fp in self.file_paths:
            if not self._is_running:
                raise InterruptedError()
            if not os.path.isfile(fp):
                continue
            ext = Path(fp).suffix.lower()
            if ext == ".pptx":
                self._log(f"  提取参考样式: {os.path.basename(fp)}")
                extracted = extract_pptx_style(fp)
                if extracted:
                    style_text = extracted
                    self._log(f"    [OK] {extracted[:120]}...")
                else:
                    self._log(f"    [WARN] 未能提取样式信息")
                break
        if not style_text:
            for fp in self.file_paths:
                if not self._is_running:
                    raise InterruptedError()
                if not os.path.isfile(fp):
                    continue
                if Path(fp).suffix.lower() in _IMAGE_STYLE_EXTS:
                    self._log(f"  提取图片色板: {os.path.basename(fp)}")
                    extracted = extract_image_style(fp)
                    if extracted:
                        style_text = extracted
                        self._log(f"    [OK] {extracted[:120]}...")
                    else:
                        self._log(f"    [WARN] 未能提取图片色板")
                    break

        files_text = ""
        for fp in self.file_paths:
            if not self._is_running:
                raise InterruptedError()
            if not os.path.isfile(fp):
                continue
            if Path(fp).suffix.lower() in _IMAGE_STYLE_EXTS:
                self._log(f"  读取参考图片: {os.path.basename(fp)}")
                img_text = extract_image_text(fp)
                if img_text:
                    self._log(f"    [OK] 从图片提取到 {len(img_text)} 字符文本")
                    files_text += f"\n--- Image Text: {os.path.basename(fp)} ---\n{img_text[:500000]}\n"
                else:
                    self._log(f"    [INFO] 图片文本提取跳过（pytesseract 未安装或识别失败）")
                continue
            self._log(f"  读取参考文件: {os.path.basename(fp)}")
            content = read_file_text(fp)
            if content.startswith("[") and ("读取失败" in content or "无法读取" in content):
                self._log(f"    [WARN] 跳过无法读取的文件")
                continue
            files_text += f"\n--- File: {os.path.basename(fp)} ---\n{content[:500000]}\n"

        if style_text:
            files_text = f"[STYLE DIRECTION]\n{style_text}\n\n[CONTENT REFERENCES]{files_text}"

        style_section = format_style_section(style_text)

        revision_prefix = ""
        if self.revision_notes:
            rev_lines = [
                "!!! CRITICAL USER FEEDBACK - YOU MUST FOLLOW THESE INSTRUCTIONS ABOVE ALL ELSE !!!",
                "The user was NOT satisfied with the previous outline and provided specific feedback:",
                f'"""',
                self.revision_notes,
                f'"""',
            ]
            if self.previous_outline:
                prev_title = self.previous_outline.get("title", "未命名")
                prev_slides = self.previous_outline.get("slides", [])
                prev_summary = []
                for s in prev_slides[:5]:
                    st = s.get("title", "")
                    prev_summary.append(f"  - [{s.get('type', 'content')}] {st}")
                rev_lines.append("")
                rev_lines.append(
                    f'PREVIOUS OUTLINE ("{prev_title}", {len(prev_slides)} slides) '
                    "that the user rejected:")
                rev_lines.extend(prev_summary)
                rev_lines.append("")
                rev_lines.append(
                    "You MUST produce a substantially different outline. "
                    "Address every point in the feedback above. "
                    "Do NOT repeat the structure or content of the previous outline.")
            rev_lines.append("")
            revision_prefix = "\n".join(rev_lines)

        system_prompt = revision_prefix + OUTLINE_SYSTEM.format(style_section=style_section)

        user_prompt = make_outline_user(
            self.prompt, self.design_scheme_label, self.industry_label,
            self.layout_label, self.custom_style, self.page_count, files_text)

        self._log(f"  请求 DeepSeek ({self.model}) 生成 {self.page_count} 页大纲...")
        raw = call_deepseek_with_retry(
            self.api_key, self.base_url, self.model,
            system_prompt, user_prompt,
            temperature=0.7, max_tokens=32768, json_mode=True,
            log_fn=self._log)
        outline = extract_json(raw)
        slides = outline.get("slides", [])
        if not slides:
            raise RuntimeError("大纲解析失败：未找到 slides 数组")

        ppt_title = outline.get("title", "未命名演示文稿")
        self._log(f"  大纲已生成: \"{ppt_title}\" — {len(slides)} 页")
        self.progress.emit(100, 100, "outline")
        return outline

    def _generate_design_spec(self, outline: dict):
        try:
            self._log("=" * 50)
            self._log("阶段 1.5/3: 生成设计规范和执行锁...")
            self.progress.emit(0, 100, "strategist")

            files_text = ""
            for fp in self.file_paths:
                if not self._is_running:
                    raise InterruptedError()
                if not os.path.isfile(fp):
                    continue
                text = read_file_text(fp)
                if text:
                    files_text += f"\n=== File: {os.path.basename(fp)} ===\n{text[:300000]}"

            user = make_strategist_user(
                outline, self.canvas_key, self.page_count,
                self.custom_style, files_text)

            self._log(f"  请求 DeepSeek ({self.model}) 生成设计规范...")
            raw = call_deepseek_with_retry(
                self.api_key, self.base_url, self.model,
                _STRATEGIST_SYSTEM_CACHED, user,
                temperature=0.3, max_tokens=32768, json_mode=False,
                log_fn=self._log)

            design_spec, spec_lock_text = parse_design_output(raw)

            if not spec_lock_text:
                self._log("  [WARN] 策略师未能生成 spec_lock，使用默认设计参数")
                self._spec_lock = None
                self.progress.emit(100, 100, "strategist")
                return

            if self._project_dir:
                (self._project_dir / "design_spec.md").write_text(
                    design_spec or "", encoding="utf-8")
                (self._project_dir / "spec_lock.md").write_text(
                    spec_lock_text, encoding="utf-8")

            self._spec_lock = parse_spec_lock(spec_lock_text)
            rhythm_count = len(self._spec_lock.get("page_rhythm", {}))
            chart_count = len(self._spec_lock.get("page_charts", {}))
            icon_lib = self._spec_lock.get("icons", {}).get("library", "none")
            self._log(f"  设计规范已生成: {rhythm_count} 页节奏分配, "
                     f"{chart_count} 图表模板, 图标库={icon_lib}")
            self.progress.emit(100, 100, "strategist")
        except InterruptedError:
            raise
        except Exception as e:
            self._log(f"  [WARN] 策略师阶段失败: {e}，使用默认设计参数")
            self._spec_lock = None

    def _generate_svgs(self, outline: dict):
        self._log("=" * 50)
        self._log("阶段 2/3: 逐页生成 SVG 幻灯片...")

        slides = outline["slides"]
        total = len(slides)
        svg_dir = self._project_dir / "svg_output"
        svg_dir.mkdir(parents=True, exist_ok=True)
        self.progress.emit(0, total, "svg")

        failed = []

        for i, slide in enumerate(slides):
            if not self._is_running:
                raise InterruptedError()

            page_num = i + 1
            slide_type = slide.get("type", "content")
            slide_title = slide.get("title", f"Slide {page_num}")

            self._log(f"  [{page_num}/{total}] {slide_title}")
            self.slide_started.emit(page_num, slide_title, slide_type)

            success = self._generate_one_svg(
                i, slide, page_num, slide_type, slide_title,
                total, svg_dir, temperature=0.5)
            if not success:
                failed.append((i, slide))

        if failed:
            failure_rate = len(failed) / total
            self._log(f"\n  {len(failed)}/{total} 个幻灯片失败 ({failure_rate:.0%})，开始重试...")
            if failure_rate > 0.5:
                self._log(f"    [WARN] 超过一半幻灯片失败，请检查 API 配置或提示词")

            retry_ok = 0
            for idx, slide in failed:
                if not self._is_running:
                    raise InterruptedError()
                page_num = idx + 1
                slide_title = slide.get("title", f"Slide {page_num}")
                slide_type = slide.get("type", "content")
                self._log(f"    [重试 {page_num}/{total}] {slide_title}")
                self.slide_started.emit(page_num, slide_title, slide_type)
                ok = self._generate_one_svg(
                    idx, slide, page_num, slide_type, slide_title,
                    total, svg_dir, temperature=0.7)
                if ok:
                    retry_ok += 1
            if retry_ok:
                self._log(f"  重试成功 {retry_ok}/{len(failed)} 个")

    def _generate_one_svg(self, idx: int, slide: dict, page_num: int,
                          slide_type: str, slide_title: str,
                          total: int, svg_dir: Path, temperature: float = 0.5) -> bool:
        try:
            system = make_svg_system(
                slide_type,
                self.design_scheme_label, self.industry_label or "",
                self.layout_label or "", self.layout_key or "", self.custom_style,
                self.design_scheme_data, self.industry_data,
                self.viewbox, page_num, total,
                spec_lock=self._spec_lock)
            user = make_svg_user(slide)

            raw = call_deepseek_with_retry(
                self.api_key, self.base_url, self.model,
                system, user,
                temperature=temperature, max_tokens=65536, json_mode=False,
                log_fn=self._log)

            svg = extract_svg(raw)
            if svg:
                svg = sanitize_duplicate_attrs(svg)
            else:
                svg = sanitize_duplicate_attrs(raw)
            if not svg or not validate_svg(svg, self.viewbox):
                preview = raw[:200].replace('\n', '\\n') if raw else "(empty)"
                self._log(f"    [DEBUG] raw response preview: {preview}")
                if not svg.strip():
                    self._log(f"    [ERR] 空响应，跳过 {slide_title}")
                    self.slide_completed.emit(page_num, slide_title, "", False)
                    self.progress.emit(page_num, total, "svg")
                    return False
                self._log(f"    [WARN] SVG 解析失败，使用原始输出")

            safe_name = sanitize_filename(slide_title)
            filepath = svg_dir / f"{page_num:02d}_{safe_name}.svg"
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(svg, encoding="utf-8")

            notes_text = slide.get("notes", "")
            if notes_text:
                notes_dir = self._project_dir / "notes"
                notes_dir.mkdir(parents=True, exist_ok=True)
                notes_path = notes_dir / f"{page_num:02d}_{safe_name}.md"
                notes_path.write_text(notes_text, encoding="utf-8")

            self._log(f"    [OK] → {filepath.name}")
            self.slide_completed.emit(page_num, slide_title, str(filepath), True)
            self.progress.emit(page_num, total, "svg")
            return True
        except Exception as e:
            self._log(f"    [ERR] 生成失败: {e}")
            self._log(f"    [TRACEBACK] {safe_traceback()}")
            self.slide_completed.emit(page_num, slide_title, "", False)
            self.progress.emit(page_num, total, "svg")
            return False

    def _run_quality_check(self):
        self._log("  运行 SVG 质量检查...")
        try:
            from svg_quality_checker import SVGQualityChecker
            checker = SVGQualityChecker()
            checker.check_directory(str(self._project_dir))
            if checker.summary['errors'] > 0:
                self._log(f"    [WARN] 质量检查发现 {checker.summary['errors']} 个错误，{checker.summary['warnings']} 个警告")
            elif checker.summary['warnings'] > 0:
                self._log(f"    [OK] 质量检查通过（{checker.summary['warnings']} 个警告）")
            else:
                self._log(f"    [OK] 质量检查全部通过 ({checker.summary['passed']}/{checker.summary['total']} 个文件)")
        except ImportError:
            self._log("    [WARN] svg_quality_checker 模块不可用，跳过")
        except Exception as e:
            self._log(f"    [WARN] 质量检查异常: {e}，继续导出")

    def _finalize_and_export(self) -> str:
        self._log("=" * 50)
        self._log("阶段 3/3: 后处理 SVG → 导出 PPTX...")

        self._log("  运行 finalize_svg...")
        try:
            import finalize_svg
            options = {
                "embed_icons": True, "fix_rounded": True,
                "flatten_text": True, "align_images": True,
            }
            finalize_svg.finalize_project(self._project_dir, options, quiet=True)
            self._log("  [OK] SVG 后处理完成")
        except ImportError as e:
            self._log(f"  [WARN] finalize_svg 加载失败: {e}，跳过")
        except Exception as e:
            self._log(f"  [WARN] 后处理异常: {e}，继续导出")

        self._log("  运行 svg_to_pptx 导出 PPTX...")
        try:
            from svg_to_pptx.pptx_builder import create_pptx_with_native_svg
            from svg_to_pptx.pptx_discovery import find_svg_files, find_notes_files
        except ImportError as e:
            raise RuntimeError(
                f"无法导入 svg_to_pptx 模块: {e}\n"
                "请确保 ppt-master 完整且依赖已安装")

        svg_final_dir = self._project_dir / "svg_final"
        source = "final"
        if not svg_final_dir.exists() or not list(svg_final_dir.glob("*.svg")):
            source = "output"

        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            svg_files, source_dir = find_svg_files(self._project_dir, source)
        finally:
            sys.stdout = old_stdout

        if not svg_files:
            raise RuntimeError(
                f"SVG 目录为空: {self._project_dir / 'svg_output'}，生成可能失败")

        sanitized_count = 0
        for svg_path in svg_files:
            try:
                original = svg_path.read_text(encoding="utf-8")
                cleaned = sanitize_duplicate_attrs(original)
                if cleaned != original:
                    svg_path.write_text(cleaned, encoding="utf-8")
                    sanitized_count += 1
            except Exception as e:
                self._log(f"    [WARN] 清理 {svg_path.name} 失败: {e}")
        if sanitized_count:
            self._log(f"  [OK] 修复 {sanitized_count} 个 SVG 文件的重复属性")

        exports_dir = self._project_dir / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)
        output_path = exports_dir / f"{self._project_dir.name}.pptx"

        old_stdout = sys.stdout
        buf = io.StringIO()
        sys.stdout = buf
        try:
            notes = find_notes_files(self._project_dir, svg_files)
            ok = create_pptx_with_native_svg(
                svg_files=svg_files,
                output_path=output_path,
                canvas_format=self.canvas_key,
                use_native_shapes=True,
                enable_notes=True,
                notes=notes,
                transition='fade',
                animation='fade',
                animation_duration=0.4,
                animation_stagger=0.5,
                verbose=False,
            )
        finally:
            sys.stdout = old_stdout
            for line in buf.getvalue().splitlines():
                line = line.strip()
                if line:
                    self._log(f"    {line}")

        if not ok:
            raise RuntimeError("svg_to_pptx 返回失败")
        return str(output_path)

    def run(self):
        if self._phase == "outline":
            self._run_outline_phase()
        elif self._phase == "svg_export":
            self._run_svg_export_phase()
        else:
            self._run_full()

    def _run_outline_phase(self):
        try:
            missing = _check_critical_deps()
            if missing:
                self._log(f"[FAIL] 缺少关键依赖: {', '.join(missing)}")
                self.finished.emit(False, "")
                return

            outline = self._generate_outline()
            slides = outline.get("slides", [])
            if not slides:
                self._log("[FAIL] 大纲生成结果为空")
                self.finished.emit(False, "")
                return

            ppt_title = outline.get("title", "presentation")
            self._create_project_dirs(ppt_title)

            self.outline_ready.emit(outline, str(self._project_dir))
            self.api_key = ""
            self.finished.emit(True, str(self._project_dir))
        except InterruptedError:
            self._log("任务已取消")
            self.finished.emit(False, "")
        except json.JSONDecodeError as e:
            self._log(f"[FAIL] JSON 解析失败: {e}")
            self.finished.emit(False, "")
        except Exception as e:
            self._log(f"[FAIL] {e}")
            self._log(f"[TRACEBACK] {safe_traceback()}")
            self.finished.emit(False, "")

    def _run_svg_export_phase(self):
        try:
            outline = self._stored_outline
            if not outline:
                self._log("[FAIL] 未提供大纲数据")
                self.finished.emit(False, "")
                return
            self._project_dir = Path(self._stored_project_dir) if self._stored_project_dir else None
            if not self._project_dir:
                self._log("[FAIL] 未提供项目目录")
                self.finished.emit(False, "")
                return

            self._log(f"  项目目录: {self._project_dir}")

            if self._is_running:
                self._generate_design_spec(outline)

            self._generate_svgs(outline)
            self._run_quality_check()

            output_path = self._finalize_and_export()

            self._log("=" * 50)
            self._log(f"[DONE] PPTX 已生成: {output_path}")
            self.api_key = ""
            self.finished.emit(True, output_path)
        except InterruptedError:
            self._log("任务已取消")
            self.finished.emit(False, "")
        except Exception as e:
            self._log(f"[FAIL] {e}")
            self._log(f"[TRACEBACK] {safe_traceback()}")
            self.finished.emit(False, "")

    def _run_full(self):
        try:
            missing = _check_critical_deps()
            if missing:
                self._log(f"[FAIL] 缺少关键依赖: {', '.join(missing)}")
                self.finished.emit(False, "")
                return

            outline = self._generate_outline()
            slides = outline["slides"]
            if len(slides) == 0:
                self._log("[FAIL] 大纲生成结果为空")
                self.finished.emit(False, "")
                return

            ppt_title = outline.get("title", "presentation")
            self._create_project_dirs(ppt_title)

            if self._is_running:
                self._generate_design_spec(outline)

            self._generate_svgs(outline)
            self._run_quality_check()
            output_path = self._finalize_and_export()

            self._log("=" * 50)
            self._log(f"[DONE] PPTX 已生成: {output_path}")
            self.api_key = ""
            self.finished.emit(True, output_path)
        except InterruptedError:
            self._log("任务已取消")
            self.finished.emit(False, "")
        except json.JSONDecodeError as e:
            self._log(f"[FAIL] JSON 解析失败: {e}")
            self.finished.emit(False, "")
        except Exception as e:
            self._log(f"[FAIL] {e}")
            self._log(f"[TRACEBACK] {safe_traceback()}")
            self.finished.emit(False, "")
