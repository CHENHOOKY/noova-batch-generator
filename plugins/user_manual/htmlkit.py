"""HTML 构建工具集 —— 为「使用手册」插件生成图文并茂的富文本。

QTextBrowser 基于 Qt 的 QTextDocument，仅支持 HTML4 / CSS2 的一个子集：
  - 表格 <table>（cellpadding / cellspacing / width / bgcolor 属性可靠）
  - 内联 style：color / background-color / font-weight / font-size / text-align
  - 列表 <ul><ol>、标题 <h1~h6>、段落 <p>、预格式 <pre>、水平线 <hr>
  - 不支持：flex / grid / box-shadow / border-radius / 外边距合并
因此本工具集用「单格着色表格」实现彩色提示框，确保在 QTextBrowser 中渲染稳定。
所有函数均返回 HTML 字符串，可自由拼接。
"""

from plugins._design import (
    C_PRIMARY, C_PRIMARY_HV, C_TEXT, C_TEXT_SUB, C_TEXT_MUTED,
    C_GREEN, C_AMBER, C_DANGER, C_BG,
)


# ── 提示框配色 ──────────────────────────────
_CALLOUT = {
    "info":    ("#EEF2FF", "#3730A3", "ℹ️",  "说明"),
    "tip":     ("#ECFDF5", "#065F46", "💡",  "小提示"),
    "warn":    ("#FFFBEB", "#92400E", "⚠️",  "注意"),
    "danger":  ("#FEF2F2", "#991B1B", "⛔",  "重要"),
    "success": ("#ECFDF5", "#065F46", "✅",  "已完成"),
}


def esc(text: str) -> str:
    """转义 HTML 特殊字符"""
    return (str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;"))


# ═══════════════════════  结构元素  ═══════════════════════

def hero(icon: str, title: str, subtitle: str, color: str = C_PRIMARY) -> str:
    """页面顶部标题横幅（用着色表格模拟彩色卡片）"""
    return (
        '<table cellspacing="0" cellpadding="18" width="100%">'
        f'<tr><td style="background-color:{color};">'
        '<p style="color:#FFFFFF;font-size:22px;font-weight:800;margin:0;">'
        f'{icon}  {title}</p>'
        '<p style="color:rgba(255,255,255,0.85);font-size:13px;margin:6px 0 0 0;">'
        f'{subtitle}</p>'
        '</td></tr></table><p style="margin:0;">&nbsp;</p>')


def section(title: str, icon: str = "") -> str:
    """二级章节标题（带主题色）"""
    head = f"{icon}  {title}" if icon else title
    return (f'<h2 style="color:{C_PRIMARY};font-size:17px;font-weight:700;'
            f'border-bottom:2px solid {C_PRIMARY};padding-bottom:4px;margin:18px 0 10px 0;">'
            f'{head}</h2>')


def sub(title: str) -> str:
    """三级小标题"""
    return (f'<h3 style="color:{C_TEXT};font-size:14px;font-weight:700;'
            f'margin:14px 0 6px 0;">{title}</h3>')


def para(text: str) -> str:
    """正文段落"""
    return f'<p style="color:{C_TEXT};font-size:13px;line-height:1.6;margin:6px 0;">{text}</p>'


def muted(text: str) -> str:
    """弱化说明文字"""
    return f'<p style="color:{C_TEXT_MUTED};font-size:12px;margin:4px 0;">{text}</p>'


def bullets(items) -> str:
    """无序列表"""
    lis = "".join(f'<li style="color:{C_TEXT};font-size:13px;">{it}</li>' for it in items)
    return f'<ul style="margin:6px 0 6px 18px;">{lis}</ul>'


def steps(items) -> str:
    """有序步骤列表"""
    lis = "".join(f'<li style="color:{C_TEXT};font-size:13px;line-height:1.6;margin:4px 0;">{it}</li>'
                  for it in items)
    return f'<ol style="margin:6px 0 6px 22px;">{lis}</ol>'


def code(text: str) -> str:
    """代码 / 示例块（灰底等宽）"""
    return ('<table cellspacing="0" cellpadding="10" width="100%" style="margin:6px 0;">'
            '<tr><td style="background-color:#F3F4F6;">'
            '<pre style="margin:0;font-family:Consolas,Monaco,monospace;'
            f'font-size:12px;color:#1E1E2E;white-space:pre-wrap;">{esc(text)}</pre>'
            '</td></tr></table>')


def divider() -> str:
    return '<hr style="border:none;border-top:1px solid #ECEDF0;margin:16px 0;">'


# ═══════════════════════  提示框  ═══════════════════════

def callout(kind: str = "info", title: str = "", body: str = "") -> str:
    """彩色提示框。kind: info / tip / warn / danger / success"""
    bg, fg, icon, default_title = _CALLOUT.get(kind, _CALLOUT["info"])
    t = title or default_title
    return ('<table cellspacing="0" cellpadding="12" width="100%" style="margin:8px 0;">'
            f'<tr><td style="background-color:{bg};">'
            f'<p style="color:{fg};font-size:13px;font-weight:700;margin:0 0 4px 0;">'
            f'{icon}  {t}</p>'
            f'<span style="color:{fg};font-size:12.5px;">{body}</span>'
            '</td></tr></table>')


def tip(body: str, title: str = "") -> str:
    return callout("tip", title, body)


def warn(body: str, title: str = "") -> str:
    return callout("warn", title, body)


def info(body: str, title: str = "") -> str:
    return callout("info", title, body)


def danger(body: str, title: str = "") -> str:
    return callout("danger", title, body)


# ═══════════════════════  表格  ═══════════════════════

def _th(text: str, bg: str) -> str:
    return (f'<th style="background-color:{bg};color:#FFFFFF;font-size:12.5px;'
            f'font-weight:700;padding:9px 12px;text-align:left;">{text}</th>')


def _td(text: str, bg: str = "#FFFFFF", bold: bool = False) -> str:
    fw = "700" if bold else "400"
    return (f'<td style="background-color:{bg};color:{C_TEXT};font-size:12.5px;'
            f'font-weight:{fw};padding:9px 12px;">{text}</td>')


def table(headers, rows, header_bg: str = C_PRIMARY, zebra: bool = True) -> str:
    """通用表格。headers: list[str]；rows: list[list[str]]"""
    head = "".join(_th(h, header_bg) for h in headers)
    body_rows = []
    for i, row in enumerate(rows):
        bg = "#F9FAFB" if (zebra and i % 2 == 1) else "#FFFFFF"
        cells = "".join(_td(c, bg, bold=(j == 0)) for j, c in enumerate(row))
        body_rows.append(f'<tr>{cells}</tr>')
    body = "".join(body_rows)
    return ('<table cellspacing="0" cellpadding="0" width="100%" '
            'style="margin:8px 0;border:1px solid #ECEDF0;">'
            f'<tr>{head}</tr>{body}</table>')


def param_table(rows) -> str:
    """参数表：参数 | 说明 | 可选值 / 默认"""
    return table(["参数", "说明", "可选值 / 默认"], rows, header_bg=C_PRIMARY)


def facts(rows) -> str:
    """快速事实表：项目 | 内容"""
    return table(["项目", "内容"], rows, header_bg="#334155")


def chip(text: str, color: str = C_PRIMARY) -> str:
    """行内彩色标签"""
    return (f'<span style="background-color:{color};color:#FFFFFF;'
            f'font-size:11px;font-weight:600;padding:2px 8px;'
            f'margin:0 2px;">{text}</span>')
