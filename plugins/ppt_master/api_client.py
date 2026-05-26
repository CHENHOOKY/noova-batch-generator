"""PPT 大师 —— DeepSeek API 客户端（基于共享 _text_api）"""

from plugins._text_api import call_text_api_with_retry


def call_deepseek(api_key: str, base_url: str, model: str,
                  system_prompt: str, user_prompt: str,
                  temperature: float = 0.7, max_tokens: int = 65536,
                  json_mode: bool = False,
                  log_fn=None) -> str:
    """调用 DeepSeek Chat Completions API（PPT 大师专用封装）"""
    return call_text_api_with_retry(
        api_key, base_url, model,
        system_prompt, user_prompt,
        temperature=temperature, max_tokens=max_tokens,
        json_mode=json_mode, log_fn=log_fn)


def call_deepseek_with_retry(api_key: str, base_url: str, model: str,
                              system_prompt: str, user_prompt: str,
                              temperature: float = 0.7,
                              max_tokens: int = 65536,
                              json_mode: bool = False,
                              log_fn=None) -> str:
    """带重试的 DeepSeek API 调用（别名，保持向后兼容）"""
    return call_text_api_with_retry(
        api_key, base_url, model,
        system_prompt, user_prompt,
        temperature=temperature, max_tokens=max_tokens,
        json_mode=json_mode, log_fn=log_fn)
