"""分镜脚本生成器 —— 常量与配置"""

import os
import re
from datetime import datetime
from pathlib import Path

# ═══════════════════════════════════════
#  DeepSeek API 配置（对齐 ppt_master）
# ═══════════════════════════════════════

DS_BASE_URL = "https://api.deepseek.com"
DS_MODELS = ["deepseek-v4-pro", "deepseek-v4-flash"]

# ═══════════════════════════════════════
#  Noova API 默认值
# ═══════════════════════════════════════

NOOVA_BASE_URL = "https://noova.cn"
DEFAULT_IMAGE_MODEL = "nano-banana-pro"
DEFAULT_IMAGE_SIZE = "1K"
DEFAULT_ASPECT_RATIO = "16:9"
IMAGE_CONCURRENCY = 3

# ═══════════════════════════════════════
#  生成默认参数
# ═══════════════════════════════════════

DEFAULT_EPISODE_COUNT = 4
DEFAULT_DURATION = 15

# ═══════════════════════════════════════
#  视觉风格预设
# ═══════════════════════════════════════

STYLE_PRESETS: dict[str, str] = {
    "电影写实": (
        "cinematic realism, natural lighting, shallow depth of field, "
        "film grain, 4K, professional color grading, anamorphic lens feel"
    ),
    "国风武侠": (
        "Chinese martial arts ink-wash painting style, flowing fabric, "
        "dynamic action poses, dramatic chiaroscuro lighting, "
        "misty mountains backdrop, elegant calligraphy-inspired composition"
    ),
    "动漫风格": (
        "anime style, cel-shaded, vibrant colors, clean linework, "
        "dynamic angles, Studio Ghibli-inspired backgrounds, "
        "dramatic lighting with rim lights"
    ),
    "赛博朋克": (
        "cyberpunk aesthetic, neon-lit rain-soaked streets, "
        "high contrast blue-purple-magenta palette, volumetric fog, "
        "holographic advertisements, chrome and glass surfaces, Blade Runner mood"
    ),
    "古装宫廷": (
        "historical Chinese palace drama, warm golden and red tones, "
        "elaborate silk costumes with embroidery, symmetrical composition, "
        "soft diffused lighting through paper windows, Tang/Song dynasty aesthetics"
    ),
    "悬疑惊悚": (
        "suspense thriller, low-key chiaroscuro lighting, deep shadows, "
        "desaturated cold color palette, tight claustrophobic framing, "
        "Dutch angles, film noir influence, Alfred Hitchcock tension"
    ),
    "温馨治愈": (
        "warm and healing aesthetic, soft golden-hour natural light, "
        "pastel color palette, gentle bokeh background, cozy lived-in spaces, "
        "slow gentle camera, Ghibli-esque warmth"
    ),
    "科幻未来": (
        "sci-fi futuristic, clean minimalist architecture, cool white-blue-silver tones, "
        "holographic UI elements, vast open spaces, ambient occlusion lighting, "
        "Interstellar/2001 Space Odyssey inspiration"
    ),
}

# ═══════════════════════════════════════
#  运镜词汇表
# ═══════════════════════════════════════

CAMERA_MOVEMENTS: list[str] = [
    "推近", "拉远", "左摇", "右摇", "横移",
    "跟随镜头", "环绕镜头", "360度旋转",
    "升镜头", "降镜头", "希区柯克变焦",
    "手持晃动", "俯拍", "仰拍",
    "固定镜头", "缓慢推镜", "急速推进",
    "稳定跟拍", "中景跟拍", "特写拉远",
]

CAMERA_VOCAB_INJECTION = (
    "可用运镜词汇（仅使用以下词汇描述镜头运动）：\n"
    + "、".join(CAMERA_MOVEMENTS)
    + "\n每段必须使用不同的运镜方式，避免重复。"
)

# ═══════════════════════════════════════
#  路径与文件名常量
# ═══════════════════════════════════════

ASSETS_DIR = "素材"


def create_project_dir() -> str:
    base = Path(os.environ.get("NOOVA_PROJECTS_DIR",
               Path.home() / "NoovaProjects"))
    base.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    proj = str(base / f"storyboard_{stamp}")
    os.makedirs(proj, exist_ok=True)
    return proj


def get_asset_dir(project_dir: str) -> str:
    d = os.path.join(project_dir, ASSETS_DIR)
    os.makedirs(d, exist_ok=True)
    return d


def sanitize_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = re.sub(r'\s+', '_', name.strip())
    return name.strip('. ') or "untitled"
