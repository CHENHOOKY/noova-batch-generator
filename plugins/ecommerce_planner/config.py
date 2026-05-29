"""电商图 —— 常量与配置"""

import os

# ── Text API (文本推理) ──
from config.settings_manager import TEXT_MODELS as DS_MODELS  # noqa: F401
DS_BASE_URL = "https://apic.dpdns.org"
DEFAULT_MAX_TOKENS = 32768
DEFAULT_TEMPERATURE = 0.7

# ── Noova 出图 API ──
NOOVA_BASE_URL = "https://noova.cn"
from plugins._noova_api import MODEL_CONFIG  # noqa: E402
DEFAULT_IMAGE_MODEL = "nano-banana-pro"
DEFAULT_IMAGE_SIZE = "1K"
DEFAULT_ASPECT_RATIO = "1:1"
MAX_CONCURRENCY = 3
MAX_POLL_RETRIES = 120

# ── 路由模式 ──
ROUTING_MODES = {
    "STYLE_FUSION":  "强锚点 - 对标融合模式",
    "STYLE_GUIDED":  "半锚点 - 风格引导模式",
    "FREE_FISSION":  "无锚点 - 自由裂变模式",
    "REDESIGN":      "原图优化改版模式",
}

# ── 下拉选项 ──
CATEGORY_OPTIONS = [
    "快消零食/饮料",
    "高端护肤/美妆/香氛",
    "家居/家具/家纺",
    "数码/家电/3C",
    "母婴/贴身/安全导向",
    "服饰/配饰/鞋包",
    "保健/功能护理",
]

PLATFORM_OPTIONS = [
    "淘宝/天猫",
    "小红书",
    "抖音",
    "京东",
    "亚马逊/独立站",
]

TASK_TYPE_OPTIONS = [
    "主图/首图",
    "详情页图组",
    "种草图/内容图",
    "大促海报/活动图",
    "商品卡/电商封面",
    "参数图/卖点图",
    "直播间背景/短视频视觉",
]

# ── 输出目录 ──
NOOVA_PROJECTS_DIR = os.path.join(os.path.expanduser("~"), "NoovaProjects")
