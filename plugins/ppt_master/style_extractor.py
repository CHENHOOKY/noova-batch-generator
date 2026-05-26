"""PPT 大师 —— 样式提取工具（PPTX/图片/文件内容）"""

import os
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from plugins.ppt_master.config import _PPT_SCRIPTS_DIR

_IMAGE_STYLE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def read_file_text(path: str) -> str:
    """读取文件文本内容，根据扩展名选择最佳方式"""
    ext = Path(path).suffix.lower()
    if ext in {".txt", ".md", ".markdown"}:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    if ext == ".pdf":
        try:
            import fitz
            doc = fitz.open(path)
            text = "\n".join(page.get_text() for page in doc)
            doc.close()
            return text
        except ImportError:
            return f"[PDF 文件: {Path(path).name} — 安装 PyMuPDF 可提取文本]"
        except Exception as e:
            return f"[PDF 读取失败: {e}]"
    if ext == ".docx":
        try:
            import mammoth
            result = mammoth.extract_raw_text(path)
            return result.value
        except ImportError:
            return f"[DOCX 文件: {Path(path).name} — 安装 mammoth 可提取文本]"
        except Exception as e:
            return f"[DOCX 读取失败: {e}]"
    if ext in {".xlsx", ".xlsm"}:
        try:
            import openpyxl
            wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
            parts = []
            max_rows = 20000
            for sn in wb.sheetnames:
                ws = wb[sn]
                parts.append(f"=== Sheet: {sn} ===")
                row_count = 0
                for row in ws.iter_rows(values_only=True, max_row=max_rows):
                    parts.append("\t".join(
                        str(c) if c is not None else "" for c in row))
                    row_count += 1
                if row_count >= max_rows:
                    parts.append(f"[警告: 工作表 \"{sn}\" 在第 {max_rows} 行处被截断]")
            wb.close()
            return "\n".join(parts)
        except ImportError:
            return f"[Excel 文件: {Path(path).name} — 安装 openpyxl 可提取文本]"
        except Exception as e:
            return f"[Excel 读取失败: {e}]"
    if ext == ".csv":
        try:
            return Path(path).read_text(encoding="utf-8-sig", errors="replace")
        except Exception as e:
            return f"[CSV 读取失败: {e}]"
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return f"[无法读取: {Path(path).name}]"


def hex_luminance(hex_color: str) -> float:
    """计算 hex 颜色相对亮度 (0-1)"""
    hex_color = hex_color.lstrip('#')
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    return 0.299 * r + 0.587 * g + 0.114 * b


def extract_pptx_style(filepath: str) -> str:
    """从参考 PPTX 提取配色+字体风格摘要。
    返回 ~200-400 字符的浓缩描述，失败返回 ""。"""
    NS = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
    colors: dict[str, str] = {}
    fonts: dict[str, str] = {}

    try:
        with zipfile.ZipFile(filepath, 'r') as zf:
            theme_files = sorted(
                n for n in zf.namelist()
                if n.startswith('ppt/theme/') and n.endswith('.xml')
            )
            if not theme_files:
                return ""
            theme_root = ET.parse(zf.open(theme_files[0])).getroot()

            clr_scheme = theme_root.find('.//a:clrScheme', NS)
            if clr_scheme is not None:
                for child in list(clr_scheme):
                    tag = child.tag.split('}', 1)[-1] if '}' in child.tag else child.tag
                    srgb = child.find('a:srgbClr', NS)
                    sys_clr = child.find('a:sysClr', NS)
                    if srgb is not None and srgb.attrib.get('val'):
                        colors[tag] = f"#{srgb.attrib['val']}"
                    elif sys_clr is not None and sys_clr.attrib.get('lastClr'):
                        colors[tag] = f"#{sys_clr.attrib['lastClr']}"

            font_scheme = theme_root.find('.//a:fontScheme', NS)
            if font_scheme is not None:
                for role, tag_name in [('major', 'a:majorFont'), ('minor', 'a:minorFont')]:
                    role_font = font_scheme.find(tag_name, NS)
                    if role_font is not None:
                        for lang, el_name in [('Latin', 'a:latin'), ('EastAsia', 'a:ea')]:
                            el = role_font.find(el_name, NS)
                            if el is not None and el.attrib.get('typeface'):
                                fonts[f'{role}{lang}'] = el.attrib['typeface']
    except Exception:
        return ""

    if not colors and not fonts:
        return ""

    font_size_hint = ""
    try:
        import pptx
        prs = pptx.Presentation(filepath)
        sizes: list[float] = []
        for slide in prs.slides[:3]:
            for shape in slide.shapes:
                if shape.has_text_frame:
                    for para in shape.text_frame.paragraphs:
                        for run in para.runs:
                            if run.font.size:
                                sizes.append(run.font.size / 12700)
        if sizes:
            sizes.sort()
            n = len(sizes)
            body_pt = sizes[n // 2]
            title_pt = sizes[min(int(n * 0.85), n - 1)]
            font_size_hint = f" | Font sizes: body~{body_pt:.0f}pt, title~{title_pt:.0f}pt"
    except Exception:
        pass

    mode = ""
    dk1 = colors.get('dk1', '').upper()
    lt1 = colors.get('lt1', '').upper()
    if dk1 and lt1:
        if hex_luminance(dk1) < hex_luminance(lt1):
            mode = " | Light mode"
        else:
            mode = " | Dark mode"

    name = os.path.basename(filepath)
    color_str = ", ".join(f"{k}={v}" for k, v in list(colors.items())[:8])
    font_str = ", ".join(f"{k}={v}" for k, v in fonts.items())

    lines = [f"[PPTX Style Reference: {name}]{mode}"]
    if color_str:
        lines.append(f"Colors: {color_str}")
    if font_str:
        lines.append(f"Fonts: {font_str}")
    if font_size_hint:
        lines.append(font_size_hint.strip(" |"))

    return " | ".join(lines)


def extract_image_style(filepath: str) -> str:
    """从参考图片提取主色调色板。
    返回 ~150-250 字符的浓缩描述，失败返回 ""。"""
    try:
        from PIL import Image
    except ImportError:
        return ""

    try:
        try:
            from PIL.Image import Resampling
            resample = Resampling.LANCZOS
        except ImportError:
            resample = Image.LANCZOS
        img = Image.open(filepath).convert("RGB")
        img = img.resize((150, 150), resample)
        q = img.quantize(16)
        palette = q.getpalette()[:48]
        pixels = list(q.getdata())
        counts: dict[int, int] = {}
        for p in pixels:
            counts[p] = counts.get(p, 0) + 1
        top = sorted(counts.items(), key=lambda x: -x[1])[:8]
        hex_colors = []
        for idx, _ in top:
            r, g, b = palette[idx * 3], palette[idx * 3 + 1], palette[idx * 3 + 2]
            hex_colors.append(f"#{r:02X}{g:02X}{b:02X}")

        total_lum = 0
        for idx, cnt in top:
            r, g, b = palette[idx * 3], palette[idx * 3 + 1], palette[idx * 3 + 2]
            total_lum += (0.299 * r + 0.587 * g + 0.114 * b) * cnt
        total_cnt = sum(c for _, c in top)
        avg_lum = total_lum / total_cnt if total_cnt else 128
        mode = "Light mode" if avg_lum > 128 else "Dark mode"

        name = os.path.basename(filepath)
        color_str = ", ".join(hex_colors)
        return (f"[Image Style Reference: {name}] | {mode}"
                f" | Palette: {color_str}"
                f" | Use these as the dominant color palette for all slides")
    except Exception:
        return ""


def extract_image_text(filepath: str) -> str:
    """从图片中提取文本（OCR）。需要 pytesseract + Tesseract-OCR 引擎。"""
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return ""

    try:
        img = Image.open(filepath)
        text = pytesseract.image_to_string(img, lang='chi_sim+eng')
        if not text.strip():
            text = pytesseract.image_to_string(img, lang='eng')
        return text.strip()
    except Exception:
        return ""


def format_style_section(style_text: str) -> str:
    """将 PPTX 样式摘要包装为 prompt 段落，无样式时返回空字符串"""
    if not style_text:
        return ""
    return (
        f"\n\nSTYLE REFERENCE (VISUAL DIRECTION):\n{style_text}\n"
        "Use these style cues (colors, fonts, sizing, light/dark mode)"
        " when planning the visual direction of each slide."
    )


def load_layout_examples(layout_key: str) -> str:
    """从布局模板目录加载 SVG 示例作为排版参考。
    最多加载 3 个文件，每个截断至 2000 字符。"""
    if not layout_key or layout_key == "none":
        return ""
    layouts_dir = _PPT_SCRIPTS_DIR.parent / "templates" / "layouts" / layout_key
    if not layouts_dir.is_dir():
        return ""
    result = ""
    count = 0
    for svg_file in sorted(layouts_dir.glob("*.svg")):
        if count >= 3:
            break
        try:
            content = svg_file.read_text(encoding="utf-8")
            if len(content) > 2000:
                content = content[:2000] + "\n<!-- truncated -->"
            result += f"\n--- Layout Example: {svg_file.name} ---\n{content}\n"
            count += 1
        except Exception:
            pass
    return result
