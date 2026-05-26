"""共享工具函数 —— 供所有插件复用"""

import re
import traceback
import json


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


def safe_traceback() -> str:
    """获取回溯字符串，编辑掉可能的 API 密钥"""
    tb = traceback.format_exc()
    tb = re.sub(r'sk-[a-zA-Z0-9]{10,}', 'sk-***REDACTED***', tb)
    return tb
