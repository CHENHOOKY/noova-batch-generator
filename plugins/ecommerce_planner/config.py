"""电商套图AI规划器 —— 常量与配置"""

# ── DeepSeek API ──
DS_BASE_URL = "https://api.deepseek.com"
DS_MODELS = ["deepseek-v4-pro", "deepseek-v4-flash"]
DEFAULT_MAX_TOKENS = 32768
DEFAULT_TEMPERATURE = 0.7

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
import os
NOOVA_PROJECTS_DIR = os.path.join(os.path.expanduser("~"), "NoovaProjects")
