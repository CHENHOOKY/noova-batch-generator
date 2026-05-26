"""PPT 大师 —— 解析与验证工具"""

import re
import json
import unicodedata


def extract_json(text: str) -> dict:
    """从文本中提取 JSON 对象（兼容 markdown 代码块包裹）"""
    text = text.strip()
    m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if m:
        text = m.group(1).strip()
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if m:
        text = m.group(0)
    return json.loads(text)


def parse_design_output(raw: str) -> tuple:
    """从策略师 API 响应中提取 design_spec.md 和 spec_lock.md 内容。
    返回 (design_spec_text, spec_lock_text)。"""
    design_spec = ""
    spec_lock = ""

    m = re.search(
        r'---SECTION:\s*design_spec\.md---\s*\n(.*?)'
        r'---SECTION:\s*spec_lock\.md---\s*\n(.*)',
        raw, re.DOTALL | re.IGNORECASE)
    if m:
        design_spec = m.group(1).strip()
        spec_lock = m.group(2).strip()
    else:
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
        if raw.strip().startswith("##"):
            spec_lock = raw.strip()

    return design_spec, spec_lock


def parse_spec_lock(text: str) -> dict:
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


def extract_svg(text: str) -> str | None:
    """从 DeepSeek 响应中提取 SVG —— 三层 fallback：
    1) 完整 ```svg...``` 代码块
    2) 不闭合的 fence 开头（手动 strip fence 行后提取）
    3) 直接 <svg> 标签（容忍截断/无闭合 </svg>）
    """
    text = text.strip()
    m = re.search(r'```(?:svg|xml|html)?\s*\n(.*?)\n```', text, re.DOTALL)
    if m:
        return m.group(1).strip()
    if text.startswith('```'):
        lines = text.split('\n')
        content = '\n'.join(lines[1:]) if len(lines) > 1 else ''
        if content.rstrip().endswith('```'):
            content = content.rstrip()[:-3].strip()
        m = re.search(r'<svg\b[\s\S]*', content)
        if m:
            return m.group(0).strip()
    else:
        m = re.search(r'<svg\b[\s\S]*', text)
        if m:
            svg = m.group(0).strip()
            end = svg.find('</svg>')
            if end != -1:
                svg = svg[:end + 6]
            return svg
    return None


def validate_svg(svg: str, viewbox: str) -> bool:
    """基本验证 SVG 是否合法"""
    if "<svg" not in svg or "</svg>" not in svg:
        return False
    if "viewBox" not in svg and "viewbox" not in svg:
        return False
    return len(svg) > 100


_ATTR_RE = re.compile(r"(\b\w+(?::\w+)?)\s*=\s*(\"[^\"]*\"|'[^']*')")


def sanitize_duplicate_attrs(svg_text: str) -> str:
    """移除 SVG 标签中的重复 XML 属性，保留首次出现。"""
    def _dedupe_attrs(match):
        tag = match.group(0)
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
        result = ''.join(parts)
        result = re.sub(r'\s+\w+-(?=\s|/?>)', '', result)
        return result

    return re.sub(r'<[A-Za-z]\w*(?::\w+)?\b[^>]*/?>', _dedupe_attrs, svg_text, flags=re.S)


def sanitize_filename(name: str) -> str:
    """将标题转为安全文件名"""
    name = unicodedata.normalize('NFC', name)
    name = re.sub(r'[\\/:*?"<>|]', '', name)
    name = name.strip()[:50]
    return name or "slide"
