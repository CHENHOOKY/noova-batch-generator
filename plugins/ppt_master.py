"""PPT 大师插件 v2 —— DeepSeek AI 驱动的一键 PPT 生成

输入主题/提示词 → DeepSeek 生成大纲 → 逐页生成 SVG → ppt-master 导出原生 PPTX
DeepSeek API 兼容 OpenAI SDK 格式，用户自备 API Key。

删除此文件不会影响主程序及其他插件。
"""

import io
import json
import os
import random
import re
import subprocess
import sys
import traceback
import unicodedata
import urllib.request
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QScrollArea,
    QLabel, QPushButton, QComboBox, QFileDialog, QMessageBox,
    QProgressBar, QTextEdit, QLineEdit, QSpinBox, QSizePolicy,
    QDialog, QSplitter,
)
from PySide6.QtCore import Qt, QThread, Signal

from plugin_base import BasePlugin

# ═══════════════════════════════════════
#  路径常量
# ═══════════════════════════════════════
_PPT_SCRIPTS_DIR = (
    Path(__file__).resolve().parent.parent
    / "ppt-master" / "skills" / "ppt-master" / "scripts"
)
_PPT_PROJECTS_DIR = (
    Path(__file__).resolve().parent.parent
    / "ppt-master" / "projects"
)

# ppt-master 参考文件路径（只读引用，不修改原项目文件）
_REFERENCES_DIR = _PPT_SCRIPTS_DIR.parent / "references"
_TEMPLATES_DIR = _PPT_SCRIPTS_DIR.parent / "templates"
_SHARED_STANDARDS_PATH = _REFERENCES_DIR / "shared-standards.md"
_ICONS_DIR = _TEMPLATES_DIR / "icons"
_CHARTS_DIR = _TEMPLATES_DIR / "charts"
_CHARTS_INDEX_PATH = _CHARTS_DIR / "charts_index.json"
_SPEC_LOCK_REF_PATH = _TEMPLATES_DIR / "spec_lock_reference.md"


def _load_reference_cache() -> dict:
    """加载 shared-standards.md 关键规则缓存（模块级，仅一次）。"""
    cache = {
        "banned_features": "",
        "replacements": "",
        "shadow_rules": "",
        "text_rules": "",
    }
    try:
        if _SHARED_STANDARDS_PATH.exists():
            content = _SHARED_STANDARDS_PATH.read_text(encoding="utf-8")
            # 提取 §1 黑名单
            m = re.search(r'## 1\. SVG Banned Features Blacklist(.*?)(?=## 2\.)', content, re.S)
            if m:
                cache["banned_features"] = m.group(1).strip()
            # 提取 §2 替代方案表格
            m = re.search(r'## 2\. PPT Compatibility Alternatives(.*?)(?=## 3\.)', content, re.S)
            if m:
                cache["replacements"] = m.group(1).strip()
            # 提取 §6 阴影克制规范
            m = re.search(r'## 6\. Shadow & Overlay Techniques(.*?)(?=## 7\.)', content, re.S)
            if m:
                cache["shadow_rules"] = m.group(1).strip()
            # 提取 §4 文字标记规则
            m = re.search(r'### Inline Text Runs.*?(?=### Element Grouping)', content, re.S)
            if m:
                cache["text_rules"] = m.group(0).strip()
    except Exception:
        pass
    return cache


_SHARED_STANDARDS_CACHE = _load_reference_cache()

# ═══════════════════════════════════════
#  设计令牌
# ═══════════════════════════════════════
C_PRIMARY = "#6366F1"
C_PRIMARY_HOVER = "#4F46E5"
C_TEXT = "#1E1E2E"
C_TEXT_SUB = "#6B7280"
C_CARD_BG = "#FFFFFF"
C_CARD_BDR = "#ECEDF0"
C_LOG_BG = "#FAFAFA"
C_DANGER = "#EF4444"
C_GREEN = "#10B981"
C_SEP = "#F0F0F3"

# ═══════════════════════════════════════
#  DeepSeek API 默认值
# ═══════════════════════════════════════
DS_BASE_URL = "https://api.deepseek.com"
DS_MODELS = ["deepseek-v4-pro", "deepseek-v4-flash"]
DS_MAX_TOKENS = 16384

# ═══════════════════════════════════════
#  设计风格选项
# ═══════════════════════════════════════
# ═══════════════════════════════════════
#  ppt-master 内置设计系统
# ═══════════════════════════════════════

# 设计配色方案 (from ppt-master config.py DESIGN_COLORS)
DESIGN_SCHEMES = [
    ("consulting", "咨询/商务",
     {"primary": "#005587", "secondary": "#0076A8", "accent": "#F5A623",
      "bg": "#FFFFFF", "bg_alt": "#F8F9FA",
      "text_dark": "#1A252F", "text_muted": "#7F8C8D"}),
    ("general", "通用/多用途",
     {"primary": "#2196F3", "secondary": "#4CAF50", "accent": "#FF9800",
      "bg": "#FFFFFF", "bg_alt": "#F8F9FA",
      "text_dark": "#2C3E50", "text_muted": "#7F8C8D"}),
    ("tech", "科技/深色",
     {"primary": "#00D1FF", "secondary": "#7B61FF", "accent": "#00FF88",
      "bg": "#0A0E17", "bg_alt": "#1A1F2E",
      "text_dark": "#0A0E17", "text_muted": "#8892A0",
      "text_light": "#FFFFFF"}),
    ("academic", "学术/严谨",
     {"primary": "#8B0000", "secondary": "#1E3A5F", "accent": "#C9B037",
      "bg": "#FFFFFF", "bg_alt": "#F5F5F5",
      "text_dark": "#1A1A1A", "text_muted": "#666666"}),
    ("government", "政务/正式",
     {"primary": "#C41E3A", "secondary": "#1E3A5F", "accent": "#D4AF37",
      "bg": "#FFFFFF", "bg_alt": "#FFF8E1",
      "text_dark": "#1A1A1A", "text_muted": "#555555"}),
]

# 行业配色 (from ppt-master config.py INDUSTRY_COLORS)
INDUSTRY_PALETTES = [
    ("none", "（不使用行业配色）", {}),
    ("finance", "金融/银行",
     {"primary": "#003366", "secondary": "#4A90D9", "accent": "#D4AF37"}),
    ("healthcare", "医疗/健康",
     {"primary": "#00796B", "secondary": "#4DB6AC", "accent": "#FF7043"}),
    ("technology", "科技/互联网",
     {"primary": "#1565C0", "secondary": "#42A5F5", "accent": "#00E676"}),
    ("education", "教育/培训",
     {"primary": "#5E35B1", "secondary": "#7E57C2", "accent": "#FFD54F"}),
    ("retail", "零售/消费",
     {"primary": "#E53935", "secondary": "#EF5350", "accent": "#FFB300"}),
    ("manufacturing", "制造/工业",
     {"primary": "#455A64", "secondary": "#78909C", "accent": "#FF6F00"}),
    ("energy", "能源/环保",
     {"primary": "#2E7D32", "secondary": "#66BB6A", "accent": "#FDD835"}),
    ("realestate", "地产/建筑",
     {"primary": "#795548", "secondary": "#A1887F", "accent": "#4CAF50"}),
    ("legal", "法律/合规",
     {"primary": "#37474F", "secondary": "#546E7A", "accent": "#8D6E63"}),
    ("media", "传媒/娱乐",
     {"primary": "#7B1FA2", "secondary": "#AB47BC", "accent": "#FF4081"}),
    ("logistics", "物流/供应链",
     {"primary": "#F57C00", "secondary": "#FFB74D", "accent": "#0288D1"}),
    ("agriculture", "农业/食品",
     {"primary": "#558B2F", "secondary": "#8BC34A", "accent": "#FFCA28"}),
    ("tourism", "旅游/酒店",
     {"primary": "#00ACC1", "secondary": "#4DD0E1", "accent": "#FF7043"}),
    ("automotive", "汽车/交通",
     {"primary": "#263238", "secondary": "#455A64", "accent": "#D32F2F"}),
]

# 页面布局模板 (from ppt-master templates/layouts)
LAYOUT_TEMPLATES = [
    ("none", "（默认布局）", ""),
    ("academic_defense", "学术答辩", "论文答辩、学术报告、研究进展"),
    ("ai_ops", "AI运维架构", "技术架构图、IT系统概览、数字化转型"),
    ("government_blue", "政务蓝色", "重点项目汇报、五年规划、工作总结"),
    ("government_red", "政务红色", "政策解读、招商推介、项目介绍"),
    ("medical_university", "医学学术", "医学报告、病例讨论、科研展示"),
    ("pixel_retro", "像素复古", "技术分享、编程教程、游戏介绍"),
    ("psychology_attachment", "心理学", "心理培训、学术讲座、咨询案例分析"),
]

CANVAS_OPTIONS = [
    ("ppt169", "PPT 16:9 (1280×720)", "0 0 1280 720"),
    ("ppt43", "PPT 4:3 (1024×768)", "0 0 1024 768"),
    ("xiaohongshu", "小红书 (1080×1440)", "0 0 1080 1440"),
    ("wechat", "微信头图 (900×383)", "0 0 900 383"),
]

CANVAS_VIEWBOX: dict[str, str] = {k: v for k, _, v in CANVAS_OPTIONS}
CANVAS_LABELS: dict[str, str] = {k: lbl for k, lbl, _ in CANVAS_OPTIONS}

# 确保 ppt-master 脚本目录在 sys.path 中（模块级别，仅一次）
_ppt_scripts_str = str(_PPT_SCRIPTS_DIR)
if _ppt_scripts_str not in sys.path:
    sys.path.insert(0, _ppt_scripts_str)


def _safe_traceback() -> str:
    """获取回溯字符串，编辑掉可能的 API 密钥"""
    tb = traceback.format_exc()
    tb = re.sub(r'sk-[a-zA-Z0-9]{10,}', 'sk-***REDACTED***', tb)
    return tb


# ═══════════════════════════════════════
#  DeepSeek API 客户端（纯 stdlib，零依赖）
# ═══════════════════════════════════════

def _call_deepseek(api_key: str, base_url: str, model: str,
                   system_prompt: str, user_prompt: str,
                   temperature: float = 0.7, max_tokens: int = 65536,
                   json_mode: bool = False,
                   log_fn=None) -> str:
    """调用 DeepSeek Chat Completions API，返回响应文本"""
    url = base_url.rstrip("/") + "/v1/chat/completions"
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}

    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", "application/json; charset=utf-8")

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        choice = result["choices"][0]
        finish = choice.get("finish_reason", "unknown")
        content = choice["message"]["content"] or ""
        # 诊断日志：token 用量 + 终止原因
        usage = result.get("usage", {})
        if log_fn and finish != "stop":
            log_fn(f"    [WARN] API 响应异常终止: finish_reason={finish}, "
                   f"prompt_tokens={usage.get('prompt_tokens','?')}, "
                   f"completion_tokens={usage.get('completion_tokens','?')}")
            if finish == "length":
                log_fn(f"    [WARN] 输出超过 token 限制，内容可能不完整")
                raise RuntimeError(
                    f"[TRUNCATED] 输出被截断 (completion_tokens="
                    f"{usage.get('completion_tokens','?')})")
        if not content.strip():
            raise RuntimeError(f"API 返回空内容 (finish_reason={finish})")
        return content
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        if e.code == 401:
            raise RuntimeError("API Key 无效 (401)，请检查后重试")
        elif e.code == 403:
            raise RuntimeError(f"API 访问被拒绝 (403): {body[:200]}")
        elif e.code == 429:
            raise RuntimeError("API 请求过于频繁 (429)，请稍后重试")
        else:
            raise RuntimeError(f"API 错误 ({e.code}): {body[:300]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"网络连接失败: {e.reason}")


def _call_deepseek_with_retry(*args, max_retries=3, log_fn=None, **kwargs):
    """带重试的 API 调用（重试条件：429 限流 + 空响应 + 输出截断）"""
    import time
    for attempt in range(max_retries):
        try:
            return _call_deepseek(*args, log_fn=log_fn, **kwargs)
        except RuntimeError as e:
            msg = str(e)
            retryable = "429" in msg or "空内容" in msg or "[TRUNCATED]" in msg
            if retryable and attempt < max_retries - 1:
                if "[TRUNCATED]" in msg:
                    current = kwargs.get("max_tokens", 4096)
                    kwargs["max_tokens"] = min(current * 2, 524288)
                    reason = f"输出截断 (max_tokens: {current} → {kwargs['max_tokens']})"
                elif "429" in msg:
                    reason = "429 限流"
                else:
                    reason = "空响应"
                wait = (attempt + 1) * 5 + random.uniform(0, 2)
                if log_fn:
                    log_fn(f"  [重试] {reason}，等待 {wait:.1f}s... (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait)
                continue
            raise


# ═══════════════════════════════════════
#  Prompt 模板
# ═══════════════════════════════════════

OUTLINE_SYSTEM = """You are a professional presentation strategist. Given a user's topic,
generate a structured PPT outline in JSON format.

Output ONLY valid JSON (no markdown, no explanation):
{{
  "title": "presentation title",
  "subtitle": "optional subtitle for cover",
  "slides": [
    {{
      "type": "cover",
      "title": "Slide Title",
      "subtitle": "Subtitle or presenter name",
      "content": ["key point 1", "key point 2"],
      "notes": "speaker notes"
    }},
    {{
      "type": "content",
      "title": "Section Title",
      "content": ["bullet 1", "bullet 2", "bullet 3"],
      "notes": "speaker notes"
    }},
    {{
      "type": "ending",
      "title": "Thank You",
      "content": ["contact info", "Q&A"],
      "notes": ""
    }}
  ]
}}

Rules:
- First slide must be type "cover", last slide type "ending"
- content array: 3-5 items per slide, concise (each 5-15 words)
- Use the user's language (Chinese for Chinese topics, English for English topics)
- If a specific slide count is given, match it. If the user asks for "auto" or does not specify, determine the appropriate number based solely on content depth and complexity.
- If reference materials contain "=== Sheet:" headers, extract and use data from ALL sheets, not just the first one
{style_section}"""


def _make_outline_user(topic: str, design_label: str, industry_label: str,
                       layout_label: str, custom_style: str,
                       page_count: int, files_text: str = "") -> str:
    parts = [
        f"Topic: {topic}",
        f"Design scheme: {design_label}",
    ]
    if industry_label and industry_label != "None":
        parts.append(f"Industry: {industry_label}")
    if layout_label and layout_label != "（默认布局）":
        parts.append(f"Layout reference: {layout_label}")
    if custom_style:
        parts.append(f"Custom style notes: {custom_style}")
    if page_count > 0:
        parts.append(f"Requested slides: {page_count}")
    else:
        parts.append(
            "Slides: auto — determine the appropriate number based on "
            "content depth and complexity. Be flexible.")
    p = "\n".join(parts) + "\n"
    if files_text:
        p += f"\nReference materials:\n{files_text[:2000000]}\n"
    p += "\nPlease generate the outline now."
    return p


def _format_palette(scheme: dict, industry: dict | None) -> str:
    """将配色方案格式化为 prompt 中的色彩规范"""
    lines = []
    if scheme:
        lines.append(f"Primary: {scheme.get('primary', '#333')}")
        lines.append(f"Secondary: {scheme.get('secondary', '#666')}")
        lines.append(f"Accent: {scheme.get('accent', '#F5A623')}")
        lines.append(f"Background: {scheme.get('bg', '#FFFFFF')}")
        lines.append(f"Background alt: {scheme.get('bg_alt', '#F8F9FA')}")
        lines.append(f"Text dark: {scheme.get('text_dark', '#1A1A1A')}")
        lines.append(f"Text muted: {scheme.get('text_muted', '#888888')}")
        if scheme.get("text_light"):
            lines.append(f"Text light: {scheme['text_light']}")
    if industry and industry.get("primary"):
        lines.append(f"Industry primary: {industry['primary']}")
        lines.append(f"Industry secondary: {industry['secondary']}")
        lines.append(f"Industry accent: {industry['accent']}")
    return "\n".join(f"  - {line}" for line in lines) if lines else ""


def _format_style_section(style_text: str) -> str:
    """将 PPTX 样式摘要包装为 prompt 段落，无样式时返回空字符串"""
    if not style_text:
        return ""
    return (
        f"\n\nSTYLE REFERENCE (VISUAL DIRECTION):\n{style_text}\n"
        "Use these style cues (colors, fonts, sizing, light/dark mode)"
        " when planning the visual direction of each slide."
    )


def _load_layout_examples(layout_key: str) -> str:
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


SVG_SYSTEM = """You are a world-class presentation SVG designer. Generate ONE slide as
pure SVG code for a professional presentation.

{spec_lock_injection}

DESIGN CONTEXT:
- Slide type: {slide_type}
- Design scheme: {design_scheme}
- Industry: {industry}
- Layout reference: {layout_template}
- Custom style notes: {custom_style}
- Page rhythm: {page_rhythm_directive}
{layout_examples}

COLOR PALETTE (use these exact colors — DO NOT introduce new colors):
{palette}

TECHNICAL REQUIREMENTS:
1. viewBox="{viewbox}" — NO XML declaration, NO <!DOCTYPE, NO HTML wrapper
2. Output ONLY a ```svg code block, nothing else before or after
3. Background: use a <rect> covering the full viewBox with bg color
4. Fonts: every font-family stack MUST end with a Windows pre-installed font
   (Microsoft YaHei, SimSun, Arial, Times New Roman, Consolas). Lead with
   the spec's font families, add fallbacks.
5. Use clean geometric shapes, lines, and proper text hierarchy
6. Semantic <g> groups: 3-8 top-level <g id="..."> groups per slide.
   Wrap logically related elements (card, list item, icon+text, header, footer).
   Chrome groups (id tokens: bg, header, footer, decoration, page-number, nav, logo)
   are auto-skipped by animation — use these naming conventions.
7. Page numbers in footer (except cover): "PAGE {page_num} / {total_pages}"
8. Footer must include a thin rule line and right-aligned page number
9. Cover slides: bold, dramatic, big title, NO footer. Anchor rhythm.
10. Use font-weight explicitly (bold=700, black=900). No fake weights.
11. ALL text properly aligned (text-anchor where needed)
12. Icons: use `<use data-icon="<library>/<name>" x="..." y="..."
    width="48" height="48" fill="#HEX"/>` format (ONLY for icons listed in inventory)
13. Images (if spec allows): `<image href="../images/file.png"
    preserveAspectRatio="xMidYMid slice" .../>` with optional clipPath for crops

BANNED FEATURES (SVG will be invalid if used):
- NO <style>, class, <foreignObject>, textPath, @font-face
- NO <animate*>, <script>, <iframe>, <symbol>+<use> (except data-icon)
- NO mask on non-image elements
- NO rgba() — use fill="#HEX" fill-opacity="N"
- NO <g opacity="..."> — set fill-opacity/stroke-opacity on each child
- NO <image opacity="..."> — use overlay rect for image opacity
- NO HTML named entities (&nbsp;, &mdash;, &copy;, &hellip;, &bull;) —
  write raw Unicode characters (—, ©, →, ·, NBSP)
- clipPath ONLY on <image> elements, not shapes

SHADOW RESTRAINT:
- Max 2-3 shadowed elements per page
- Single light source per page (all shadows share same dx/dy direction)
- Two-tier elevation only: resting (flood-opacity 0.06-0.10, dy=2-4) and
  raised (flood-opacity 0.12-0.20, dy=6-10). NEVER exceed 0.20
- Shadow only on floating elements over photo/colored panels, NOT on
  background panels, dividers, peer-grid cards, or body-text containers
- For shadows use filter with feGaussianBlur + feOffset + feFlood pattern

TEXT STYLING RULES:
- Single logical line = single <text> with inline <tspan> children.
  NEVER use multiple adjacent <text> elements for one visual line.
- Wrap key data (percentages, multipliers, amounts, load-bearing nouns)
  in `<tspan fill="accent-color" font-weight="bold">...</tspan>`
- Inline tspans must NOT carry x/y/dy (those start new lines). dx is safe.
- For multi-line text: one <text> with per-line <tspan x="..." dy="...">
- Columns = separate <text> elements (two-column layout = two <text>)

PAGE RHYTHM DIRECTIVE:
{runtime_rhythm}

Keep shapes elegant but deliberate — rects, lines, circles with proper
stroke widths, rounded corners where appropriate. Think like a designer."""


STRATEGIST_SYSTEM = """You are a world-class presentation design strategist. Your job is to
analyze a PPT outline and produce a comprehensive design specification and execution lock.

You will receive:
- A confirmed PPT outline (JSON with title, slides, content)
- Design context (style notes, canvas format, reference materials)

INSTRUCTIONS:
1. Analyze the outline deeply — identify content patterns, data density per slide,
   narrative flow, and audience type
2. Produce TWO sections in the exact format below

---SECTION: design_spec.md---
(A complete design narrative in markdown covering these areas:
## I. Project Info — title, canvas, page count, style direction
## II. Canvas — viewBox, format, margins
## III. Visual Theme — color scheme with HEX values, 60-30-10 rule, light/dark mode,
     style objective in 1-2 sentences
## IV. Typography — font stacks per role (title/body/emphasis/code),
     every stack MUST end with a pre-installed font (Microsoft YaHei / SimSun / Arial /
     Times New Roman / Consolas). Body baseline px. Size ramp table.
## V. Layout Principles — page structure zones, rhythm approach
## VI. Icon Spec — chosen library (exactly one of: chunk-filled / tabler-filled /
     tabler-outline / phosphor-duotone), inventory of 6-15 icon names needed across the deck
## VII. Visualization Reference — per-page chart template assignments (if any)
## VIII. Image Resource List — placeholder `<image>` usage strategy (if any)
## IX. Content Outline — the confirmed outline with per-page layout notes
## X. Speaker Notes — style and structure
## XI. Tech Constraints — SVG compatibility and PPT export rules)

---SECTION: spec_lock.md---
(Machine-readable execution contract. Format EXACTLY as:

## canvas
- viewBox: <value>
- format: <value>

## colors
- bg: #HEX
- primary: #HEX
- accent: #HEX
- secondary_accent: #HEX (if needed)
- text: #HEX
- text_secondary: #HEX
- border: #HEX (if needed)

## typography
- font_family: "<Font>", <fallback>, sans-serif
- title_family: "<Font>", <fallback>, sans-serif
- body_family: "<Font>", "<Font>", <fallback>, sans-serif
- emphasis_family: "<Font>", <fallback>, serif
- code_family: "<Font>", "<Font>", monospace
- body: <N>px
- title: <N>px
- subtitle: <N>px
- annotation: <N>px

## icons
- library: <chunk-filled|tabler-filled|tabler-outline|phosphor-duotone>
- stroke_width: <1.5|2|3>  (ONLY for tabler-outline; omit otherwise)
- inventory: <icon1>, <icon2>, ..., <iconN>

## page_rhythm
- P01: <anchor|dense|breathing>
- P02: <anchor|dense|breathing>
... (one entry per slide, including cover and ending)

## page_charts
- P<NN>: <chart_template_key>
... (only for slides that use a charts/ template; omit section if none)

## forbidden
- Mixing icon libraries
- rgba()
- <style>, class, <foreignObject>, textPath, @font-face, <animate*>,
  <script>, <iframe>, <symbol>+<use>
- <g opacity> (set opacity on each child individually)
- HTML named entities in text (&nbsp;, &mdash;, &copy;, etc.) — use raw Unicode
)

CRITICAL RULES:
- spec_lock.md MUST be parseable: every `## section` followed by `- key: value` lines
- Colors: exactly 4-6 hex values. Follow 60-30-10 rule. Text contrast ratio >= 4.5:1
- Typography: every font-family stack MUST end with a Windows pre-installed font
  (Microsoft YaHei / SimSun / Arial / Times New Roman / Consolas / SimHei / Georgia)
- Icons: pick exactly ONE stylistic library. Do NOT mix. Inventory lists icon names
  without library prefix.
- Page rhythm: assign EVERY slide one of {{anchor, dense, breathing}}:
  * anchor — cover, ending, chapter/section openers. Bold, dramatic. Follow template.
  * dense — data-heavy, multi-point, comparisons. Card grids, multi-column allowed.
  * breathing — single concept, hero quote, transition. NO multi-card grid layouts.
    Use whitespace, dividers, full-bleed imagery, single emphasis.
  * Rhythm follows narrative: breathing pages mark genuine pauses. Do not invent
    filler pages. A data report may be nearly all dense — that's fine.
- Chart matching (page_charts section): scan the outline for pages whose content
  shape matches a visualization type (bar chart, line chart, timeline, process flow,
  matrix/quadrant, funnel, etc.). Reference these common chart template keys:
  bar_chart, line_chart, pie_chart, donut_chart, timeline_horizontal, process_flow,
  vertical_pillars, quadrant_bubble_scatter, matrix_2x2, funnel_chart, sankey_chart,
  numbered_steps, hub_spokes, comparison_table, waterfall_chart, kpi_dashboard,
  chevron_chain, swot_quadrant, team_roster, agenda_list, roadmap_horizontal.
  Only assign a chart when the page's content genuinely matches. Leave non-data
  pages unassigned (they get free design).

SVG TECHNICAL STANDARDS (enforced in spec_lock forbidden section):
{banned_features}
{replacements}
{shadow_rules}
{text_rules}"""


_STRATEGIST_SYSTEM_CACHED = STRATEGIST_SYSTEM.format(
    banned_features=_SHARED_STANDARDS_CACHE.get("banned_features", ""),
    replacements=_SHARED_STANDARDS_CACHE.get("replacements", ""),
    shadow_rules=_SHARED_STANDARDS_CACHE.get("shadow_rules", "")[:3000],
    text_rules=_SHARED_STANDARDS_CACHE.get("text_rules", "")[:2000],
)


def _make_svg_system(slide_type: str, scheme_label: str, industry_label: str,
                     layout_label: str, layout_key: str, custom_style: str,
                     scheme: dict, industry: dict | None,
                     viewbox: str, page_num: int, total_pages: int,
                     spec_lock: dict | None = None) -> str:
    palette = _format_palette(scheme, industry)
    examples = _load_layout_examples(layout_key)

    # 构建 spec_lock 注入块
    spec_injection = ""
    page_rhythm_label = ""
    runtime_rhythm = ""

    if spec_lock:
        colors = spec_lock.get("colors", {})
        typo = spec_lock.get("typography", {})
        icons = spec_lock.get("icons", {})
        page_rhythm_map = spec_lock.get("page_rhythm", {})
        page_key = f"P{page_num:02d}"
        rhythm = page_rhythm_map.get(page_key, "dense")
        page_rhythm_label = f"{rhythm} (page {page_num}/{total_pages})"

        # 构建颜色锁定块
        color_lines = [f"- {k}: {v}" for k, v in colors.items() if v and v != "#......"]
        # 构建字体锁定块
        font_lines = [f"- {k}: {v}" for k, v in typo.items() if v]
        # 构建图标锁
        icon_lib = icons.get("library", "")
        icon_inv = icons.get("inventory", [])
        icon_stroke = icons.get("stroke_width", "")

        spec_injection = f"""EXECUTION LOCK (READ BEFORE GENERATING):
Colors (do NOT deviate):
{chr(10).join(color_lines) if color_lines else '- Use the palette listed below'}

Typography:
{chr(10).join(font_lines) if font_lines else '- Use the fonts listed below'}

Icons: library={icon_lib}, inventory={icon_inv if icon_inv else 'use judgment'}
{f'Icons stroke-width: {icon_stroke}' if icon_stroke else ''}
"""

        # 构建运行时节奏指令
        rhythm_directives = {
            "anchor": ("This is an ANCHOR page (cover/ending/chapter). "
                       "Bold, dramatic layout. Follow the structural template. "
                       "Make a strong visual statement. Large typography, "
                       "generous spacing, single focal point."),
            "dense": ("This is a DENSE page (data/multi-point/comparison). "
                      "Card grids, multi-column layouts, and tables are ALLOWED. "
                      "Use cards, panels, or columns to organize information. "
                      "4-6 cards max. Keep each card focused with 1-3 data points."),
            "breathing": ("This is a BREATHING page (single concept/hero/transition). "
                          "NO multi-card grid layouts. Use generous whitespace, "
                          "dividers, a single emphasis element, or full-bleed imagery. "
                          "The page says ONE thing. Single rounded elements are fine. "
                          "Organize via naked text, rules, and negative space."),
        }
        runtime_rhythm = rhythm_directives.get(rhythm, rhythm_directives["dense"])
    else:
        # 无 spec_lock 时的通用节奏指令
        runtime_rhythm = ("Free design — choose layout density based on content. "
                          "Cover/ending: bold and dramatic. Content: clear structure.")

    return SVG_SYSTEM.format(
        spec_lock_injection=spec_injection,
        slide_type=slide_type,
        design_scheme=scheme_label,
        industry=industry_label or "None",
        layout_template=layout_label or "Default",
        custom_style=custom_style or "None",
        page_rhythm_directive=page_rhythm_label,
        layout_examples=examples,
        palette=palette,
        viewbox=viewbox,
        page_num=page_num,
        total_pages=total_pages,
        runtime_rhythm=runtime_rhythm,
    )


def _make_svg_user(slide_data: dict) -> str:
    """根据单页大纲数据构造 SVG 生成 prompt"""
    stype = slide_data.get("type", "content")
    title = slide_data.get("title", "")
    subtitle = slide_data.get("subtitle", "")
    content = slide_data.get("content", [])

    parts = [f"Generate a {stype} slide.", f"Title: {title}"]
    if subtitle and stype == "cover":
        parts.append(f"Subtitle: {subtitle}")
    if content:
        parts.append("Content:")
        for item in content:
            parts.append(f"  - {item}")
    if stype == "cover":
        parts.append("This is the COVER slide — make it bold and dramatic.")
    elif stype == "ending":
        parts.append("This is the ENDING slide — clean, memorable closing.")
    else:
        parts.append("This is a CONTENT slide — clear layout with bullet points.")
    return "\n".join(parts)


def _make_strategist_user(outline: dict, canvas_key: str, page_count: int,
                          custom_style: str, files_text: str) -> str:
    """构造策略师阶段的用户提示——传入大纲和设计上下文。"""
    slides = outline.get("slides", [])
    title = outline.get("title", "未命名")
    outline_text = json.dumps(outline, ensure_ascii=False, indent=2)

    parts = [
        f"PPT Title: {title}",
        f"Slide Count: {len(slides)}",
        f"Canvas: {canvas_key}",
    ]
    if custom_style:
        parts.append(f"Style Direction: {custom_style}")
    parts.append(f"\nFull Outline:\n```json\n{outline_text}\n```")

    if files_text:
        truncated = files_text[:500000]
        parts.append(f"\nReference Materials:\n{truncated}")

    parts.append(
        "\nBased on the outline above, generate the design specification "
        "and execution lock. Follow the STRATEGIST_SYSTEM instructions exactly. "
        "Output BOTH sections: design_spec.md and spec_lock.md."
    )
    return "\n".join(parts)


# ═══════════════════════════════════════
#  解析工具
# ═══════════════════════════════════════

def _extract_json(text: str) -> dict:
    """从文本中提取 JSON 对象（兼容 markdown 代码块包裹）"""
    text = text.strip()
    m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if m:
        text = m.group(1).strip()
    # 尝试找到最外层 { ... }
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if m:
        text = m.group(0)
    return json.loads(text)


def _parse_design_output(raw: str) -> tuple:
    """从策略师 API 响应中提取 design_spec.md 和 spec_lock.md 内容。
    返回 (design_spec_text, spec_lock_text)。"""
    design_spec = ""
    spec_lock = ""

    # 匹配 ---SECTION: design_spec.md--- ... ---SECTION: spec_lock.md---
    m = re.search(
        r'---SECTION:\s*design_spec\.md---\s*\n(.*?)'
        r'---SECTION:\s*spec_lock\.md---\s*\n(.*)',
        raw, re.DOTALL | re.IGNORECASE)
    if m:
        design_spec = m.group(1).strip()
        spec_lock = m.group(2).strip()
    else:
        # Fallback: try to find the sections independently
        m_ds = re.search(
            r'---SECTION:\s*design_spec\.md---\s*\n(.*?)(?=---SECTION:|$)',
            raw, re.DOTALL | re.IGNORECASE)
        if m_ds:
            design_spec = m_ds.group(1).strip()
        m_sl = re.search(
            r'---SECTION:\s*spec_lock\.md---\s*\n(.*)',
            raw, re.DOTALL | re.IGNORECASE)
        if m_sl:
            spec_lock = m_sl.group(1).strip()

    if not spec_lock:
        # Last fallback: treat whole response as spec_lock if it starts with ##
        if raw.strip().startswith("##"):
            spec_lock = raw.strip()

    return design_spec, spec_lock


def _parse_spec_lock(text: str) -> dict:
    """解析 spec_lock.md 文本为嵌套字典。
    格式：## section_name\n- key: value\n- key: value"""
    result: dict[str, dict] = {}
    current_section = ""
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("## "):
            current_section = stripped[3:].strip()
            result[current_section] = {}
        elif stripped.startswith("- ") and current_section:
            kv = stripped[2:]
            if ":" in kv:
                key, _, value = kv.partition(":")
                key = key.strip()
                value = value.strip()
                if current_section == "page_rhythm":
                    result[current_section][key] = value
                elif current_section == "page_charts":
                    result[current_section][key] = value
                elif current_section == "icons" and key == "inventory":
                    result[current_section]["inventory"] = [
                        n.strip() for n in value.split(",") if n.strip()
                    ]
                elif current_section == "forbidden":
                    result[current_section][key] = value
                else:
                    result[current_section][key] = value
    return result


def _extract_svg(text: str) -> str | None:
    """从 DeepSeek 响应中提取 SVG — 三层 fallback：
    1) 完整 ```svg...``` 代码块
    2) 不闭合的 fence 开头（手动 strip fence 行后提取）
    3) 直接 <svg> 标签（容忍截断/无闭合 </svg>）
    """
    text = text.strip()
    # Layer 1: 完整且正确闭合的 markdown 代码块
    m = re.search(r'```(?:svg|xml|html)?\s*\n(.*?)\n```', text, re.DOTALL)
    if m:
        return m.group(1).strip()
    # Layer 2: 以 ``` 开头但未正确闭合（DeepSeek 截断常见）
    if text.startswith('```'):
        lines = text.split('\n')
        content = '\n'.join(lines[1:]) if len(lines) > 1 else ''
        # 剥离末尾残留的 ```
        if content.rstrip().endswith('```'):
            content = content.rstrip()[:-3].strip()
        m = re.search(r'<svg\b[\s\S]*', content)
        if m:
            return m.group(0).strip()
    else:
        # Layer 3: 直接查找 <svg> 内容，容忍缺失 </svg>
        m = re.search(r'<svg\b[\s\S]*', text)
        if m:
            svg = m.group(0).strip()
            # 尝试截断到 </svg>；缺失也接受
            end = svg.find('</svg>')
            if end != -1:
                svg = svg[:end + 6]
            return svg
    return None


def _validate_svg(svg: str, viewbox: str) -> bool:
    """基本验证 SVG 是否合法"""
    if "<svg" not in svg or "</svg>" not in svg:
        return False
    if "viewBox" not in svg and "viewbox" not in svg:
        return False
    # 不强制要求特定 viewBox，只检查结构
    return len(svg) > 100


def _sanitize_duplicate_attrs(svg_text: str) -> str:
    """移除 SVG 标签中的重复 XML 属性，保留首次出现。
    AI 生成偶尔出现 fill="#xxx" fill="#yyy" 同类重复，会导致 ET.parse 崩溃。"""
    # 匹配属性名（含命名空间前缀）和双引号或单引号值
    _ATTR_RE = re.compile(r"(\b\w+(?::\w+)?)\s*=\s*(\"[^\"]*\"|'[^']*')")

    def _dedupe_attrs(match):
        tag = match.group(0)
        # 先清理残缺属性名（末尾带 - 且没有 = 值的，如 stroke- ）
        tag = re.sub(r'\s+\w+-(?=\s|/?>)', '', tag)
        seen = set()
        parts = []
        last = 0
        for m in _ATTR_RE.finditer(tag):
            parts.append(tag[last:m.start()])
            if m.group(1) not in seen:
                parts.append(m.group(0))
                seen.add(m.group(1))
            last = m.end()
        parts.append(tag[last:])
        # 二次清理——去掉去重后残留的残缺属性
        result = ''.join(parts)
        result = re.sub(r'\s+\w+-(?=\s|/?>)', '', result)
        return result

    # 匹配开标签（含命名空间前缀）或自闭合标签
    return re.sub(r'<[A-Za-z]\w*(?::\w+)?\b[^>]*/?>', _dedupe_attrs, svg_text, flags=re.S)


def _sanitize_filename(name: str) -> str:
    """将标题转为安全文件名"""
    name = unicodedata.normalize('NFC', name)
    name = re.sub(r'[\\/:*?"<>|]', '', name)
    name = name.strip()[:50]
    return name or "slide"


# ═══════════════════════════════════════
#  文件内容提取（尽力而为，不强制依赖）
# ═══════════════════════════════════════

def _read_file_text(path: str) -> str:
    """读取文件文本内容，根据扩展名选择最佳方式"""
    ext = Path(path).suffix.lower()
    if ext in {".txt", ".md", ".markdown"}:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    if ext == ".pdf":
        try:
            import fitz  # PyMuPDF
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
    # 其他格式
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return f"[无法读取: {Path(path).name}]"


def _hex_luminance(hex_color: str) -> float:
    """计算 hex 颜色相对亮度 (0-1)，用于判断浅色/深色模式"""
    hex_color = hex_color.lstrip('#')
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    return 0.299 * r + 0.587 * g + 0.114 * b


def _extract_pptx_style(filepath: str) -> str:
    """从参考 PPTX 提取配色+字体风格摘要，供 prompt 注入。
    返回 ~200-400 字符的浓缩描述，失败返回 ""。
    """
    import zipfile
    from xml.etree import ElementTree as ET

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

            # 提取配色方案
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

            # 提取字体方案
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

    # 字号采样（python-pptx）
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

    # 浅色/深色模式检测
    mode = ""
    dk1 = colors.get('dk1', '').upper()
    lt1 = colors.get('lt1', '').upper()
    if dk1 and lt1:
        if _hex_luminance(dk1) < _hex_luminance(lt1):
            mode = " | Light mode"
        else:
            mode = " | Dark mode"

    # 组装摘要
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


_IMAGE_STYLE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def _extract_image_style(filepath: str) -> str:
    """从参考图片提取主色调色板，供 prompt 注入。
    使用 PIL 量化后提取高频颜色，返回 ~150-250 字符的浓缩描述，失败返回 ""。
    """
    try:
        from PIL import Image
    except ImportError:
        return ""

    try:
        # 兼容 Pillow 10+（LANCZOS → Resampling.LANCZOS）
        try:
            from PIL.Image import Resampling
            resample = Resampling.LANCZOS
        except ImportError:
            resample = Image.LANCZOS
        img = Image.open(filepath).convert("RGB")
        # 缩放到小尺寸加速处理
        img = img.resize((150, 150), resample)
        # 量化到 16 色
        q = img.quantize(16)
        # 获取调色板
        palette = q.getpalette()[:48]  # 16 colors × 3 (RGB)
        # 统计每种颜色的像素数
        pixels = list(q.getdata())
        counts: dict[int, int] = {}
        for p in pixels:
            counts[p] = counts.get(p, 0) + 1
        # 按频率排序取前 8 色
        top = sorted(counts.items(), key=lambda x: -x[1])[:8]
        hex_colors = []
        for idx, _ in top:
            r, g, b = palette[idx * 3], palette[idx * 3 + 1], palette[idx * 3 + 2]
            hex_colors.append(f"#{r:02X}{g:02X}{b:02X}")

        # 计算整体亮度判断明暗模式
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


def _extract_image_text(filepath: str) -> str:
    """从图片中提取文本（OCR）。需要 pytesseract + Tesseract-OCR 引擎。
    返回提取的文本，失败或未安装返回空字符串。"""
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


# ═══════════════════════════════════════
#  依赖检查
# ═══════════════════════════════════════

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
        # Fallback: 直接安装核心包
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
        # 即使 pip 报 warning 也尝试成功
        return True
    except Exception as e:
        if log_fn:
            log_fn(f"安装失败: {e}")
        return False


# ═══════════════════════════════════════
#  核心 Worker
# ═══════════════════════════════════════

class PPTGenerateWorker(QThread):
    """后台两阶段 PPT 生成：大纲 → SVG → PPTX"""

    log_msg = Signal(str)
    progress = Signal(int, int, str)  # current, total, stage_name
    finished = Signal(bool, str)      # success, output_path
    outline_ready = Signal(dict, str)  # outline dict, project_dir
    slide_started = Signal(int, str, str)  # page_num, title, slide_type
    slide_completed = Signal(int, str, str, bool)  # page_num, title, svg_path, success

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

    # ══════ 辅助方法 ══════

    def _create_project_dirs(self, ppt_title: str) -> Path:
        """创建项目目录结构并设置 self._project_dir"""
        date_str = datetime.now().strftime("%Y%m%d")
        dir_name = f"{ppt_title}_{self.canvas_key}_{date_str}"
        dir_name = re.sub(r'[\\/:*?"<>|]', '_', dir_name)[:80]
        base = Path(self.output_dir) if self.output_dir else _PPT_PROJECTS_DIR
        self._project_dir = base / dir_name
        for d in ["svg_output", "svg_final", "exports", "images", "notes"]:
            (self._project_dir / d).mkdir(parents=True, exist_ok=True)
        self._log(f"  项目目录: {self._project_dir}")
        return self._project_dir

    # ══════ 阶段 1: 生成大纲 ══════

    def _generate_outline(self) -> dict:
        self._log("=" * 50)
        self._log("阶段 1/3: 生成 PPT 大纲...")
        self.progress.emit(0, 100, "outline")

        if self.revision_notes:
            self._log(f"  [修改建议] {self.revision_notes[:200]}")

        # 提取样式参考：优先 PPTX，其次图片
        style_text = ""
        for fp in self.file_paths:
            if not self._is_running:
                raise InterruptedError()
            if not os.path.isfile(fp):
                continue
            ext = Path(fp).suffix.lower()
            if ext == ".pptx":
                self._log(f"  提取参考样式: {os.path.basename(fp)}")
                extracted = _extract_pptx_style(fp)
                if extracted:
                    style_text = extracted
                    self._log(f"    [OK] {extracted[:120]}...")
                else:
                    self._log(f"    [WARN] 未能提取样式信息")
                break
        # 如果没有 PPTX，尝试从图片提取调色板
        if not style_text:
            for fp in self.file_paths:
                if not self._is_running:
                    raise InterruptedError()
                if not os.path.isfile(fp):
                    continue
                if Path(fp).suffix.lower() in _IMAGE_STYLE_EXTS:
                    self._log(f"  提取图片色板: {os.path.basename(fp)}")
                    extracted = _extract_image_style(fp)
                    if extracted:
                        style_text = extracted
                        self._log(f"    [OK] {extracted[:120]}...")
                    else:
                        self._log(f"    [WARN] 未能提取图片色板")
                    break

        # 读取参考文件内容（跳过图片文件）
        files_text = ""
        for fp in self.file_paths:
            if not self._is_running:
                raise InterruptedError()
            if not os.path.isfile(fp):
                continue
            if Path(fp).suffix.lower() in _IMAGE_STYLE_EXTS:
                self._log(f"  读取参考图片: {os.path.basename(fp)}")
                img_text = _extract_image_text(fp)
                if img_text:
                    self._log(f"    [OK] 从图片提取到 {len(img_text)} 字符文本")
                    files_text += f"\n--- Image Text: {os.path.basename(fp)} ---\n{img_text[:500000]}\n"
                else:
                    self._log(f"    [INFO] 图片文本提取跳过（pytesseract 未安装或识别失败）")
                continue
            self._log(f"  读取参考文件: {os.path.basename(fp)}")
            content = _read_file_text(fp)
            # 过滤读取失败的占位字符串，不将其作为内容注入提示
            if content.startswith("[") and ("读取失败" in content or "无法读取" in content):
                self._log(f"    [WARN] 跳过无法读取的文件")
                continue
            files_text += f"\n--- File: {os.path.basename(fp)} ---\n{content[:500000]}\n"

        # 将样式方向前置到参考材料中
        if style_text:
            files_text = f"[STYLE DIRECTION]\n{style_text}\n\n[CONTENT REFERENCES]{files_text}"

        # 构造带样式注入的 system prompt
        style_section = _format_style_section(style_text)

        # 构建修改反馈上下文
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
                    prev_summary.append(
                        f"  - [{s.get('type', 'content')}] {st}")
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

        user_prompt = _make_outline_user(
            self.prompt, self.design_scheme_label, self.industry_label,
            self.layout_label, self.custom_style, self.page_count, files_text)

        self._log(f"  请求 DeepSeek ({self.model}) 生成 {self.page_count} 页大纲...")
        raw = _call_deepseek_with_retry(
            self.api_key, self.base_url, self.model,
            system_prompt, user_prompt,
            temperature=0.7, max_tokens=32768, json_mode=True,
            log_fn=self._log)
        outline = _extract_json(raw)
        slides = outline.get("slides", [])
        if not slides:
            raise RuntimeError("大纲解析失败：未找到 slides 数组")

        ppt_title = outline.get("title", "未命名演示文稿")
        self._log(f"  大纲已生成: \"{ppt_title}\" — {len(slides)} 页")
        self.progress.emit(100, 100, "outline")
        return outline

    # ══════ 阶段 1.5: 策略师 — 设计规范 + 执行锁 ══════

    def _generate_design_spec(self, outline: dict):
        """策略师阶段：基于大纲生成 design_spec.md 和 spec_lock.md。
        失败时 spec_lock 保持 None，后续 SVG 生成回退到旧行为。"""
        try:
            self._log("=" * 50)
            self._log("阶段 1.5/3: 生成设计规范和执行锁...")
            self.progress.emit(0, 100, "strategist")

            # 收集参考文件内容
            files_text = ""
            for fp in self.file_paths:
                if not self._is_running:
                    raise InterruptedError()
                if not os.path.isfile(fp):
                    continue
                text = _read_file_text(fp)
                if text:
                    files_text += f"\n=== File: {os.path.basename(fp)} ===\n{text[:300000]}"

            user = _make_strategist_user(
                outline, self.canvas_key, self.page_count,
                self.custom_style, files_text)

            self._log(f"  请求 DeepSeek ({self.model}) 生成设计规范...")
            raw = _call_deepseek_with_retry(
                self.api_key, self.base_url, self.model,
                _STRATEGIST_SYSTEM_CACHED, user,
                temperature=0.3, max_tokens=32768, json_mode=False,
                log_fn=self._log)

            design_spec, spec_lock_text = _parse_design_output(raw)

            if not spec_lock_text:
                self._log("  [WARN] 策略师未能生成 spec_lock，使用默认设计参数")
                self._spec_lock = None
                self.progress.emit(100, 100, "strategist")
                return

            # 写入文件
            if self._project_dir:
                (self._project_dir / "design_spec.md").write_text(
                    design_spec or "", encoding="utf-8")
                (self._project_dir / "spec_lock.md").write_text(
                    spec_lock_text, encoding="utf-8")

            self._spec_lock = _parse_spec_lock(spec_lock_text)
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

    # ══════ 阶段 2: 逐页 SVG ══════

    def _generate_svgs(self, outline: dict):
        self._log("=" * 50)
        self._log("阶段 2/3: 逐页生成 SVG 幻灯片...")

        slides = outline["slides"]
        total = len(slides)
        svg_dir = self._project_dir / "svg_output"
        svg_dir.mkdir(parents=True, exist_ok=True)
        self.progress.emit(0, total, "svg")

        failed = []  # (i, slide) tuples for retry

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

        # 重试失败的幻灯片（最多一次，稍高 temperature）
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
        """生成单个 SVG 幻灯片。返回 True 表示成功。"""
        try:
            system = _make_svg_system(
                slide_type,
                self.design_scheme_label, self.industry_label or "",
                self.layout_label or "", self.layout_key or "", self.custom_style,
                self.design_scheme_data, self.industry_data,
                self.viewbox, page_num, total,
                spec_lock=self._spec_lock)
            user = _make_svg_user(slide)

            raw = _call_deepseek_with_retry(
                self.api_key, self.base_url, self.model,
                system, user,
                temperature=temperature, max_tokens=65536, json_mode=False,
                log_fn=self._log)

            svg = _extract_svg(raw)
            if svg:
                svg = _sanitize_duplicate_attrs(svg)
            else:
                svg = _sanitize_duplicate_attrs(raw)
            if not svg or not _validate_svg(svg, self.viewbox):
                preview = raw[:200].replace('\n', '\\n') if raw else "(empty)"
                self._log(f"    [DEBUG] raw response preview: {preview}")
                if not svg.strip():
                    self._log(f"    [ERR] 空响应，跳过 {slide_title}")
                    self.slide_completed.emit(page_num, slide_title, "", False)
                    self.progress.emit(page_num, total, "svg")
                    return False
                self._log(f"    [WARN] SVG 解析失败，使用原始输出")

            safe_name = _sanitize_filename(slide_title)
            filepath = svg_dir / f"{page_num:02d}_{safe_name}.svg"
            # 防御性确保父目录存在（防止某些边界条件下目录丢失）
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(svg, encoding="utf-8")

            # Write speaker notes if present
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
            self._log(f"    [TRACEBACK] {_safe_traceback()}")
            self.slide_completed.emit(page_num, slide_title, "", False)
            self.progress.emit(page_num, total, "svg")
            return False

    def _run_quality_check(self):
        """运行 SVG 质量检查，记录问题到日志"""
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

    # ══════ 阶段 3: 后处理 + 导出 ══════

    def _finalize_and_export(self) -> str:
        self._log("=" * 50)
        self._log("阶段 3/3: 后处理 SVG → 导出 PPTX...")

        # 3a: finalize_svg
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

        # 3b: svg_to_pptx
        self._log("  运行 svg_to_pptx 导出 PPTX...")
        try:
            from svg_to_pptx.pptx_builder import create_pptx_with_native_svg
            from svg_to_pptx.pptx_discovery import find_svg_files, find_notes_files
        except ImportError as e:
            raise RuntimeError(
                f"无法导入 svg_to_pptx 模块: {e}\n"
                "请确保 ppt-master 完整且依赖已安装")

        # 判断优先使用 svg_final（后处理）还是 svg_output（原始）
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

        # 二次清理：确保所有 SVG 文件（含 finalize_svg 产出）无重复属性
        sanitized_count = 0
        for svg_path in svg_files:
            try:
                original = svg_path.read_text(encoding="utf-8")
                cleaned = _sanitize_duplicate_attrs(original)
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

    # ══════ 主入口 ══════

    def run(self):
        if self._phase == "outline":
            self._run_outline_phase()
        elif self._phase == "svg_export":
            self._run_svg_export_phase()
        else:
            self._run_full()

    def _run_outline_phase(self):
        """仅运行 Phase 1：生成大纲 + 创建项目目录"""
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

            # 创建项目目录
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
            self._log(f"[TRACEBACK] {_safe_traceback()}")
            self.finished.emit(False, "")

    def _run_svg_export_phase(self):
        """运行 Phase 2+3：SVG 生成 + 导出 PPTX（使用已存储的 outline 和 project_dir）"""
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

            # 阶段 1.5: 策略师
            if self._is_running:
                self._generate_design_spec(outline)

            # 阶段 2
            self._generate_svgs(outline)
            self._run_quality_check()

            # 阶段 3
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
            self._log(f"[TRACEBACK] {_safe_traceback()}")
            self.finished.emit(False, "")

    def _run_full(self):
        """原始完整流程（向后兼容）"""
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
            self._log(f"[TRACEBACK] {_safe_traceback()}")
            self.finished.emit(False, "")


# ═══════════════════════════════════════
#  SlideCard — 幻灯片预览卡片
# ═══════════════════════════════════════

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
    clicked = Signal(str)  # emits svg_path when clicked (done state)

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

        # 状态图标
        self._status_lbl = QLabel(_SLIDE_STATUS_ICONS["waiting"])
        self._status_lbl.setFixedWidth(24)
        self._status_lbl.setStyleSheet(
            "font-size: 16px; background: transparent;")
        layout.addWidget(self._status_lbl)

        # 页码
        num_lbl = QLabel(f"{page_num:02d}")
        num_lbl.setFixedWidth(28)
        num_lbl.setStyleSheet(
            "font-size: 14px; font-weight: 700; color: #9CA3AF;"
            " background: transparent;")
        layout.addWidget(num_lbl)

        # 类型徽标
        badge = QLabel(type_label)
        badge.setFixedWidth(40)
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet(
            f"font-size: 11px; font-weight: 600; color: white;"
            f" background-color: {type_color}; border-radius: 6px;"
            f" padding: 2px 6px;")
        layout.addWidget(badge)

        # 标题 + 内容预览
        text_col = QVBoxLayout()
        text_col.setSpacing(1)
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            "font-size: 13px; font-weight: 600; color: #1E1E2E;"
            " background: transparent;")
        title_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        text_col.addWidget(title_lbl)

        if content_preview:
            preview = content_preview[:60] + ("..." if len(content_preview) > 60 else "")
            cp_lbl = QLabel(preview)
            cp_lbl.setStyleSheet(
                "font-size: 11px; color: #9CA3AF; background: transparent;")
            text_col.addWidget(cp_lbl)

        layout.addLayout(text_col, 1)

    def set_status(self, status: str, svg_path: str = ""):
        """更新状态: waiting | generating | done | failed"""
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


# ═══════════════════════════════════════
#  OutlineConfirmDialog — 大纲确认弹窗
# ═══════════════════════════════════════

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

        # 标题
        ppt_title = outline.get("title", "未命名演示文稿")
        subtitle = outline.get("subtitle", "")
        header = QLabel(f"📋  {ppt_title}")
        header.setStyleSheet(
            "font-size: 20px; font-weight: 700; color: #1E1E2E; background: transparent;")
        root.addWidget(header)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setStyleSheet(
                "font-size: 13px; color: #6B7280; background: transparent;")
            root.addWidget(sub)

        # 统计
        slides = outline.get("slides", [])
        stats = QLabel(f"共 {len(slides)} 页幻灯片")
        stats.setStyleSheet(
            "font-size: 13px; color: #6366F1; font-weight: 600; background: transparent;")
        root.addWidget(stats)

        # 可滚动的幻灯片列表
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

            # 页码
            num = QLabel(f"{i + 1:02d}")
            num.setFixedWidth(28)
            num.setStyleSheet(
                "font-size: 14px; font-weight: 700; color: #9CA3AF;"
                " background: transparent;")
            rl.addWidget(num)

            # 类型徽标
            badge = QLabel(stype_label)
            badge.setFixedWidth(40)
            badge.setAlignment(Qt.AlignCenter)
            badge.setStyleSheet(
                f"font-size: 11px; font-weight: 600; color: white;"
                f" background-color: {stype_color}; border-radius: 6px;"
                f" padding: 2px 6px;")
            rl.addWidget(badge)

            # 文字区
            text_col = QVBoxLayout()
            text_col.setSpacing(2)
            t = QLabel(title)
            t.setStyleSheet(
                "font-size: 14px; font-weight: 600; color: #1E1E2E;"
                " background: transparent;")
            text_col.addWidget(t)
            if content:
                c_preview = " · ".join(content[:3])
                if len(c_preview) > 100:
                    c_preview = c_preview[:100] + "..."
                c = QLabel(c_preview)
                c.setWordWrap(True)
                c.setStyleSheet(
                    "font-size: 12px; color: #6B7280; background: transparent;")
                text_col.addWidget(c)
            rl.addLayout(text_col, 1)

            scroll_layout.addWidget(row)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        root.addWidget(scroll, 1)

        # 反馈输入区
        fb_label = QLabel("修改建议（可选）：")
        fb_label.setStyleSheet(
            "font-size: 13px; color: #6B7280; background: transparent;"
            " font-weight: 600;")
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

        # 按钮区
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


# ═══════════════════════════════════════
#  工具函数
# ═══════════════════════════════════════

def _open_file_or_dir(path: str):
    """跨平台文件/目录打开"""
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.run(["open", path])
    else:
        subprocess.run(["xdg-open", path])


# ═══════════════════════════════════════
#  插件主类
# ═══════════════════════════════════════

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
        self._api_section_visible = True
        self._last_output_path = ""

        # Two-phase flow state
        self._stored_outline: dict | None = None
        self._stored_project_dir: str = ""
        self._stored_worker_params: dict = {}
        self._slide_cards: dict[int, SlideCard] = {}
        self._slide_list_layout: QVBoxLayout | None = None
        self._slide_placeholder: QLabel | None = None
        self._phase: str = ""  # "" | "outline" | "svg_export"

        # Widgets to hold references
        self._api_toggle_btn: QPushButton | None = None
        self._api_content: QFrame | None = None
        self._input_api: QLineEdit | None = None
        self._model_combo: QComboBox | None = None

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
        scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        outer = QVBoxLayout(content)
        outer.setContentsMargins(56, 44, 56, 52)
        outer.setSpacing(0)

        # ── 顶栏 ──
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

        # ── 标题 ──
        title = QLabel(self.icon + "  " + self.name)
        title.setStyleSheet(
            "font-size: 28px; font-weight: 700; color: " + C_TEXT
            + "; background: transparent;")
        subtitle = QLabel(
            "输入主题，DeepSeek AI 自动生成大纲和幻灯片 → 导出原生 PPTX")
        subtitle.setStyleSheet(
            "font-size: 14px; color: " + C_TEXT_SUB
            + "; background: transparent; margin-bottom: 2px;")
        outer.addWidget(title)
        outer.addWidget(subtitle)
        outer.addSpacing(20)

        # ── 左右分栏 ──
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

        # 1. API 设置（可折叠）
        layout.addWidget(self._build_api_section())
        layout.addWidget(self._make_sep())
        # 2. 提示词
        layout.addWidget(self._build_prompt_section())
        layout.addWidget(self._make_sep())
        # 3. 设计选项
        layout.addWidget(self._build_design_section())
        layout.addWidget(self._make_sep())
        # 4. 输出目录
        layout.addWidget(self._build_output_section())
        layout.addWidget(self._make_sep())
        # 5. 参考文件
        layout.addWidget(self._build_ref_section())
        layout.addSpacing(16)
        # 6. 操作区
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

        # 折叠按钮
        self._api_toggle_btn = QPushButton("⚙️  API 设置 ▼")
        self._api_toggle_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none;"
            " font-size: 14px; font-weight: 700; color: " + C_TEXT
            + "; text-align: left; padding: 0; }"
            "QPushButton:hover { color: " + C_PRIMARY + "; }")
        self._api_toggle_btn.setCursor(Qt.PointingHandCursor)
        self._api_toggle_btn.clicked.connect(self._toggle_api_section)
        wl.addWidget(self._api_toggle_btn)

        # 折叠内容
        self._api_content = QFrame()
        self._api_content.setStyleSheet(
            "QFrame { background: #F8F9FC; border-radius: 10px;"
            " padding: 12px; }")
        ac = QVBoxLayout(self._api_content)
        ac.setContentsMargins(14, 14, 14, 14)
        ac.setSpacing(10)

        # API Key
        ak_lbl = QLabel("API Key")
        ak_lbl.setStyleSheet(
            "font-size: 12px; font-weight: 600; color: " + C_TEXT_SUB
            + "; background: transparent;")
        ac.addWidget(ak_lbl)
        self._input_api = QLineEdit()
        self._input_api.setPlaceholderText("sk-...")
        self._input_api.setEchoMode(QLineEdit.Password)
        self._input_api.setText(os.environ.get("DEEPSEEK_API_KEY", ""))
        self._input_style(self._input_api)
        ac.addWidget(self._input_api)

        # 模型 + Base URL 同行
        mrow = QHBoxLayout()
        mrow.setSpacing(10)
        # 模型
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
        ac.addLayout(mrow)

        wl.addWidget(self._api_content)
        return wrapper

    def _toggle_api_section(self):
        self._api_section_visible = not self._api_section_visible
        self._api_content.setVisible(self._api_section_visible)
        arrow = "▼" if self._api_section_visible else "▶"
        self._api_toggle_btn.setText(f"⚙️  API 设置 {arrow}")

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
            "font-size: 11px; color: #9CA3AF; background: transparent;"
            " padding: 0 4px;")
        self._prompt_count.setAlignment(Qt.AlignRight)
        wl.addWidget(self._prompt_count)
        return wrapper

    def _on_prompt_changed(self):
        text = self._prompt_input.toPlainText()
        count = len(text)
        self._prompt_count.setText(f"已输入 {count} 字")

    # ── 设计选项 ──

    def _build_design_section(self) -> QWidget:
        wrapper = QWidget()
        wrapper.setStyleSheet("background: transparent;")
        wl = QVBoxLayout(wrapper)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setSpacing(10)
        wl.addWidget(self._section_header("🎨", "设计选项"))

        # 自定义风格
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

        # 参考样式 PPTX 上传
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
        ref_btn.clicked.connect(
            lambda: self._pick_ref_style())
        ref_row.addWidget(ref_btn)
        wl.addLayout(ref_row)

        # 页数 + 画布同行
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
            "font-size: 11px; color: #9CA3AF; background: transparent;"
            " padding: 0 4px;")
        wl.addWidget(hint)
        return wrapper

    def _pick_output_dir(self):
        path = QFileDialog.getExistingDirectory(
            self._workspace, "选择输出目录",
            str(_PPT_PROJECTS_DIR))
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
            "font-size: 11px; color: #9CA3AF; background: transparent;"
            " padding: 0 4px;")
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
        btn.clicked.connect(
            lambda: self._pick_ref_file(inp))
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

        # 头部 + 打开按钮
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
            " border-radius: 8px; padding: 8px 14px; font-size: 12px;"
            " color: #333; }"
            "QPushButton:hover { background: #E5E7EB; }")
        self._open_btn.setCursor(Qt.PointingHandCursor)
        self._open_btn.clicked.connect(self._open_output)
        self._open_btn.setVisible(False)
        header_row.addWidget(self._open_btn)
        layout.addLayout(header_row)

        # QSplitter: 上=幻灯片预览 / 下=日志
        splitter = QSplitter(Qt.Vertical)
        splitter.setStyleSheet(
            "QSplitter::handle { background: #E5E7EB; height: 2px; }")

        # ── 上部: 幻灯片预览区 ──
        slide_panel = QFrame()
        slide_panel.setStyleSheet(
            "QFrame { background: #FAFBFC; border: 1px solid #ECEDF0;"
            " border-radius: 10px; }")
        sp_layout = QVBoxLayout(slide_panel)
        sp_layout.setContentsMargins(12, 10, 12, 10)
        sp_layout.setSpacing(6)

        slide_header = QLabel("幻灯片预览")
        slide_header.setStyleSheet(
            "font-size: 13px; font-weight: 700; color: #6B7280;"
            " background: transparent;")
        sp_layout.addWidget(slide_header)

        # 可滚动卡片列表
        slide_scroll = QScrollArea()
        slide_scroll.setWidgetResizable(True)
        slide_scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }")
        slide_list_widget = QWidget()
        slide_list_widget.setStyleSheet("background: transparent;")
        self._slide_list_layout = QVBoxLayout(slide_list_widget)
        self._slide_list_layout.setContentsMargins(0, 0, 0, 0)
        self._slide_list_layout.setSpacing(6)

        # 占位提示
        self._slide_placeholder = QLabel(
            "点击「生成 PPT」开始\n生成后在此预览每页幻灯片")
        self._slide_placeholder.setAlignment(Qt.AlignCenter)
        self._slide_placeholder.setStyleSheet(
            "font-size: 13px; color: #9CA3AF; background: transparent;"
            " padding: 40px 0;")
        self._slide_list_layout.addWidget(self._slide_placeholder)
        self._slide_list_layout.addStretch()

        slide_scroll.setWidget(slide_list_widget)
        sp_layout.addWidget(slide_scroll, 1)
        splitter.addWidget(slide_panel)

        # ── 下部: 日志区 ──
        log_panel = QFrame()
        log_panel.setStyleSheet(
            "QFrame { background: #FAFBFC; border: 1px solid #ECEDF0;"
            " border-radius: 10px; }")
        lp_layout = QVBoxLayout(log_panel)
        lp_layout.setContentsMargins(12, 10, 12, 10)
        lp_layout.setSpacing(6)

        log_sub_header = QLabel("生成日志")
        log_sub_header.setStyleSheet(
            "font-size: 13px; font-weight: 700; color: #6B7280;"
            " background: transparent;")
        lp_layout.addWidget(log_sub_header)

        self._log_area = QTextEdit()
        self._log_area.setReadOnly(True)
        self._log_area.setStyleSheet(
            "QTextEdit { border: 1px solid #E5E7EB;"
            " border-radius: 8px; padding: 10px;"
            " background-color: " + C_LOG_BG
            + "; font-size: 12px; color: " + C_TEXT
            + "; font-family: 'Consolas', 'Courier New', monospace; }")
        lp_layout.addWidget(self._log_area, 1)
        splitter.addWidget(log_panel)

        # 初始 60:40
        total_h = 600
        splitter.setSizes([int(total_h * 0.55), int(total_h * 0.45)])
        layout.addWidget(splitter, 1)

        # 进度条
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

    # ═══════════════════════════════════════
    #  操作逻辑
    # ═══════════════════════════════════════

    def _start_generate(self, revision_notes: str = "", previous_outline: dict = None):
        api_key = self._input_api.text().strip()
        if not api_key:
            QMessageBox.warning(
                self._workspace, "提示",
                "请输入 DeepSeek API Key\n\n"
                "前往 https://platform.deepseek.com/ 获取")
            return

        prompt = self._prompt_input.toPlainText().strip()
        if not prompt:
            QMessageBox.warning(self._workspace, "提示", "请输入 PPT 主题/提示词")
            return

        # 依赖检查
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

        base_url = DS_BASE_URL
        model = self._model_combo.currentText().strip()
        if not model:
            model = DS_MODELS[0]
        page_count = self._page_spin.value()
        canvas_key = self._canvas_combo.currentData()
        viewbox = CANVAS_VIEWBOX.get(canvas_key, "0 0 1280 720")

        # 设计选项 — 固定默认值（UI 已简化为仅自定义风格 + 参考上传）
        scheme = DESIGN_SCHEMES[1]     # 通用/多用途
        industry = INDUSTRY_PALETTES[0]  # 不使用行业配色
        layout = LAYOUT_TEMPLATES[0]   # 默认布局
        custom_style = self._custom_style_input.toPlainText().strip()

        # 输出目录
        output_dir = self._output_dir_input.text().strip()
        if not output_dir:
            output_dir = str(_PPT_PROJECTS_DIR)

        file_paths = []
        # 参考样式 PPTX（优先级最高，放在列表首位）
        if self._ref_style_input:
            ref_style = self._ref_style_input.text().strip()
            if ref_style and os.path.isfile(ref_style):
                file_paths.append(ref_style)
        for inp, _ in self._ref_rows:
            t = inp.text().strip()
            if t and os.path.isfile(t):
                file_paths.append(t)

        # 存储参数供 phase 2 复用
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

        # UI 状态切换
        self._start_btn.setVisible(False)
        self._cancel_btn.setVisible(True)
        self._progress_bar.setVisible(True)
        self._progress_bar.setValue(0)
        self._open_btn.setVisible(False)
        self._log_area.clear()
        self._clear_slide_list()

        # Phase 1: 大纲生成
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

    def _cancel_generate(self):
        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(100)
        self._disconnect_monitor()
        self._phase = ""
        self._stored_outline = None
        self._stored_project_dir = ""
        self._reset_ui()

    def _disconnect_worker(self):
        """断开旧 Worker 的所有信号连接，防止过时信号触发回调"""
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
        # 断开共享监视器连接
        self._disconnect_monitor()
        # Phase 1: 大纲就绪后 _on_outline_ready 已接管流程，不重置 UI
        if self._phase == "outline":
            if not success:
                self._reset_ui()
                self._phase = ""
            return
        # Phase 2: SVG 生成 + 导出完成或失败
        if self._phase == "svg_export":
            self._reset_ui()
            self._phase = ""
            self._stored_outline = None
            self._stored_project_dir = ""
            if success and output_path:
                self._open_btn.setVisible(True)
                self._last_output_path = output_path
            return
        # 过时信号（阶段已被取消/清除）—— 忽略

    def _connect_monitor(self):
        """连接共享监视器的终止信号"""
        mw = self.main_window
        if mw:
            try:
                mw.stop_requested.connect(self._cancel_generate)
            except (TypeError, RuntimeError):
                pass

    def _disconnect_monitor(self):
        """断开共享监视器的终止信号"""
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
        """清空幻灯片预览列表"""
        self._slide_cards.clear()
        if self._slide_list_layout:
            # 移除 scroll area 内所有 widget
            while self._slide_list_layout.count():
                item = self._slide_list_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            # 重新添加占位符
            self._slide_placeholder = QLabel(
                "生成大纲后将在此预览每页幻灯片")
            self._slide_placeholder.setAlignment(Qt.AlignCenter)
            self._slide_placeholder.setStyleSheet(
                "font-size: 13px; color: #9CA3AF; background: transparent;"
                " padding: 40px 0;")
            self._slide_list_layout.addWidget(self._slide_placeholder)
            self._slide_list_layout.addStretch()

    def _populate_slide_list(self, outline: dict):
        """根据大纲填充幻灯片卡片（等待状态）"""
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
        """点击完成的幻灯片卡片，用系统默认程序打开 SVG"""
        if svg_path and os.path.isfile(svg_path):
            _open_file_or_dir(svg_path)

    def _on_outline_ready(self, outline: dict, project_dir: str):
        """大纲生成完成 → 存储 + 弹出确认弹窗"""
        if self._phase != "outline":
            return  # 过时信号：生成已被取消或阶段已切换
        self._stored_outline = outline
        self._stored_project_dir = project_dir

        # 先填充预览列表
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
        else:  # cancel
            self._phase = ""
            self._stored_outline = None
            self._stored_project_dir = ""
            self._clear_slide_list()
            self._reset_ui()

    def _start_phase2(self):
        """确认大纲后，启动 Phase 2: SVG 生成 + PPTX 导出"""
        self._phase = "svg_export"
        # 显式设置 Phase 2 UI 状态
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
        """幻灯片开始生成 → 更新卡片为 generating 状态"""
        card = self._slide_cards.get(page_num)
        if card:
            card.set_status("generating")

    def _on_slide_completed(self, page_num: int, title: str,
                            svg_path: str, success: bool):
        """幻灯片生成完成 → 更新卡片状态"""
        card = self._slide_cards.get(page_num)
        if card:
            if success:
                card.set_status("done", svg_path)
            else:
                card.set_status("failed")
