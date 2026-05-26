"""分镜脚本生成器 —— API 客户端薄封装"""

from plugins._text_api import call_text_api_with_retry
from plugins._noova_api import NoovaAPI


def call_deepseek(api_key: str, base_url: str, model: str,
                  system_prompt: str, user_prompt: str,
                  temperature: float = 0.7, max_tokens: int = 16384,
                  json_mode: bool = False, log_fn=None) -> str:
    return call_text_api_with_retry(
        api_key, base_url, model,
        system_prompt, user_prompt,
        temperature=temperature, max_tokens=max_tokens,
        json_mode=json_mode, log_fn=log_fn)


def generate_single_image(api: NoovaAPI, model: str, prompt: str,
                          aspect_ratio: str, image_size: str,
                          save_path: str, poll_interval: int = 20,
                          log_fn=None, cancel_check=None) -> tuple[bool, str]:
    """生成单张图片并保存到 save_path。
    返回 (success, error_message_or_empty_string).
    不抛出异常——失败返回 (False, reason)."""
    try:
        task_id, _ = api.create_draw_task(
            model, prompt, aspect_ratio, image_size, urls=[])
        if log_fn:
            log_fn(f"    任务 {task_id[:12]}... → {save_path}")
        result = api.poll_task_result(
            task_id, poll_interval, log_callback=log_fn,
            cancel_check=cancel_check)
        status = result.get("data", {}).get("status", "unknown")
        if status != "succeeded":
            return False, f"任务状态: {status}"
        img_url = result["data"]["results"][0]["url"]
        api.download_image(img_url, save_path)
        return True, ""
    except Exception as e:
        return False, str(e)
