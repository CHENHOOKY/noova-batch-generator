# Noova AI 批量出图助手

AI 图像生成桌面应用，基于 PySide6 + Noova AI API，集成批量生图、图像放大、PPT 自动生成和智能绘本创作。

## 功能插件

| 插件 | 图标 | 说明 |
|------|------|------|
| **批量出图** | 🎨 | 导入 Excel，自动解析提示词与参考图，批量调用 AI 模型生成图片 |
| **文件夹批量出图** | 📁 | 多文件夹批处理，每文件夹独立配置提示词与参考图 |
| **图像放大** | 🔍 | AI 超分辨率放大（Real-ESRGAN），纯 CPU 运行，支持 PNG/JPG/WebP |
| **PPT 大师** | 📊 | SVG 驱动的 PPT/PPTX 自动生成，5 套设计模板 + 14 种行业配色 |
| **绘本魔法师** | 📖 | AI 故事创作 + 插图生成 + PDF 导出，一键生成完整绘本 |

## 安装

```bash
# 安装依赖
pip install PySide6 requests pandas openpyxl pillow opencv-python-headless numpy onnxruntime python-pptx

# 运行
python main.py
```

### 打包为 exe

```bash
pip install pyinstaller
pyinstaller noova.spec
```

## API 配置

各插件使用 Noova AI API 生成图像，需要 API Key（`sk-` 开头）。可在插件设置面板直接填入，或设置环境变量 `NOOVA_API_KEY`。

绘本魔法师额外使用 DeepSeek API 生成故事文本，需设置环境变量 `DEEPSEEK_API_KEY`。

## 项目结构

```
├── main.py              # 主程序入口 + 应用壳
├── plugin_base.py       # 插件基类
├── plugins/
│   ├── _design.py       # 共享设计令牌
│   ├── _noova_api.py    # Noova API 通信层
│   ├── batch_draw.py    # 批量出图插件
│   ├── folder_batch_draw.py  # 文件夹批量出图插件
│   ├── upscale.py       # 图像放大插件
│   ├── ppt_master.py    # PPT 大师插件
│   └── picture_book.py  # 绘本魔法师插件
├── ppt-master/          # PPT 大师子模块
├── models/              # Real-ESRGAN 模型文件
├── kart-io-picture-book-wizard/  # 绘本引擎
└── noova.spec           # PyInstaller 打包配置
```

## 开发

新增插件只需在 `plugins/` 下创建 `.py` 文件，继承 `BasePlugin` 并实现 `create_workspace()`。详见项目内的插件开发指南。
