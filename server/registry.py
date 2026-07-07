"""插件元数据注册表 —— 供前端展示卡片。enabled 标记当前 Web 版已支持的插件。"""

PLUGINS = [
    {"id": "batch_draw",        "name": "批量出图",       "icon": "🎨", "color": "#6366F1", "enabled": True, "desc": "导入 Excel，自动解析提示词与参考图，批量 AI 出图"},
    {"id": "folder_batch_draw", "name": "文件夹批量出图", "icon": "📁", "color": "#8B5CF6", "enabled": True, "desc": "按提示词分组，逐张读取参考图批量生成，结果按组存放"},
    {"id": "upscale",           "name": "图像放大",       "icon": "🔍", "color": "#10B981", "enabled": True,  "desc": "Real-ESRGAN 深度超分，纯 CPU 4 倍放大，无需 API"},
    {"id": "picture_book",      "name": "绘本魔法师",     "icon": "📖", "color": "#F59E0B", "enabled": True, "desc": "AI 生成中英双语儿童绘本，含拼音、学习点与配图"},
    {"id": "ppt_master",        "name": "PPT 大师",       "icon": "📊", "color": "#6366F1", "enabled": True, "desc": "输入主题，AI 自动生成大纲和幻灯片，导出原生 PPTX"},
    {"id": "storyboard",        "name": "分镜脚本生成器", "icon": "🎬", "color": "#8B5CF6", "enabled": True, "desc": "故事 → 四幕剧本 → 素材规划 → AI 出图 → 逐秒分镜"},
    {"id": "ecommerce",         "name": "电商图",         "icon": "🛒", "color": "#F97316", "enabled": True, "desc": "输入产品信息，AI 推理视觉 DNA 并生成 N 套差异化方案图"},
    {"id": "user_manual",       "name": "使用手册",       "icon": "📚", "color": "#0EA5E9", "enabled": True, "desc": "Noova 全部功能插件的图文使用手册与快速上手指南"},
]
