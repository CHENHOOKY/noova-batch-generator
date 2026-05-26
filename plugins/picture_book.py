"""绘本魔法师 — AI 驱动的儿童中英双语绘本生成插件

输入主题/参数 → DeepSeek 生成故事+拼音+学习点 → 可选配图 → 导出 Markdown/PDF/PPTX

核心特色：
  - 18种视觉风格（水彩、黏土、水墨、年画...）
  - 14个场景（草地、池塘、厨房、节庆...）
  - CCLP 4.0 角色一致性锁（严格/适中/灵活）
  - 年龄驱动系统（3-12岁自动适配页数/句长/学习领域）
  - 双 API 分离：文本 API（DeepSeek）+ 出图 API（Noova 兼容）
"""

from __future__ import annotations

import importlib
import json
import os
import re
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path

# ═══════════════════  PySide6  ═══════════════════
from PySide6.QtCore import Qt, Signal, QThread, QMarginsF
from PySide6.QtGui import QFont, QPageLayout, QPageSize, QTextDocument
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QScrollArea, QFrame, QTextEdit,
    QProgressBar, QSpinBox, QCheckBox, QLineEdit,
    QFileDialog, QMessageBox,
)
from PySide6.QtPrintSupport import QPrinter

# ═══════════════════  项目内部  ═══════════════════
from plugin_base import BasePlugin
from plugins._design import NoScrollComboBox as QComboBox

# ──── 确保项目根目录在 sys.path 中 ────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ──── 导入 kart-io 引擎（目录含连字符，Python 无法直接 import，通过 importlib 加载） ────
_kart_io_path = str(_PROJECT_ROOT / 'kart-io-picture-book-wizard')
if _kart_io_path not in sys.path:
    sys.path.insert(0, _kart_io_path)

_config = importlib.import_module('engine.config')
_rules = importlib.import_module('engine.rules')

STYLES = _config.STYLES
SCENES = _config.SCENES
CHARACTERS = _config.CHARACTERS
AGE_SYSTEM = _config.AGE_SYSTEM
WATERMARK_PREVENTION = _config.WATERMARK_PREVENTION
SOUL_ELEMENTS = _config.SOUL_ELEMENTS
SUPPORTING_CHARACTERS = _config.SUPPORTING_CHARACTERS
ANIMAL_COMPANIONS = _config.ANIMAL_COMPANIONS
STORY_STRUCTURES = _config.STORY_STRUCTURES
CCLP_CONFIG = _config.CCLP_CONFIG

# ──── 补充引擎缺失的配置条目 ────
SUPPORTING_CHARACTERS["sibling"] = {
    "name_cn": "兄弟姐妹",
    "anchor": "a young Chinese child, similar age to the main character, casual everyday clothes",
    "signature": {"hair": "neat black hair", "top": "colorful t-shirt", "bottom": "casual pants", "shoes": "sneakers"},
    "relationship": "玩伴、陪伴、成长",
}
ANIMAL_COMPANIONS.update({
    "duckling": {
        "name_cn": "小鸭", "anchor": "a small fluffy yellow duckling, orange beak, webbed orange feet, round body",
        "signature": {"feathers": "soft yellow downy feathers", "beak": "small orange beak", "features": "tiny wings, waddling walk"},
    },
    "bird": {
        "name_cn": "小鸟", "anchor": "a small bright blue songbird, delicate wings, cheerful expression",
        "signature": {"feathers": "bright blue plumage", "beak": "tiny pointed beak", "features": "slender legs, melodic song"},
    },
    "butterfly": {
        "name_cn": "蝴蝶", "anchor": "a large colorful butterfly with intricate wing patterns, floating gracefully",
        "signature": {"wings": "orange and black patterned wings with white spots", "features": "delicate antennae, light floating flight"},
    },
    "frog": {
        "name_cn": "青蛙", "anchor": "a small bright green tree frog, large expressive eyes, cheerful hopping",
        "signature": {"skin": "smooth bright green", "eyes": "large round golden eyes", "features": "long jumping legs, sticky toe pads"},
    },
    "lamb": {
        "name_cn": "羊羔", "anchor": "a fluffy white baby lamb, gentle dark eyes, soft woolly coat, pink nose",
        "signature": {"wool": "soft fluffy white wool", "eyes": "gentle dark eyes", "features": "pink nose, small curly horns, bouncy walk"},
    },
})

AgeSystem = _rules.AgeSystem
PromptAssembler = _rules.PromptAssembler
StoryParams = _rules.StoryParams
create_engine = _rules.create_engine

# ──── 出图 API ────
from plugins._noova_api import NoovaAPI, MODEL_CONFIG


# ═══════════════════════════════════════════════════════
#  设计令牌
# ═══════════════════════════════════════════════════════

C_PRIMARY = "#F59E0B"
C_PRIMARY_HV = "#D97706"
C_TEXT = "#1E1E2E"
C_TEXT_SUB = "#6B7280"
C_TEXT_MUTED = "#9CA3AF"
C_BG = "#F9FAFB"
C_CARD_BG = "#FFFFFF"
C_CARD_BDR = "#ECEDF0"
C_INPUT_BG = "#FAFAFA"
C_INPUT_BDR = "#E5E7EB"
C_GREEN = "#10B981"
C_DANGER = "#EF4444"
R_SM = 8
R_MD = 12
R_LG = 14
R_XL = 24

# 文本 API 默认
DS_BASE_URL = "https://api.deepseek.com"
DS_MODELS = ["deepseek-v4-pro", "deepseek-v4-flash"]
DS_DEFAULT_MODEL = "deepseek-v4-pro"
DS_MAX_TOKENS = 16384

# 出图 API 默认
IMG_BASE_URL = "https://noova.cn"

# 水印防护级别
WM_LEVELS = {
    "level1": WATERMARK_PREVENTION["level1"],
    "level2": WATERMARK_PREVENTION["level2"],
}
DEFAULT_WM = "level2"


# ═══════════════════════════════════════════════════════
#  选项数据（从 engine/config.py 提取）
# ═══════════════════════════════════════════════════════

STYLE_OPTIONS = [
    ("storybook",       "【核心】经典绘本 Storybook"),
    ("watercolor",      "【核心】水彩 Watercolor"),
    ("gouache",         "【核心】水粉 Gouache"),
    ("crayon",          "【核心】蜡笔 Crayon"),
    ("colored-pencil",  "【核心】彩铅 Colored Pencil"),
    ("clay",            "【核心】黏土 Clay"),
    ("paper-cut",       "【核心】剪纸 Paper Cut"),
    ("dreamy",          "【氛围】梦幻 Dreamy"),
    ("fairytale",       "【氛围】童话 Fairytale"),
    ("collage",         "【氛围】拼贴 Collage"),
    ("fabric",          "【氛围】布艺 Fabric"),
    ("felt",            "【氛围】毛毡 Felt"),
    ("ink",             "【中国】水墨 Ink Wash"),
    ("ink-line",        "【中国】白描 Ink Line"),
    ("nianhua",         "【中国】年画 Nianhua"),
    ("porcelain",       "【中国】青花瓷 Porcelain"),
    ("shadow-puppet",   "【中国】皮影 Shadow Puppet"),
    ("tech",            "【专业】科技 Tech"),
]
STYLE_KEYS = [s[0] for s in STYLE_OPTIONS]
DEFAULT_STYLE = "watercolor"

SCENE_OPTIONS = [
    ("meadow",       "🌿 草地 Meadow"),
    ("pond",         "💧 池塘 Pond"),
    ("rice-paddy",   "🌾 稻田 Rice Paddy"),
    ("stars",        "⭐ 星空 Stars"),
    ("forest",       "🌲 森林 Forest"),
    ("kitchen",      "🍳 厨房 Kitchen"),
    ("courtyard",    "🏠 庭院 Courtyard"),
    ("market",       "🛒 集市 Market"),
    ("temple",       "🛕 寺庙 Temple"),
    ("festival",     "🎉 节庆 Festival"),
    ("grandma-room", "👵 奶奶的房间 Grandma's Room"),
    ("kindergarten", "🎒 幼儿园 Kindergarten"),
    ("soccer-field", "⚽ 足球场 Soccer Field"),
    ("playground",   "🤸 操场 Playground"),
]
SCENE_KEYS = [s[0] for s in SCENE_OPTIONS]
DEFAULT_SCENE = "meadow"

CHARACTER_OPTIONS = [
    ("yueyue",   "悦悦 Yueyue — 5岁女孩，好奇温柔（默认）"),
    ("xiaoming", "小明 Xiaoming — 6岁男孩，爱冒险有活力"),
    ("meimei",   "美美 Meimei — 4岁女孩，有创意爱想象"),
    ("lele",     "乐乐 Lele — 3岁男孩，开朗天真"),
]
CHARACTER_KEYS = [c[0] for c in CHARACTER_OPTIONS]
DEFAULT_CHARACTER = "yueyue"

EMOTION_OPTIONS = [
    ("", "（自动选择）"),
]
for ek, ev in SOUL_ELEMENTS.get("emotions", {}).items():
    EMOTION_OPTIONS.append((ek, ev.get("cn", ek)))

THEME_OPTIONS = [
    ("", "（自动选择）"),
]
for tk, tv in SOUL_ELEMENTS.get("themes", {}).items():
    THEME_OPTIONS.append((tk, tv.get("cn", tk)))

NARRATIVE_OPTIONS = [
    ("", "（自动选择）"),
]
for nk, nv in SOUL_ELEMENTS.get("narratives", {}).items():
    NARRATIVE_OPTIONS.append((nk, nv.get("cn", nk)))

PACING_OPTIONS = [
    ("", "（自动选择）"),
]
for pk in SOUL_ELEMENTS.get("pacing", []):
    PACING_OPTIONS.append((pk, pk))

COLOR_MOOD_OPTIONS = [
    ("", "（自动选择）"),
]
for ck, cv in SOUL_ELEMENTS.get("colors", {}).items():
    COLOR_MOOD_OPTIONS.append((ck, cv.get("cn", ck)))

CCLP_OPTIONS = [
    ("strict",   "🔒 严格 Strict — 仅表情姿势可变"),
    ("moderate", "🔓 适中 Moderate — 服装可随场景调整"),
    ("flexible", "🔑 灵活 Flexible — 允许时间/主题变化"),
]

SUPPORTING_CHAR_OPTS = [
    ("grandma", "👵 奶奶 Grandma"),
    ("grandpa", "👴 爷爷 Grandpa"),
    ("mom",     "👩 妈妈 Mom"),
    ("dad",     "👨 爸爸 Dad"),
    ("sibling", "🧒 兄弟姐妹 Sibling"),
]

ANIMAL_OPTS = [
    ("dog",      "🐕 小狗 Dog"),
    ("cat",      "🐈 小猫 Cat"),
    ("rabbit",  "🐇 小兔 Rabbit"),
    ("chick",   "🐤 小鸡 Chick"),
    ("duckling","🐥 小鸭 Duckling"),
    ("bird",    "🐦 小鸟 Bird"),
    ("butterfly","🦋 蝴蝶 Butterfly"),
    ("frog",    "🐸 青蛙 Frog"),
    ("lamb",    "🐑 羊羔 Lamb"),
]

OUTPUT_FORMAT_OPTS = [
    ("markdown", "📝 Markdown", True),   # 始终勾选
    ("pdf",      "📄 PDF",      False),
    ("pptx",     "📊 PPTX",     False),
]


# ═══════════════════════════════════════════════════════
#  文本 API 系统提示（绘本生成）
# ═══════════════════════════════════════════════════════

SYSTEM_PROMPT_TEXT = """你是一位专业的儿童绘本作家和教育专家，精通中英双语创作。你需要为儿童生成一本完整的双语绘本。

## 核心要求

1. **内容安全第一**：绝对禁止暴力、恐怖、成人、政治、宗教、商业品牌内容
2. **年龄适配**：根据目标年龄调整句子长度、词汇难度、认知复杂度
3. **科学准确性**：描述的自然现象必须符合科学事实（如：树皮纹理可见✅，活树年轮不可见❌）
4. **文化真实性**：中式元素要准确得体
5. **故事温暖有趣**：适合儿童，传递正面价值观

## 输出格式

你必须返回一个合法的 JSON 对象，格式如下：

```json
{
  "title_cn": "中文标题",
  "title_en": "English Title",
  "pages": [
    {
      "page_num": 1,
      "story_cn": "中文故事文本（一句话）",
      "story_en": "English story text (one sentence)",
      "pinyin": "完整拼音标注（带声调）",
      "learning_char": "学习汉字（一个）",
      "learning_pinyin": "汉字拼音",
      "learning_meaning": "汉字英文含义",
      "learning_extra": "额外学习目标（可选，格式：类别：内容 或留空字符串）",
      "image_prompt": "详细英文图片生成提示词（150-250词）"
    }
  ],
  "story_summary_cn": "故事总结中文",
  "story_summary_en": "Story summary English",
  "extension_activities": [
    "延伸活动建议1",
    "延伸活动建议2",
    "延伸活动建议3"
  ]
}
```

## 设计上下文（由用户提供）

{design_context}

## 重要约束

- 中文句子和英文句子必须对应，但不能是逐字翻译
- 拼音必须准确包含声调（ā á ǎ à ō ó ǒ ò ē é ě è ī í ǐ ì ū ú ǔ ù ǖ ǘ ǚ ǜ）
- learning_char 必须是 SINGLE Chinese character
- image_prompt 必须包含：角色外观描述 + 场景环境 + 风格关键词 + 无文字无水印
- 如果内容涉及自然科学（年龄≥7），必须确保描述的事实准确
- 角色外观在所有页面中必须保持一致（参考设计上下文中的角色锚点）
"""


from plugins._utils import extract_json as _extract_json
from plugins._text_api import call_text_api as _call_text_api, call_text_api_with_retry as _call_text_api_with_retry


def _parse_story_response(raw: dict) -> dict:
    """解析 API 返回的绘本 JSON，标准化字段"""
    pages = raw.get("pages", [])
    parsed_pages = []
    for i, p in enumerate(pages):
        parsed_pages.append({
            "page_num": p.get("page_num", i + 1),
            "story_cn": p.get("story_cn", ""),
            "story_en": p.get("story_en", ""),
            "pinyin": p.get("pinyin", ""),
            "learning_char": p.get("learning_char", ""),
            "learning_pinyin": p.get("learning_pinyin", ""),
            "learning_meaning": p.get("learning_meaning", ""),
            "learning_extra": p.get("learning_extra", ""),
            "image_prompt": p.get("image_prompt", ""),
        })
    return {
        "title_cn": raw.get("title_cn", "未命名绘本"),
        "title_en": raw.get("title_en", "Untitled Picture Book"),
        "pages": parsed_pages,
        "story_summary_cn": raw.get("story_summary_cn", ""),
        "story_summary_en": raw.get("story_summary_en", ""),
        "extension_activities": raw.get("extension_activities", []),
    }


# ═══════════════════════════════════════════════════════
#  导出辅助函数
# ═══════════════════════════════════════════════════════

def _format_markdown_page(page: dict, image_map: dict = None) -> str:
    """格式化单页 markdown 内容"""
    parts = [
        f"## 第{page['page_num']}页 / Page {page['page_num']}\n",
        f"📖 **故事 / Story:**",
        f"{page['story_cn']}",
        f"{page['story_en']}\n",
        f"---\n",
        f"🔤 **拼音 / Pinyin:**",
        f"{page['pinyin']}\n",
        f"---\n",
        f"✨ **学习要点 / Learning Point:**",
        f"{page['learning_char']} ({page['learning_pinyin']}) - {page['learning_meaning']}",
    ]
    if page.get("learning_extra"):
        parts.append(f"\n{page['learning_extra']}")
    parts.append("\n---\n")

    # 图片 prompt
    if page.get("image_prompt"):
        parts.append(f"🎨 **图片提示词 / Image Prompt:**")
        parts.append(f"```\n{page['image_prompt']}\n```\n")

    # 生成的图片
    if image_map and page["page_num"] in image_map:
        img_path = image_map[page["page_num"]]
        parts.append(f"![Page {page['page_num']}]({img_path})\n")

    parts.append("---\n")
    return "\n".join(parts)


def _export_markdown(content: dict, output_dir: str, timestamp: str,
                     style_key: str, scene_key: str, character_key: str,
                     pages: int, image_map: dict = None) -> str:
    """导出 Markdown 文件，返回文件路径"""
    os.makedirs(output_dir, exist_ok=True)
    month_dir = os.path.join(output_dir, timestamp[:4] + "-" + timestamp[4:6])
    os.makedirs(month_dir, exist_ok=True)

    pages_str = f"-{pages}pages" if pages > 1 else ""
    filename = f"{style_key}-{scene_key}-{character_key}{pages_str}-{timestamp}.md"
    filepath = os.path.join(month_dir, filename)

    style_cn = STYLES.get(style_key, {}).get("name_cn", style_key)
    scene_cn = SCENES.get(scene_key, {}).get("name_cn", scene_key)
    char_cn = CHARACTERS.get(character_key, {}).get("name_cn", character_key)

    md_parts = [
        f"# {content['title_cn']} / {content['title_en']}\n",
        f"**生成时间 / Generated**: {timestamp}",
        f"**风格 / Style**: {style_cn} ({style_key})",
        f"**场景 / Scene**: {scene_cn} ({scene_key})",
        f"**角色 / Character**: {char_cn} ({character_key})",
        f"**页数 / Pages**: {pages}\n",
        "---\n",
    ]

    for page in content["pages"]:
        md_parts.append(_format_markdown_page(page, image_map))

    # 多页故事追加总结
    if pages > 1 and content.get("story_summary_cn"):
        md_parts.append("## 📚 故事总结 / Story Summary\n")
        md_parts.append(f"### 完整故事 / Complete Story")
        md_parts.append(f"{content['story_summary_cn']}")
        md_parts.append(f"{content['story_summary_en']}\n")

        md_parts.append("### 学习成果 / Learning Outcomes")
        md_parts.append("**学习的汉字 (Characters Learned)**:")
        for p in content["pages"]:
            md_parts.append(
                f"- Page {p['page_num']}: {p['learning_char']} "
                f"({p['learning_pinyin']}) - {p['learning_meaning']}")
        md_parts.append("")

        if content.get("extension_activities"):
            md_parts.append("### 延伸活动建议 / Extension Activities")
            for i, act in enumerate(content["extension_activities"], 1):
                md_parts.append(f"{i}. {act}")
            md_parts.append("")

    md_parts.append("---\n")
    md_parts.append("## 生成信息 / Generation Info\n")
    md_parts.append(f"- **Generator**: 绘本魔法师 Picture Book Wizard (Noova Plugin)")
    md_parts.append(f"- **Timestamp**: {timestamp}")
    md_parts.append(f"- **Config**: {style_key}/{scene_key}/{character_key}/{pages}pages\n")

    md_content = "\n".join(md_parts)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(md_content)
    return filepath


def _markdown_to_html(md_text: str) -> str:
    """将 Markdown 文本转换为带样式的 HTML"""
    html = md_text

    # 转义 HTML（占位符 @@...@@ 不含特殊字符，不受影响）
    html = html.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # 恢复已有的 HTML 标签
    html = html.replace("&lt;br&gt;", "<br>")
    html = html.replace("&lt;/h", "</h").replace("&lt;h", "<h")
    html = html.replace("&lt;p&gt;", "<p>").replace("&lt;/p&gt;", "</p>")
    html = html.replace("&lt;b&gt;", "<b>").replace("&lt;/b&gt;", "</b>")
    html = html.replace("&lt;i&gt;", "<i>").replace("&lt;/i&gt;", "</i>")
    html = html.replace("&lt;pre&gt;", "<pre>").replace("&lt;/pre&gt;", "</pre>")
    html = html.replace("&lt;code&gt;", "<code>").replace("&lt;/code&gt;", "</code>")
    html = html.replace("&lt;li&gt;", "<li>").replace("&lt;/li&gt;", "</li>")
    html = html.replace("&lt;ul&gt;", "<ul>").replace("&lt;/ul&gt;", "</ul>")
    html = html.replace("&lt;ol&gt;", "<ol>").replace("&lt;/ol&gt;", "</ol>")

    # Markdown 标题
    html = re.sub(r'^#### (.+)$', r'<h4>\1</h4>', html, flags=re.MULTILINE)
    html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
    html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
    html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)

    # 粗体
    html = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', html)
    # 水平线
    html = re.sub(r'^---$', r'<hr>', html, flags=re.MULTILINE)
    # 代码块
    html = re.sub(r'```(.*?)```', r'<pre><code>\1</code></pre>', html, flags=re.DOTALL)

    # 段落：连续空行分隔的文本
    paragraphs = []
    for block in re.split(r'\n\s*\n', html):
        block = block.strip()
        if not block:
            continue
        if re.match(r'^<(h[1-4]|hr|ul|ol|li|pre|img)', block):
            paragraphs.append(block)
        else:
            paragraphs.append(f"<p>{block.replace(chr(10), '<br>')}</p>")

    html_body = "\n".join(paragraphs)

    css = """
    <style>
        body { font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif;
               font-size: 14px; line-height: 1.8; color: #333;
               max-width: 800px; margin: 40px auto; padding: 20px;
               background: #FFFEF9; }
        h1 { color: #F59E0B; font-size: 24px; border-bottom: 2px solid #FDE68A;
             padding-bottom: 10px; }
        h2 { color: #D97706; font-size: 20px; margin-top: 30px; }
        h3 { color: #92400E; font-size: 16px; }
        hr { border: none; border-top: 1px dashed #FDE68A; margin: 20px 0; }
        pre { background: #FFFBEB; border: 1px solid #FDE68A; border-radius: 8px;
              padding: 16px; overflow-x: auto; font-size: 12px; }
        img { max-width: 100%; border-radius: 12px; margin: 10px 0;
              box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
        p { margin: 8px 0; }
    </style>
    """

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>绘本</title>{css}</head>
<body>{html_body}</body>
</html>"""


def _export_pdf(md_content: str, output_path: str, image_map: dict = None):
    """通过 QTextDocument + QPrinter 导出 PDF"""
    # 用安全占位符标记图片位置（避免 HTML 实体转义破坏标签）
    img_placeholders = {}  # placeholder -> abs_path
    if image_map:
        for page_num, img_path in sorted(image_map.items()):
            if os.path.exists(img_path):
                abs_path = os.path.abspath(img_path).replace('\\', '/')
                placeholder = f"@@IMG_{page_num}@@"
                img_placeholders[placeholder] = abs_path
                # 只在标题行 "## Page N" 后插入占位符，避免破坏 ![Page N](...) 语法
                md_content = re.sub(
                    rf'^(##\s+Page\s+{page_num}\b.*)$',
                    rf'\1\n{placeholder}',
                    md_content, flags=re.MULTILINE)

    html = _markdown_to_html(md_content)

    # 注入图片标签到最终 HTML（此时已转义完毕，直接替换占位符）
    for placeholder, abs_path in img_placeholders.items():
        img_tag = (
            f'<br><img src="file:///{abs_path}" '
            f'style="max-width:100%;border-radius:12px;margin:10px 0;'
            f'box-shadow:0 4px 12px rgba(0,0,0,0.1);"><br>'
        )
        html = html.replace(placeholder, img_tag)

    doc = QTextDocument()
    doc.setHtml(html)
    doc.setDefaultFont(QFont("Microsoft YaHei", 11))

    printer = QPrinter(QPrinter.HighResolution)
    printer.setOutputFormat(QPrinter.PdfFormat)
    printer.setOutputFileName(output_path)
    page_size = QPageSize(QPageSize.A4)
    printer.setPageSize(page_size)
    margins = QMarginsF(20, 20, 20, 20)
    layout = QPageLayout(page_size, QPageLayout.Portrait, margins, QPageLayout.Millimeter)
    printer.setPageLayout(layout)

    doc.print_(printer)


def _export_pptx(content: dict, output_path: str, style_key: str,
                 scene_key: str, color_mood: str, image_map: dict = None):
    """通过 python-pptx 导出 PPTX"""
    try:
        from pptx import Presentation
        from pptx.util import Inches, Pt, Emu
        from pptx.dml.color import RGBColor
        from pptx.enum.text import PP_ALIGN
    except ImportError:
        raise RuntimeError("缺少 python-pptx 库，请执行: pip install python-pptx")

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    # 色彩情绪映射
    mood_colors = {
        "warm-bright": "FFF5EB",
        "fresh": "F0FFF0",
        "dreamy": "FFF0F5",
        "vibrant": "FFF8E1",
        "serene": "F0F8FF",
    }
    bg_hex = mood_colors.get(color_mood, "FFFEF9")

    # --- 封面页 ---
    slide_layout = prs.slide_layouts[6]  # blank
    slide = prs.slides.add_slide(slide_layout)
    bg = slide.background
    fill = bg.fill
    fill.solid()
    fill.fore_color.rgb = RGBColor(
        int(bg_hex[0:2], 16), int(bg_hex[2:4], 16), int(bg_hex[4:6], 16))

    # 标题
    title_box = slide.shapes.add_textbox(Inches(2), Inches(2), Inches(9.3), Inches(1.5))
    tf = title_box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = content.get("title_cn", "")
    p.font.size = Pt(48)
    p.font.bold = True
    p.font.color.rgb = RGBColor(0xD9, 0x77, 0x06)
    p.alignment = PP_ALIGN.CENTER

    # 英文副标题
    sub_box = slide.shapes.add_textbox(Inches(2), Inches(3.5), Inches(9.3), Inches(1))
    tf2 = sub_box.text_frame
    p2 = tf2.paragraphs[0]
    p2.text = content.get("title_en", "")
    p2.font.size = Pt(24)
    p2.font.color.rgb = RGBColor(0x92, 0x4E, 0x0E)
    p2.alignment = PP_ALIGN.CENTER

    # --- 内容页 ---
    for page in content.get("pages", []):
        slide = prs.slides.add_slide(slide_layout)
        bg = slide.background
        fill = bg.fill
        fill.solid()
        fill.fore_color.rgb = RGBColor(
            int(bg_hex[0:2], 16), int(bg_hex[2:4], 16), int(bg_hex[4:6], 16))

        y = Inches(0.5)

        # 页码
        num_box = slide.shapes.add_textbox(Inches(0.5), y, Inches(12), Inches(0.4))
        ntf = num_box.text_frame
        np = ntf.paragraphs[0]
        np.text = f"第 {page['page_num']} 页 / Page {page['page_num']}"
        np.font.size = Pt(14)
        np.font.color.rgb = RGBColor(0x9C, 0xA3, 0xAF)
        np.alignment = PP_ALIGN.RIGHT

        y += Inches(0.6)

        # 中文故事
        cn_box = slide.shapes.add_textbox(Inches(0.8), y, Inches(7), Inches(1.5))
        ctf = cn_box.text_frame
        ctf.word_wrap = True
        cp = ctf.paragraphs[0]
        cp.text = page.get("story_cn", "")
        cp.font.size = Pt(28)
        cp.font.color.rgb = RGBColor(0x1E, 0x1E, 0x2E)

        # 英文故事
        en_p = ctf.add_paragraph()
        en_p.text = page.get("story_en", "")
        en_p.font.size = Pt(16)
        en_p.font.color.rgb = RGBColor(0x6B, 0x72, 0x80)

        # 拼音
        py_p = ctf.add_paragraph()
        py_p.text = page.get("pinyin", "")
        py_p.font.size = Pt(14)
        py_p.font.color.rgb = RGBColor(0x9C, 0xA3, 0xAF)

        y += Inches(2.2)

        # 学习点
        ln_box = slide.shapes.add_textbox(Inches(0.8), y, Inches(7), Inches(0.6))
        ltf = ln_box.text_frame
        lp = ltf.paragraphs[0]
        lp.text = (f"✨ {page.get('learning_char', '')} "
                   f"({page.get('learning_pinyin', '')}) — "
                   f"{page.get('learning_meaning', '')}")
        lp.font.size = Pt(18)
        lp.font.color.rgb = RGBColor(0xD9, 0x77, 0x06)

        # 图片（如果有）
        if image_map and page["page_num"] in image_map:
            img_path = image_map[page["page_num"]]
            if os.path.exists(img_path):
                try:
                    slide.shapes.add_picture(
                        img_path, Inches(8.5), Inches(0.8),
                        Inches(4.3), Inches(5.5))
                except Exception as e:
                    print(f"[WARN] PPTX 插图失败 page={page['page_num']}: {e}")

    prs.save(output_path)


# ═══════════════════════════════════════════════════════
#  PictureBookWorker — 后台绘本生成线程
# ═══════════════════════════════════════════════════════

class PictureBookWorker(QThread):
    log_msg = Signal(str)
    progress = Signal(int, int, str)       # current, total, phase_name
    finished = Signal(bool, str)           # success, summary
    page_generated = Signal(int, str, str) # page_num, title, status

    def __init__(self,
                 text_api_key: str, text_base_url: str, text_model: str,
                 image_api_key: str, image_base_url: str, image_model: str,
                 style_key: str, scene_key: str, age: int, pages: int,
                 character_key: str, emotion: str, theme: str,
                 cclp_mode: str, narrative: str, pacing: str, color_mood: str,
                 supporting_chars: list, animal_companions: list,
                 custom_topic: str, story_title: str,
                 output_dir: str, output_formats: list,
                 generate_images: bool,
                 aspect_ratio: str, image_size: str,
                 poll_interval: int = 20, concurrency: int = 1):
        super().__init__()
        self._text_api_key = text_api_key
        self._text_base_url = text_base_url
        self._text_model = text_model
        self._image_api_key = image_api_key
        self._image_base_url = image_base_url
        self._image_model = image_model
        self._style_key = style_key
        self._scene_key = scene_key
        self._age = age
        self._pages = pages
        self._character_key = character_key
        self._emotion = emotion
        self._theme = theme
        self._cclp_mode = cclp_mode
        self._narrative = narrative
        self._pacing = pacing
        self._color_mood = color_mood
        self._supporting_chars = supporting_chars
        self._animal_companions = animal_companions
        self._custom_topic = custom_topic
        self._story_title = story_title
        self._output_dir = output_dir
        self._output_formats = output_formats
        self._generate_images = generate_images
        self._aspect_ratio = aspect_ratio
        self._image_size = image_size
        self._poll_interval = poll_interval
        self._concurrency = concurrency
        self._is_running = True
        self._engine = create_engine()

    def _log(self, text: str):
        self.log_msg.emit(text)

    def stop(self):
        self._is_running = False

    def run(self):
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        content = None
        image_map = {}
        output_files = []

        try:
            # ──── Phase 1: 验证 + 自动配置 ────
            self.progress.emit(0, 100, "验证参数")
            self._log("=" * 50)
            self._log("Phase 1: 验证参数 + 自动配置")

            # 自动填充
            if not self._character_key:
                self._character_key = AgeSystem.get_default_character(self._age)
                self._log(f"  自动选择角色: {self._character_key}")

            if self._pages <= 0:
                self._pages = AgeSystem.calculate_pages(self._age)
                self._log(f"  自动计算页数: {self._pages}")

            if not self._cclp_mode:
                self._cclp_mode = "strict" if self._pages <= 5 else "moderate"
                self._log(f"  自动选择 CCLP: {self._cclp_mode}")

            # 构建 StoryParams 并验证
            params = StoryParams(
                style=self._style_key,
                scene=self._scene_key,
                age=self._age,
                pages=self._pages,
                character=self._character_key,
                emotion=self._emotion or None,
                theme=self._theme or None,
            )
            validation = self._engine.validate(params)
            if not validation.valid:
                self._log(f"  [ERROR] 参数验证失败: {validation.errors}")
                self.finished.emit(False, f"参数验证失败: {'; '.join(validation.errors)}")
                return
            if validation.warnings:
                for w in validation.warnings:
                    self._log(f"  [WARN] {w}")

            self._log(f"  风格={self._style_key} 场景={self._scene_key} "
                       f"年龄={self._age} 页数={self._pages} 角色={self._character_key}")

            if not self._is_running:
                return

            # ──── Phase 2: 生成故事（文本 API） ────
            self.progress.emit(10, 100, "生成故事")
            self._log("")
            self._log("Phase 2: 调用文本 API 生成绘本故事...")

            design_context = self._build_design_context()
            system_prompt = SYSTEM_PROMPT_TEXT.replace(
                "{design_context}", design_context)

            title_inst = (f'绘本标题为：{self._story_title}'
                          if self._story_title.strip()
                          else '请根据故事内容自动生成一个吸引人的中英文标题')
            if self._custom_topic:
                user_prompt = (f"请生成一本关于「{self._custom_topic}」的"
                               f"儿童绘本。{title_inst}。")
            else:
                user_prompt = f"请生成一本儿童绘本。{title_inst}。"
            self._log(f"  发送请求 → {self._text_model} ({len(system_prompt)} chars system)")

            raw_response = _call_text_api_with_retry(
                self._text_api_key, self._text_base_url, self._text_model,
                system_prompt, user_prompt,
                temperature=0.8, max_tokens=DS_MAX_TOKENS,
                json_mode=True, log_fn=self._log)

            if not self._is_running:
                return

            self._log("  解析 API 响应...")
            content = _parse_story_response(_extract_json(raw_response))
            content["pages"] = content["pages"][:self._pages]  # 截断到目标页数
            actual_pages = len(content["pages"])
            self._log(f"  故事生成完成: {actual_pages} 页, "
                       f"标题: {content['title_cn']}")

            if actual_pages == 0:
                self.finished.emit(False, "API 未返回任何页面内容")
                return

            # ──── Phase 3: 组装图片 prompt ────
            self.progress.emit(40, 100, "组装图片提示词")
            self._log("")
            self._log("Phase 3: 组装图片生成提示词...")

            for page in content["pages"]:
                is_first = page["page_num"] == 1
                anchor = self._engine.generate_anchor(
                    self._character_key, page["page_num"])
                assembled = PromptAssembler.assemble(
                    style=self._style_key,
                    scene=self._scene_key,
                    character_anchor=anchor,
                    action=page.get("story_en", ""),
                    expression=page.get("story_en", ""),
                    is_first_page=is_first,
                )
                page["image_prompt"] = assembled
                self._log(f"  Page {page['page_num']}: prompt "
                           f"({PromptAssembler.get_word_count(assembled)} words)")

            if not self._is_running:
                return

            # ──── Phase 4: 生成配图（可选） ────
            if self._generate_images and self._image_api_key:
                self.progress.emit(50, 100, "生成配图")
                self._log("")
                self._log("Phase 4: 调用出图 API 生成绘本配图...")

                images_dir = os.path.join(self._output_dir, "images")
                os.makedirs(images_dir, exist_ok=True)

                api = NoovaAPI(self._image_api_key)
                # 临时覆盖 base_url
                if self._image_base_url and self._image_base_url != "https://noova.cn":
                    api.BASE_URL = self._image_base_url.rstrip("/")

                for i, page in enumerate(content["pages"]):
                    if not self._is_running:
                        break
                    pn = page["page_num"]
                    progress_pct = 50 + int(40 * (i + 1) / len(content["pages"]))
                    self.progress.emit(progress_pct, 100, f"生成第{pn}页配图")
                    self.page_generated.emit(pn, page.get("story_cn", ""), "generating")
                    self._log(f"  第{pn}页: 提交出图任务...")

                    try:
                        task_id, _ = api.create_draw_task(
                            self._image_model, page["image_prompt"],
                            self._aspect_ratio, self._image_size, urls=[])
                        self._log(f"    task_id={task_id}, 等待结果...")

                        result = api.poll_task_result(
                            task_id, self._poll_interval,
                            self._log,
                            cancel_check=lambda: not self._is_running)

                        if not self._is_running:
                            break

                        status = str(
                            (result.get("data") or {}).get("status") or "")
                        if status == "succeeded":
                            results = (result.get("data") or {}).get("results", [])
                            if results:
                                img_url = results[0].get("url")
                                save_path = os.path.join(
                                    images_dir, f"page_{pn:02d}.png")
                                api.download_image(img_url, save_path)
                                image_map[pn] = save_path
                                self.page_generated.emit(
                                    pn, page.get("story_cn", ""), "done")
                                self._log(f"    [OK] 图片已保存: {save_path}")
                            else:
                                self.page_generated.emit(
                                    pn, page.get("story_cn", ""), "no-result")
                                self._log(f"    [WARN] 任务成功但无图片返回")
                        else:
                            self.page_generated.emit(
                                pn, page.get("story_cn", ""), f"failed:{status}")
                            self._log(f"    [WARN] 任务状态: {status}")
                    except Exception as e:
                        self.page_generated.emit(
                            pn, page.get("story_cn", ""), f"error:{e}")
                        self._log(f"    [ERROR] 第{pn}页出图失败: {e}")

                self._log(f"  配图完成: {len(image_map)}/{len(content['pages'])} 页")

            if not self._is_running:
                return

            # ──── Phase 5: 导出 ────
            self.progress.emit(95, 100, "导出文件")
            self._log("")
            self._log("Phase 5: 导出输出文件...")

            # Markdown（始终生成）
            md_path = _export_markdown(
                content, self._output_dir, timestamp,
                self._style_key, self._scene_key, self._character_key,
                actual_pages, image_map)
            output_files.append(f"Markdown: {md_path}")
            self._log(f"  [OK] Markdown → {md_path}")

            stem = os.path.splitext(md_path)[0]

            # PDF
            if "pdf" in self._output_formats:
                try:
                    pdf_path = stem + ".pdf"
                    with open(md_path, "r", encoding="utf-8") as f:
                        md_text = f.read()
                    _export_pdf(md_text, pdf_path, image_map)
                    output_files.append(f"PDF: {pdf_path}")
                    self._log(f"  [OK] PDF → {pdf_path}")
                except Exception as e:
                    self._log(f"  [WARN] PDF 导出失败: {e}")

            # PPTX
            if "pptx" in self._output_formats:
                try:
                    pptx_path = stem + ".pptx"
                    _export_pptx(content, pptx_path, self._style_key,
                                 self._scene_key, self._color_mood, image_map)
                    output_files.append(f"PPTX: {pptx_path}")
                    self._log(f"  [OK] PPTX → {pptx_path}")
                except Exception as e:
                    self._log(f"  [WARN] PPTX 导出失败: {e}")

            self.progress.emit(100, 100, "完成")
            self._log("")
            self._log("=" * 50)
            self._log("绘本生成完成！")

            summary_parts = [
                f"📖 {content['title_cn']} / {content['title_en']}",
                f"📄 {actual_pages} 页 | 🎨 {self._style_key} | "
                f"🌿 {self._scene_key} | 👤 {self._character_key}",
            ]
            if image_map:
                summary_parts.append(f"🖼️ {len(image_map)} 张配图")
            summary_parts.append("\n输出文件:")
            summary_parts.extend(f"  • {f}" for f in output_files)

            self.finished.emit(True, "\n".join(summary_parts))

        except Exception as e:
            self._log("")
            self._log(f"[FATAL] 生成失败: {e}")
            tb = traceback.format_exc()
            # 隐藏 API key
            tb = re.sub(r'sk-[a-zA-Z0-9]{10,}', 'sk-***REDACTED***', tb)
            self._log(tb)
            self.finished.emit(False, str(e))

    def _build_design_context(self) -> str:
        """构建设计上下文文本，注入到 system prompt"""
        style = STYLES.get(self._style_key, {})
        scene = SCENES.get(self._scene_key, {})
        char = CHARACTERS.get(self._character_key, {})
        age_config = AgeSystem.get_age_config(self._age)

        parts = [
            "=== 绘本设计上下文 ===\n",
            "## 视觉风格",
            f"- 风格代码: {self._style_key}",
            f"- 中文名: {style.get('name_cn', '')}",
            f"- 关键词: {style.get('keywords', '')}",
            f"- 最适合: {', '.join(style.get('best_for', []))}",
            "",
            "## 场景",
            f"- 场景代码: {self._scene_key}",
            f"- 中文名: {scene.get('name_cn', '')}",
            f"- 场景元素: {scene.get('elements', '')}",
            f"- 氛围: {scene.get('mood', '')}",
            f"- 可观察内容: {', '.join(scene.get('observable', []))}",
            f"- 不可观察内容（避免描述）: {', '.join(scene.get('not_observable', []))}",
            "",
            "## 角色锚点（CCLP 4.0）",
            f"- 角色代码: {self._character_key}",
            f"- 中文名: {char.get('name_cn', '')}",
            f"- 年龄: {char.get('age', self._age)} 岁",
            f"- 性格: {', '.join(char.get('personality', []))}",
            f"- 完整描述: {char.get('anchor', '')}",
            f"- 标志特征: {json.dumps(char.get('signature', {}), ensure_ascii=False)}",
            f"- 体态: {char.get('build', '')}",
            f"- CCLP 模式: {self._cclp_mode}",
        ]

        cclp_config = CCLP_CONFIG.get("levels", {}).get(self._cclp_mode, {})
        if cclp_config:
            parts.append(f"- CCLP 说明: {cclp_config.get('description', '')}")
        parts.append(f"- CCLP 标记: {CCLP_CONFIG.get('markers', {}).get('lock', '')}")

        parts.extend(["", "## 年龄配置"])
        parts.append(f"- 年龄段: {age_config.get('label', '')} ({age_config.get('label_en', '')})")
        cn_lim, en_lim = AgeSystem.get_sentence_limits(self._age)
        parts.append(f"- 中文句长: {cn_lim[0]}-{cn_lim[1]} 字")
        parts.append(f"- 英文句长: {en_lim[0]}-{en_lim[1]} 词")
        parts.append(f"- 复杂度: {age_config.get('complexity', '')}")
        parts.append(f"- 学习领域: {', '.join(age_config.get('learning', []))}")
        parts.append(f"- 情感表达: {', '.join(age_config.get('emotions', []))}")
        parts.append(f"- HSK 等级: {age_config.get('hsk_level', '')}")

        parts.extend(["", "## 故事结构"])
        story_struct = STORY_STRUCTURES.get(
            self._pages, STORY_STRUCTURES.get(5, {}))
        parts.append(f"- 页数: {self._pages}")
        parts.append(f"- 结构: {story_struct.get('name', '')} ({story_struct.get('name_cn', '')})")
        for i, page_desc in enumerate(story_struct.get("pages", []), 1):
            if i <= self._pages:
                parts.append(f"  Page {i}: {page_desc}")

        # 灵魂元素
        if self._emotion or self._theme or self._narrative or self._pacing or self._color_mood:
            parts.extend(["", "## 灵魂元素"])
            if self._emotion:
                em = SOUL_ELEMENTS["emotions"].get(self._emotion, {})
                parts.append(f"- 情绪: {em.get('cn', self._emotion)} → 色彩: {em.get('colors', [])}")
            if self._theme:
                th = SOUL_ELEMENTS["themes"].get(self._theme, {})
                parts.append(f"- 主题: {th.get('cn', self._theme)} → 叙事类型: {th.get('narratives', [])}")
            if self._narrative:
                na = SOUL_ELEMENTS["narratives"].get(self._narrative, {})
                parts.append(f"- 叙事: {na.get('cn', self._narrative)} (最少{na.get('pages_min','?')}页)")
            if self._pacing:
                parts.append(f"- 节奏: {self._pacing}")
            if self._color_mood:
                cm = SOUL_ELEMENTS["colors"].get(self._color_mood, {})
                parts.append(f"- 色彩情绪: {cm.get('cn', self._color_mood)} → 参考色: {cm.get('hex', '')}")

        # 配角
        if self._supporting_chars:
            parts.extend(["", "## 配角角色"])
            for sc in self._supporting_chars:
                sdata = SUPPORTING_CHARACTERS.get(sc, {})
                parts.append(f"- {sdata.get('name_cn', sc)}: {sdata.get('anchor', '')}")
                parts.append(f"  标志特征: {json.dumps(sdata.get('signature', {}), ensure_ascii=False)}")

        # 动物伙伴
        if self._animal_companions:
            parts.extend(["", "## 动物伙伴"])
            for ac in self._animal_companions:
                adata = ANIMAL_COMPANIONS.get(ac, {})
                parts.append(f"- {adata.get('name_cn', ac)}: {adata.get('anchor', '')}")

        # 水印防护
        parts.extend(["", "## 图片规范"])
        parts.append(f"- 水印防护: {WM_LEVELS.get(DEFAULT_WM, '')}")
        parts.append("- 禁止：文字叠加、水印、签名、logo、品牌元素、版权符号、URL")

        # 内容安全
        parts.extend(["", "## 内容安全约束"])
        parts.append("- 禁止：暴力、恐怖、成人内容、政治宣传、宗教教义、商业品牌")
        parts.append("- 确保：科学准确性（场景可观察元素）、年龄适配、正面价值观")

        return "\n".join(parts)


# ═══════════════════════════════════════════════════════
#  PictureBookPlugin — 插件主类
# ═══════════════════════════════════════════════════════

class PictureBookPlugin(BasePlugin):
    plugin_id = "picture_book"
    name = "绘本魔法师"
    icon = "📖"
    color = "#F59E0B"
    description = ("AI 驱动的儿童中英双语绘本生成工具\n"
                   "选择角色、场景、风格 → 自动生成绘本、拼音标注与配图")

    def create_workspace(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet(f"background-color: {C_BG};")

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(56, 44, 56, 52)
        layout.setSpacing(20)

        # ── 返回按钮 ──
        back_btn = QPushButton("← 返回首页")
        back_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none;"
            f" color: {C_TEXT_SUB}; font-size: 14px; padding: 4px 0; }}"
            f"QPushButton:hover {{ color: {C_PRIMARY}; }}")
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.clicked.connect(lambda: self.main_window.switch_page(0))
        layout.addWidget(back_btn)

        # ── 标题区 ──
        title = QLabel(f"{self.icon} {self.name}")
        title.setStyleSheet(
            f"font-size: 28px; font-weight: 700; color: {C_TEXT}; background: transparent;")
        layout.addWidget(title)

        subtitle = QLabel("AI 驱动的儿童中英双语绘本生成工具 — 输入主题，自动生成双语绘本、拼音标注与配图")
        subtitle.setStyleSheet(
            f"font-size: 14px; color: {C_TEXT_SUB}; background: transparent;")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        # ═══════════════════  区域 1: API 配置  ═══════════════════
        layout.addWidget(self._build_api_section())

        # ═══════════════════  区域 2: 绘本设置  ═══════════════════
        layout.addWidget(self._build_story_settings())

        # ═══════════════════  区域 3: 高级选项  ═══════════════════
        self._advanced_card = self._build_advanced_section()
        self._advanced_card.setVisible(False)
        layout.addWidget(self._build_advanced_toggle())
        layout.addWidget(self._advanced_card)

        # ═══════════════════  区域 4: 输出设置  ═══════════════════
        layout.addWidget(self._build_output_section())

        # ═══════════════════  区域 5: 操作按钮  ═══════════════════
        layout.addLayout(self._build_action_row())

        # ═══════════════════  区域 6: 进度/日志  ═══════════════════
        layout.addWidget(self._build_progress_panel())

        layout.addStretch()

        scroll.setWidget(content)
        wrapper = QVBoxLayout(page)
        wrapper.setContentsMargins(0, 0, 0, 0)
        wrapper.addWidget(scroll)
        return page

    # ──── UI 子构建方法 ────

    def _make_card(self, name: str = "") -> QFrame:
        """创建标准白色卡片"""
        card = QFrame()
        card.setStyleSheet(
            f"QFrame#{name} {{ background-color: {C_CARD_BG};"
            f" border: 1px solid {C_CARD_BDR}; border-radius: {R_LG}px; }}")
        if name:
            card.setObjectName(name)
        return card

    def _card_layout(self, card: QFrame, margins=(24, 20, 24, 20), spacing=14) -> QVBoxLayout:
        """为卡片创建内边距布局"""
        layout = QVBoxLayout(card)
        layout.setContentsMargins(*margins)
        layout.setSpacing(spacing)
        return layout

    def _section_label(self, text: str) -> QLabel:
        """创建区域标题"""
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"font-size: 16px; font-weight: 700; color: {C_TEXT}; background: transparent;")
        return lbl

    def _sub_label(self, text: str) -> QLabel:
        """创建字段标签"""
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"font-size: 12px; font-weight: 600; color: {C_TEXT_SUB}; background: transparent;")
        return lbl

    def _input_style(self, w: QLineEdit):
        """应用输入框样式"""
        w.setStyleSheet(
            f"QLineEdit {{ border: 1px solid {C_INPUT_BDR}; border-radius: 10px;"
            f" padding: 9px 12px; font-size: 13px; background: {C_INPUT_BG};"
            f" color: {C_TEXT}; }}"
            f"QLineEdit:focus {{ border: 1px solid {C_PRIMARY}; background: #FFFFFF; }}")

    def _combo_style(self, w: QComboBox):
        """应用下拉框样式"""
        w.setStyleSheet(
            f"QComboBox {{ border: 1px solid {C_INPUT_BDR}; border-radius: 10px;"
            f" padding: 9px 12px; font-size: 13px; background: {C_INPUT_BG};"
            f" color: {C_TEXT}; }}"
            f"QComboBox:focus {{ border: 1px solid {C_PRIMARY}; background: #FFFFFF; }}"
            f"QComboBox::drop-down {{ subcontrol-origin: padding;"
            f" subcontrol-position: top right; width: 24px;"
            f" border-left: 1px solid {C_INPUT_BDR}; border-top-right-radius: 10px;"
            f" border-bottom-right-radius: 10px; }}"
            f"QComboBox QAbstractItemView {{ background: #FFFFFF; color: {C_TEXT};"
            f" border: 1px solid {C_INPUT_BDR}; border-radius: 6px;"
            f" selection-background-color: #FEF3C7; selection-color: {C_TEXT};"
            f" outline: none; }}")

    def _build_api_card(self, prefix: str, models: list,
                        default_model: str) -> QFrame:
        """构建单个 API 配置子卡片"""
        card = self._make_card(prefix.replace(" ", ""))
        cl = self._card_layout(card, (16, 14, 16, 14), 8)

        cl.addWidget(self._section_label(prefix))

        cl.addWidget(self._sub_label("API Key"))
        key_input = QLineEdit()
        key_input.setEchoMode(QLineEdit.Password)
        key_input.setPlaceholderText("输入 API Key...")
        self._input_style(key_input)
        cl.addWidget(key_input)

        cl.addWidget(self._sub_label("模型"))
        model_combo = QComboBox()
        model_combo.addItems(models)
        default_idx = models.index(default_model) if default_model in models else 0
        model_combo.setCurrentIndex(default_idx)
        self._combo_style(model_combo)
        cl.addWidget(model_combo)

        return card, key_input, model_combo

    def _build_api_section(self) -> QFrame:
        card = self._make_card("ApiCard")
        layout = self._card_layout(card)

        layout.addWidget(self._section_label("⚙️ API 配置"))

        row = QHBoxLayout()
        row.setSpacing(16)

        left, self._text_api_key_input, self._text_api_model_combo = \
            self._build_api_card(
                "📝 文本 API", DS_MODELS, DS_DEFAULT_MODEL)
        right, self._image_api_key_input, self._image_api_model_combo = \
            self._build_api_card(
                "🎨 出图 API",
                list(MODEL_CONFIG.keys()),
                list(MODEL_CONFIG.keys())[0] if MODEL_CONFIG else "")
        self._image_api_model_combo.currentTextChanged.connect(
            self._on_img_model_changed)
        row.addWidget(left)
        row.addWidget(right)

        layout.addLayout(row)
        return card

    def _build_story_settings(self) -> QFrame:
        card = self._make_card("StoryCard")
        layout = self._card_layout(card)

        layout.addWidget(self._section_label("📖 绘本设置"))

        # 自定义主题输入（优先于下拉选项）
        topic_row = QHBoxLayout()
        topic_row.setSpacing(8)
        self._input_custom_topic = QLineEdit()
        self._input_custom_topic.setPlaceholderText(
            "输入你想生成的故事主题（如：勇敢的小狗学会了分享），留空则使用下方下拉选项自动生成...")
        self._input_style(self._input_custom_topic)
        topic_row.addWidget(self._input_custom_topic, 1)
        layout.addLayout(topic_row)
        layout.addSpacing(6)

        grid = QGridLayout()
        grid.setSpacing(12)

        # Row 1
        grid.addWidget(self._sub_label("风格"), 0, 0)
        self._combo_style_w = QComboBox()
        self._combo_style_w.addItems([s[1] for s in STYLE_OPTIONS])
        default_si = STYLE_KEYS.index(DEFAULT_STYLE)
        self._combo_style_w.setCurrentIndex(default_si)
        self._combo_style(self._combo_style_w)
        grid.addWidget(self._combo_style_w, 1, 0)

        grid.addWidget(self._sub_label("场景"), 0, 1)
        self._combo_scene = QComboBox()
        self._combo_scene.addItems([s[1] for s in SCENE_OPTIONS])
        self._combo_style(self._combo_scene)
        grid.addWidget(self._combo_scene, 1, 1)

        grid.addWidget(self._sub_label("年龄"), 0, 2)
        self._spin_age = QSpinBox()
        self._spin_age.setRange(3, 12)
        self._spin_age.setValue(5)
        self._spin_age.setSuffix(" 岁")
        self._spin_age.valueChanged.connect(self._on_age_changed)
        self._spin_age.setStyleSheet(
            f"QSpinBox {{ border: 1px solid {C_INPUT_BDR}; border-radius: 10px;"
            f" padding: 9px 12px; font-size: 13px; background: {C_INPUT_BG};"
            f" color: {C_TEXT}; }}"
            f"QSpinBox:focus {{ border: 1px solid {C_PRIMARY}; background: #FFFFFF; }}")
        grid.addWidget(self._spin_age, 1, 2)

        grid.addWidget(self._sub_label("角色"), 0, 3)
        self._combo_char = QComboBox()
        self._combo_char.addItems([c[1] for c in CHARACTER_OPTIONS])
        self._combo_style(self._combo_char)
        grid.addWidget(self._combo_char, 1, 3)

        # Row 2
        grid.addWidget(self._sub_label("页数"), 2, 0)
        self._spin_pages = QSpinBox()
        self._spin_pages.setRange(1, 15)
        self._spin_pages.setValue(4)
        self._spin_pages.setSuffix(" 页")
        self._spin_pages.setStyleSheet(
            f"QSpinBox {{ border: 1px solid {C_INPUT_BDR}; border-radius: 10px;"
            f" padding: 9px 12px; font-size: 13px; background: {C_INPUT_BG};"
            f" color: {C_TEXT}; }}"
            f"QSpinBox:focus {{ border: 1px solid {C_PRIMARY}; background: #FFFFFF; }}")
        grid.addWidget(self._spin_pages, 3, 0)

        for col, (attr, opts) in enumerate([
            ("emo", EMOTION_OPTIONS), ("theme", THEME_OPTIONS),
            ("narr", NARRATIVE_OPTIONS)
        ], 1):
            grid.addWidget(self._sub_label(
                {"emo": "情感", "theme": "主题", "narr": "叙事"}[attr]), 2, col)
            combo = QComboBox()
            combo.addItems([o[1] for o in opts])
            if attr in ("theme", "narr"):
                combo.setEditable(True)
                combo.setInsertPolicy(QComboBox.NoInsert)
            self._combo_style(combo)
            grid.addWidget(combo, 3, col)
            setattr(self, f"_combo_{attr}", combo)

        # Row 3
        for col, (attr, opts) in enumerate([
            ("cclp", CCLP_OPTIONS), ("pacing", PACING_OPTIONS),
            ("color_mood", COLOR_MOOD_OPTIONS)
        ]):
            grid.addWidget(self._sub_label(
                {"cclp": "CCLP 模式", "pacing": "节奏",
                 "color_mood": "色彩情绪"}[attr]), 4, col)
            combo = QComboBox()
            combo.addItems([o[1] for o in opts])
            self._combo_style(combo)
            grid.addWidget(combo, 5, col)
            setattr(self, f"_combo_{attr}", combo)

        layout.addLayout(grid)
        return card

    def _build_advanced_toggle(self) -> QPushButton:
        self._adv_toggle_btn = QPushButton("⚙️ 高级选项 ▶")
        self._adv_toggle_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none;"
            f" color: {C_TEXT_SUB}; font-size: 14px; padding: 4px 0; }}"
            f"QPushButton:hover {{ color: {C_PRIMARY}; }}")
        self._adv_toggle_btn.setCursor(Qt.PointingHandCursor)
        self._adv_toggle_btn.clicked.connect(self._toggle_advanced)
        return self._adv_toggle_btn

    def _build_advanced_section(self) -> QFrame:
        card = self._make_card("AdvancedCard")
        layout = self._card_layout(card)

        layout.addWidget(self._section_label("⚙️ 高级选项"))

        # 配角
        layout.addWidget(self._sub_label("配角角色"))
        sc_row = QHBoxLayout()
        sc_row.setSpacing(12)
        self._supporting_checks = {}
        for key, label in SUPPORTING_CHAR_OPTS:
            cb = QCheckBox(label)
            cb.setStyleSheet(
                f"QCheckBox {{ font-size: 13px; color: {C_TEXT};"
                f" spacing: 6px; background: transparent; }}")
            sc_row.addWidget(cb)
            self._supporting_checks[key] = cb
        sc_row.addStretch()
        layout.addLayout(sc_row)

        # 动物伙伴
        layout.addWidget(self._sub_label("动物伙伴"))
        an_row = QHBoxLayout()
        an_row.setSpacing(12)
        self._animal_checks = {}
        for key, label in ANIMAL_OPTS:
            cb = QCheckBox(label)
            cb.setStyleSheet(
                f"QCheckBox {{ font-size: 13px; color: {C_TEXT};"
                f" spacing: 6px; background: transparent; }}")
            an_row.addWidget(cb)
            self._animal_checks[key] = cb
        an_row.addStretch()
        layout.addLayout(an_row)

        # 绘本标题
        layout.addWidget(self._sub_label("绘本标题（留空由 AI 自动生成）"))
        self._input_title = QLineEdit()
        self._input_title.setPlaceholderText("输入自定义标题，或留空...")
        self._input_style(self._input_title)
        layout.addWidget(self._input_title)

        return card

    def _build_output_section(self) -> QFrame:
        card = self._make_card("OutputCard")
        layout = self._card_layout(card)

        layout.addWidget(self._section_label("📦 输出设置"))

        # 输出目录
        out_row = QHBoxLayout()
        out_row.setSpacing(10)
        self._input_outdir = QLineEdit()
        self._input_outdir.setText(
            str(Path.home() / "NoovaOutput" / "picture-books"))
        self._input_outdir.setPlaceholderText("输出目录...")
        self._input_style(self._input_outdir)
        out_row.addWidget(self._input_outdir)

        pick_btn = QPushButton("选择目录...")
        pick_btn.setStyleSheet(
            f"QPushButton {{ background: #F3F4F6; border: 1px solid {C_INPUT_BDR};"
            f" border-radius: 10px; padding: 9px 14px; font-size: 13px;"
            f" color: {C_TEXT}; }}"
            f"QPushButton:hover {{ background: #E5E7EB; }}")
        pick_btn.clicked.connect(self._pick_output_dir)
        out_row.addWidget(pick_btn)
        layout.addLayout(out_row)

        # 输出格式
        fmt_row = QHBoxLayout()
        fmt_row.setSpacing(20)
        fmt_row.addWidget(self._sub_label("输出格式:"))
        self._format_checks = {}
        for key, label, default_on in OUTPUT_FORMAT_OPTS:
            cb = QCheckBox(label)
            cb.setChecked(default_on)
            cb.setEnabled(key != "markdown")  # Markdown 始终勾选且不可取消
            cb.setStyleSheet(
                f"QCheckBox {{ font-size: 13px; color: {C_TEXT};"
                f" spacing: 6px; background: transparent; }}"
                f"QCheckBox:disabled {{ color: {C_TEXT_MUTED}; }}")
            fmt_row.addWidget(cb)
            self._format_checks[key] = cb
        fmt_row.addStretch()
        layout.addLayout(fmt_row)

        # 图片生成
        img_row = QHBoxLayout()
        img_row.setSpacing(16)
        self._check_gen_images = QCheckBox("🖼️ 生成绘本配图（需要出图 API）")
        self._check_gen_images.setStyleSheet(
            f"QCheckBox {{ font-size: 14px; font-weight: 600; color: {C_TEXT};"
            f" spacing: 8px; background: transparent; }}")
        self._check_gen_images.toggled.connect(self._on_image_toggle)
        img_row.addWidget(self._check_gen_images)
        img_row.addStretch()
        layout.addLayout(img_row)

        # 图幅设置容器（仅配图模式显示）
        self._img_opts_container = QWidget()
        img_grid = QGridLayout(self._img_opts_container)
        img_grid.setContentsMargins(0, 6, 0, 0)
        img_grid.setSpacing(10)

        # Row 0: 比例 + 尺寸（模型跟随 API 配置区的出图 API 模型）
        img_grid.addWidget(self._sub_label("比例"), 0, 0)
        self._combo_aspect = QComboBox()
        self._combo_style(self._combo_aspect)
        img_grid.addWidget(self._combo_aspect, 1, 0)

        img_grid.addWidget(self._sub_label("画质"), 0, 1)
        self._combo_img_size = QComboBox()
        self._combo_style(self._combo_img_size)
        img_grid.addWidget(self._combo_img_size, 1, 1)

        # Row 2: 并发任务数 + 轮询间隔
        img_grid.addWidget(self._sub_label("并发任务数"), 2, 0)
        self._spin_concurrency = QSpinBox()
        self._spin_concurrency.setRange(1, 10)
        self._spin_concurrency.setValue(1)
        self._spin_concurrency.setSuffix(" 个")
        self._spin_concurrency.setStyleSheet(
            f"QSpinBox {{ border: 1px solid {C_INPUT_BDR}; border-radius: 10px;"
            f" padding: 9px 12px; font-size: 13px; background: {C_INPUT_BG};"
            f" color: {C_TEXT}; }}"
            f"QSpinBox:focus {{ border: 1px solid {C_PRIMARY}; background: #FFFFFF; }}")
        img_grid.addWidget(self._spin_concurrency, 3, 0)

        img_grid.addWidget(self._sub_label("轮询间隔"), 2, 1)
        self._spin_poll = QSpinBox()
        self._spin_poll.setRange(5, 9999)
        self._spin_poll.setValue(20)
        self._spin_poll.setSuffix(" 秒")
        self._spin_poll.setStyleSheet(
            f"QSpinBox {{ border: 1px solid {C_INPUT_BDR}; border-radius: 10px;"
            f" padding: 9px 12px; font-size: 13px; background: {C_INPUT_BG};"
            f" color: {C_TEXT}; }}"
            f"QSpinBox:focus {{ border: 1px solid {C_PRIMARY}; background: #FFFFFF; }}")
        img_grid.addWidget(self._spin_poll, 3, 1)

        layout.addWidget(self._img_opts_container)
        self._img_opts_container.setVisible(False)
        # 初始填充（根据 API 配置区选中的模型）
        self._on_img_model_changed(self._image_api_model_combo.currentText())
        return card

    def _on_img_model_changed(self, model_name: str):
        """出图模型变化时联动更新比例和尺寸选项"""
        cfg = MODEL_CONFIG.get(model_name, {})
        ratios = cfg.get("ratios", ["1:1"])
        sizes = cfg.get("sizes", ["1024x1024"])
        self._combo_aspect.clear()
        self._combo_aspect.addItems(ratios)
        self._combo_img_size.clear()
        self._combo_img_size.addItems(sizes)

    def _build_action_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(14)

        self._btn_start = QPushButton("🚀 开始生成")
        self._btn_start.setStyleSheet(
            f"QPushButton {{ background: {C_PRIMARY}; color: #FFFFFF;"
            f" border: none; border-radius: 12px; padding: 12px 36px;"
            f" font-size: 15px; font-weight: 700; }}"
            f"QPushButton:hover {{ background: {C_PRIMARY_HV}; }}"
            f"QPushButton:disabled {{ background: #FCD34D; }}")
        self._btn_start.setCursor(Qt.PointingHandCursor)
        self._btn_start.clicked.connect(self._start_generate)
        row.addWidget(self._btn_start)

        self._btn_stop = QPushButton("⏹ 终止")
        self._btn_stop.setStyleSheet(
            f"QPushButton {{ background: #FEE2E2; color: {C_DANGER};"
            f" border: 1px solid #FECACA; border-radius: 12px;"
            f" padding: 12px 28px; font-size: 15px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: #FECACA; }}"
            f"QPushButton:disabled {{ background: #F3F4F6; color: {C_TEXT_MUTED};"
            f" border: 1px solid {C_INPUT_BDR}; }}")
        self._btn_stop.setCursor(Qt.PointingHandCursor)
        self._btn_stop.clicked.connect(self._stop_task)
        self._btn_stop.setEnabled(False)
        row.addWidget(self._btn_stop)

        row.addStretch()
        return row

    def _build_progress_panel(self) -> QFrame:
        card = self._make_card("ProgressCard")
        layout = self._card_layout(card)

        header = QHBoxLayout()
        header.addWidget(self._section_label("📋 进度与日志"))
        header.addStretch()
        layout.addLayout(header)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setStyleSheet(
            f"QProgressBar {{ border: none; border-radius: {R_MD}px;"
            f" background: #F3F4F6; height: 22px; text-align: center;"
            f" font-size: 12px; color: {C_TEXT}; }}"
            f"QProgressBar::chunk {{ background: {C_PRIMARY};"
            f" border-radius: {R_MD}px; }}")
        layout.addWidget(self._progress_bar)

        self._log_area = QTextEdit()
        self._log_area.setReadOnly(True)
        self._log_area.setMinimumHeight(160)
        self._log_area.setStyleSheet(
            f"QTextEdit {{ background: #1E1E2E; color: #E4E4E7;"
            f" border: none; border-radius: {R_MD}px; padding: 14px;"
            f" font-family: 'Cascadia Code', 'Consolas', 'Microsoft YaHei', monospace;"
            f" font-size: 12px; line-height: 1.6; }}")
        layout.addWidget(self._log_area)

        return card

    # ──── 事件处理 ────

    def _toggle_advanced(self):
        visible = self._advanced_card.isVisible()
        self._advanced_card.setVisible(not visible)
        self._adv_toggle_btn.setText(
            "⚙️ 高级选项 ▼" if not visible else "⚙️ 高级选项 ▶")

    def _pick_output_dir(self):
        d = QFileDialog.getExistingDirectory(
            self._input_outdir, "选择输出目录",
            self._input_outdir.text().strip() or str(Path.home()))
        if d:
            self._input_outdir.setText(d)

    def _on_age_changed(self, age: int):
        """年龄变化时自动更新页数和角色"""
        try:
            config = AgeSystem.get_age_config(age)
            default_pages = config.get("default_pages", 4)
            self._spin_pages.setValue(default_pages)

            default_char = config.get("default_character", "yueyue")
            char_idx = CHARACTER_KEYS.index(default_char)
            self._combo_char.setCurrentIndex(char_idx)
        except Exception:
            pass  # 非内置角色无默认索引，保留当前选择

    def _on_image_toggle(self, checked: bool):
        """显示/隐藏出图相关选项"""
        self._img_opts_container.setVisible(checked)

    def _start_generate(self):
        """开始生成"""
        # 校验必填项
        text_key = self._text_api_key_input.text().strip()
        if not text_key:
            QMessageBox.warning(self._text_api_key_input,
                                "缺少 API Key", "请输入文本 API Key")
            return

        if self._check_gen_images.isChecked():
            img_key = self._image_api_key_input.text().strip()
            if not img_key:
                QMessageBox.warning(self._image_api_key_input,
                                    "缺少 API Key", "请输入出图 API Key 或取消勾选「生成绘本配图」")
                return

        # 收集参数
        style_key = STYLE_KEYS[self._combo_style_w.currentIndex()]
        scene_key = SCENE_KEYS[self._combo_scene.currentIndex()]
        age = self._spin_age.value()
        pages = self._spin_pages.value()
        char_key = CHARACTER_KEYS[self._combo_char.currentIndex()]
        emotion = list(EMOTION_OPTIONS)[self._combo_emo.currentIndex()][0]
        # 主题/叙事支持自定义输入：下拉选择用 key，手输用 currentText()
        ti = self._combo_theme.currentIndex()
        theme = list(THEME_OPTIONS)[ti][0] if ti >= 0 else self._combo_theme.currentText().strip()
        ni = self._combo_narr.currentIndex()
        narrative = list(NARRATIVE_OPTIONS)[ni][0] if ni >= 0 else self._combo_narr.currentText().strip()
        pacing = list(PACING_OPTIONS)[self._combo_pacing.currentIndex()][0]
        color_mood = list(COLOR_MOOD_OPTIONS)[self._combo_color_mood.currentIndex()][0]
        cclp_mode = list(CCLP_OPTIONS)[self._combo_cclp.currentIndex()][0]
        supporting = [k for k, cb in self._supporting_checks.items() if cb.isChecked()]
        animals = [k for k, cb in self._animal_checks.items() if cb.isChecked()]
        custom_topic = self._input_custom_topic.text().strip()
        output_dir = self._input_outdir.text().strip() or "."
        output_formats = ["markdown"]
        if self._format_checks["pdf"].isChecked():
            output_formats.append("pdf")
        if self._format_checks["pptx"].isChecked():
            output_formats.append("pptx")
        gen_images = self._check_gen_images.isChecked()
        aspect_ratio = self._combo_aspect.currentText()
        image_size = self._combo_img_size.currentText()
        image_model = self._image_api_model_combo.currentText()
        poll_interval = self._spin_poll.value()
        concurrency = self._spin_concurrency.value()

        # 创建 worker
        self._worker = PictureBookWorker(
            text_api_key=text_key,
            text_base_url=DS_BASE_URL,
            text_model=self._text_api_model_combo.currentText(),
            image_api_key=self._image_api_key_input.text().strip(),
            image_base_url=IMG_BASE_URL,
            image_model=image_model,
            style_key=style_key, scene_key=scene_key, age=age, pages=pages,
            character_key=char_key, emotion=emotion, theme=theme,
            cclp_mode=cclp_mode, narrative=narrative, pacing=pacing,
            color_mood=color_mood, supporting_chars=supporting,
            animal_companions=animals,
            custom_topic=custom_topic,
            story_title=self._input_title.text().strip(),
            output_dir=output_dir, output_formats=output_formats,
            generate_images=gen_images,
            aspect_ratio=aspect_ratio, image_size=image_size,
            poll_interval=poll_interval, concurrency=concurrency,
        )

        # 连接信号
        self._worker.log_msg.connect(self._log_append)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.page_generated.connect(self._on_page_done)

        # UI 状态
        self._log_area.clear()
        self._log_append("🚀 开始生成绘本...")
        self._btn_start.setEnabled(False)
        self._btn_stop.setEnabled(True)
        self._progress_bar.setValue(0)

        # 连接全局终止信号
        self.main_window.stop_requested.connect(self._stop_task)

        self._worker.start()

    def _stop_task(self):
        if hasattr(self, '_worker') and self._worker and self._worker.isRunning():
            self._worker.stop()
            self._log_append("⏹ 用户中止生成...")

    def _log_append(self, text: str):
        self._log_area.append(text)
        sb = self._log_area.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_progress(self, current: int, total: int, phase: str):
        self._progress_bar.setMaximum(total)
        self._progress_bar.setValue(current)
        self._progress_bar.setFormat(f"{phase} — %p%")

    def _on_page_done(self, page_num: int, title: str, status: str):
        pass  # 日志已在 worker 中输出

    def _on_finished(self, success: bool, summary: str):
        self.main_window.stop_requested.disconnect(self._stop_task)
        self._btn_start.setEnabled(True)
        self._btn_stop.setEnabled(False)

        if success:
            self._log_append("")
            self._log_append("✅ 生成完成！")
            self._log_append(summary)
            QMessageBox.information(
                self._btn_start, "生成完成",
                f"绘本生成完成！\n\n{summary}")
        else:
            self._log_append(f"\n❌ 生成失败: {summary}")
            QMessageBox.warning(
                self._btn_start, "生成失败",
                f"绘本生成过程中出现错误：\n\n{summary}")
