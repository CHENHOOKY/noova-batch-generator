"""统一的 OpenAI 兼容文本 API 客户端 —— 供 ppt_master / picture_book 复用"""

import json
import time
import random
import urllib.request
import urllib.error


def call_text_api(api_key: str, base_url: str, model: str,
                  system_prompt: str, user_prompt: str,
                  temperature: float = 0.7, max_tokens: int = 16384,
                  json_mode: bool = False, timeout: int = 180,
                  log_fn=None) -> str:
    """调用 OpenAI 兼容 Chat Completions API，返回响应文本"""
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
    req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        choice = result["choices"][0]
        finish = choice.get("finish_reason", "unknown")
        content = choice["message"]["content"] or ""
        usage = result.get("usage", {})
        if log_fn and finish != "stop":
            log_fn(f"  [WARN] API finish_reason={finish}, "
                   f"prompt={usage.get('prompt_tokens','?')}, "
                   f"completion={usage.get('completion_tokens','?')}")
            if finish == "length":
                raise RuntimeError(
                    f"[TRUNCATED] 输出被截断 "
                    f"(completion_tokens={usage.get('completion_tokens','?')})")
        if not content.strip():
            raise RuntimeError(f"API 返回空内容 (finish_reason={finish})")
        if log_fn:
            log_fn(f"  [OK] prompt_tokens={usage.get('prompt_tokens','?')}, "
                   f"completion_tokens={usage.get('completion_tokens','?')}")
        return content
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        if e.code == 401:
            raise RuntimeError("API Key 无效 (401)，请检查后重试")
        if e.code == 403:
            raise RuntimeError(f"API 访问被拒绝 (403): {body_text[:200]}")
        if e.code == 429:
            raise RuntimeError(f"API 请求过于频繁 (429)，请稍后重试")
        raise RuntimeError(f"API HTTP {e.code}: {body_text[:300]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"API 连接失败: {e.reason}")
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as e:
        raise RuntimeError(f"API 响应格式异常: {e}") from e


def call_text_api_with_retry(api_key: str, base_url: str, model: str,
                              system_prompt: str, user_prompt: str,
                              temperature: float = 0.7,
                              max_tokens: int = 16384,
                              json_mode: bool = False,
                              max_retries: int = 3,
                              log_fn=None) -> str:
    """带重试的 API 调用（指数退避 + 截断时自动扩容 max_tokens）"""
    last_error = None
    current_tokens = max_tokens
    for attempt in range(max_retries):
        try:
            return call_text_api(
                api_key, base_url, model,
                system_prompt, user_prompt,
                temperature=temperature, max_tokens=current_tokens,
                json_mode=json_mode, log_fn=log_fn)
        except RuntimeError as e:
            msg = str(e)
            last_error = e
            if "TRUNCATED" in msg:
                current_tokens = min(current_tokens * 2, 524288)
                if log_fn:
                    log_fn(f"  [RETRY] 输出截断，max_tokens → {current_tokens}")
            elif "429" in msg:
                wait = (2 ** attempt) * 5
                if log_fn:
                    log_fn(f"  [RETRY] 限流，{wait}s 后重试...")
                time.sleep(wait)
            elif "401" in msg:
                raise
            else:
                if attempt < max_retries - 1:
                    wait = (2 ** attempt) * 3 + random.uniform(0, 2)
                    if log_fn:
                        log_fn(f"  [RETRY] {msg[:80]}，{wait:.1f}s 后重试...")
                    time.sleep(wait)
    raise last_error
