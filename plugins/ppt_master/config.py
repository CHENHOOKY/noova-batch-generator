"""PPT 大师 —— 配置常量、路径与设计系统"""

import re
import sys
from pathlib import Path

# ═══════════════════════════════════════
#  路径常量
# ═══════════════════════════════════════
_PPT_SCRIPTS_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "ppt-master" / "skills" / "ppt-master" / "scripts"
)
_PPT_PROJECTS_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "ppt-master" / "projects"
)

_REFERENCES_DIR = _PPT_SCRIPTS_DIR.parent / "references"
_TEMPLATES_DIR = _PPT_SCRIPTS_DIR.parent / "templates"
_SHARED_STANDARDS_PATH = _REFERENCES_DIR / "shared-standards.md"
_ICONS_DIR = _TEMPLATES_DIR / "icons"
_CHARTS_DIR = _TEMPLATES_DIR / "charts"
_CHARTS_INDEX_PATH = _CHARTS_DIR / "charts_index.json"
_SPEC_LOCK_REF_PATH = _TEMPLATES_DIR / "spec_lock_reference.md"

# 确保 ppt-master 脚本目录在 sys.path 中
_ppt_scripts_str = str(_PPT_SCRIPTS_DIR)
if _ppt_scripts_str not in sys.path:
    sys.path.insert(0, _ppt_scripts_str)


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
            m = re.search(r'## 1\. SVG Banned Features Blacklist(.*?)(?=## 2\.)', content, re.S)
            if m:
                cache["banned_features"] = m.group(1).strip()
            m = re.search(r'## 2\. PPT Compatibility Alternatives(.*?)(?=## 3\.)', content, re.S)
            if m:
                cache["replacements"] = m.group(1).strip()
            m = re.search(r'## 6\. Shadow & Overlay Techniques(.*?)(?=## 7\.)', content, re.S)
            if m:
                cache["shadow_rules"] = m.group(1).strip()
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
#  设计配色方案
# ═══════════════════════════════════════
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

# 行业配色
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

# 页面布局模板
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

# 画布选项
CANVAS_OPTIONS = [
    ("ppt169", "PPT 16:9 (1280×720)", "0 0 1280 720"),
    ("ppt43", "PPT 4:3 (1024×768)", "0 0 1024 768"),
    ("xiaohongshu", "小红书 (1080×1440)", "0 0 1080 1440"),
    ("wechat", "微信头图 (900×383)", "0 0 900 383"),
]

CANVAS_VIEWBOX: dict[str, str] = {k: v for k, _, v in CANVAS_OPTIONS}
CANVAS_LABELS: dict[str, str] = {k: lbl for k, lbl, _ in CANVAS_OPTIONS}
