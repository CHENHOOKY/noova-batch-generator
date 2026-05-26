# Noova AI — AI 创意桌面套件

基于 PySide6 的桌面端 AI 创意工具集，6 合 1 插件系统，覆盖 AI 生图、超分放大、PPT 自动生成、儿童绘本创作、分镜脚本生成等场景。

v2.4.0 | Python 3.10+ | Windows / macOS / Linux

---

## 功能插件

| 插件 | 图标 | 说明 | 依赖模型 |
|------|------|------|---------|
| **批量出图** | 🎨 | 导入 Excel，自动解析提示词与参考图，批量调用 AI 模型生成图片 | Noova API |
| **文件夹批量出图** | 📁 | 多文件夹批处理，每文件夹独立配置提示词与参考图 | Noova API |
| **图像放大** | 🔍 | AI 超分辨率放大（Real-ESRGAN），纯 CPU 运行，支持 PNG/JPG/WebP | ONNX Runtime（本地） |
| **PPT 大师** | 📊 | SVG 驱动的 PPT/PPTX 自动生成，5 套设计模板 + 14 种行业配色 | DeepSeek API |
| **绘本魔法师** | 📖 | AI 故事创作 + 插图生成 + Markdown/PDF/PPTX 导出，18 种视觉风格 | DeepSeek + Noova API |
| **分镜脚本生成器** | 🎬 | 四幕剧本 → 素材规划 → AI 出图 → Seedance 2.0 逐秒分镜提示词 | DeepSeek + Noova API |

---

## 系统要求

| 项目 | 最低要求 |
|------|---------|
| 操作系统 | Windows 10+（主要）/ macOS 12+ / Linux（需安装 Noto Sans CJK SC 字体） |
| Python | 3.10 或更高 |
| 内存 | 2 GB（推荐 4 GB，ONNX 推理需额外内存） |
| 磁盘 | ~300 MB（含依赖 + Real-ESRGAN 模型首次自动下载 ~5 MB） |
| 网络 | API 类插件需要；仅用 Upscale 插件可离线 |

---

## 安装

```bash
# 1. 进入项目目录
cd Noova

# 2. 创建并激活虚拟环境（推荐）
python -m venv .venv

# Windows:
.venv\Scripts\activate

# macOS / Linux:
source .venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 运行
python main.py
```

---

## API 配置

各插件按需配置 API Key，可在插件设置面板直接填入，也可设环境变量。

| 插件 | 所需 API | 环境变量 | 获取方式 |
|------|---------|---------|---------|
| 批量出图 | Noova AI | `NOOVA_API_KEY` | noova.cn 注册获取（`sk-` 开头） |
| 文件夹批量出图 | Noova AI | `NOOVA_API_KEY` | 同上 |
| 图像放大 | 无 | — | 本地模型，无需 API |
| PPT 大师 | DeepSeek | — | api.deepseek.com 注册获取，在插件面板填入 |
| 绘本魔法师 | DeepSeek + Noova AI | `DEEPSEEK_API_KEY` + `NOOVA_API_KEY` | 同上 |
| 分镜脚本生成器 | DeepSeek + Noova AI | — | 同上，在插件面板填入 |

> API Key 存在本地内存中，不会上传到任何第三方服务器。

---

## 项目结构

```
Noova/
├── main.py                       # 应用主壳（侧边栏 / 卡片网格 / 路由 / 监控台）
├── plugin_base.py                # 插件基类（BasePlugin）
├── noova.spec                    # PyInstaller 打包配置
├── build.bat                     # Windows 一键打包脚本
├── requirements.txt              # Python 依赖
├── logo.ico                      # 应用图标
├── plugins/                      # 插件目录（启动时自动发现）
│   ├── __init__.py               # 包标记
│   ├── _design.py                # 共享设计令牌（字体 / 颜色 / NoScrollComboBox / QSS）
│   ├── _noova_api.py             # 共享 Noova AI 图片 API 客户端 + MODEL_CONFIG
│   ├── _text_api.py              # 共享 OpenAI 兼容文本 API（含重试）
│   ├── _utils.py                 # 共享工具（extract_json / safe_traceback）
│   ├── batch_draw.py             # 批量出图插件
│   ├── folder_batch_draw.py      # 文件夹批量出图插件
│   ├── upscale.py                # 图像放大插件
│   ├── picture_book.py           # 绘本魔法师插件
│   ├── ppt_master/               # PPT 大师插件（package）
│   │   ├── __init__.py
│   │   ├── plugin.py
│   │   ├── worker.py
│   │   ├── config.py
│   │   ├── api_client.py
│   │   ├── prompts.py
│   │   ├── parsers.py
│   │   ├── style_extractor.py
│   │   └── widgets.py
│   └── storyboard_generator/     # 分镜脚本生成器插件（package）
│       ├── __init__.py
│       ├── plugin.py
│       ├── worker.py
│       ├── config.py
│       ├── api_client.py
│       ├── prompts.py
│       ├── widget.py
│       └── asset_manager.py
├── ppt-master/                   # PPT 大师子模块（脚本 / 模板 / 设计参考）
├── kart-io-picture-book-wizard/  # 绘本引擎
└── models/                       # Real-ESRGAN ONNX 模型文件
```

> **命名约定**：`plugins/` 下以 `_` 开头的文件（`_design.py`, `_noova_api.py`, `_text_api.py`, `_utils.py`）为共享基础设施，不会被识别为独立插件。

---

## 关键设计

- **零侵入**：新增插件只需在 `plugins/` 下放 `.py` 文件或 package 目录，继承 `BasePlugin`，设置 5 个元数据属性 + 实现 `create_workspace()`。启动时自动发现，无需修改 `main.py`。
- **热删除**：删除插件文件 → 重启 → 程序正常，卡片消失。
- **共享基础设施**（`plugins/_*.py`）：所有插件复用相同的设计令牌、API 客户端、工具函数，保持视觉和代码一致性。

---

## 打包

```bash
# 一键打包（Windows）
build.bat

# 手动打包
pip install pyinstaller
pyinstaller --clean --noconfirm noova.spec
```

输出：`dist/Noova.exe`

---

## 版本历史

| 版本 | 日期 | 主要变更 |
|------|------|---------|
| 2.4.0 | 2026-05 | 新增分镜脚本生成器插件。插件发现支持 package 结构。共享层提取（`_noova_api` / `_text_api` / `_utils` / `_design`）。NoScrollComboBox 防误触。 |
| 2.3.0 | 2026-04 | 新增 PPT 大师插件（package 结构）。`_design.py` 共享设计令牌。 |
| 2.0.0 | 2026-03 | 迁移至 PySide6。新增绘本魔法师、文件夹批量出图插件。 |
| 1.0.0 | 2025-12 | 初始版本：批量出图 + 图像放大。 |

---

## 故障排查

| 问题 | 解决方案 |
|------|---------|
| `No module named 'PySide6'` | 确保在 `.venv` 中运行 `pip install -r requirements.txt` |
| API 401 错误 | 检查 Key 是否以 `sk-` 开头，粘贴时无多余空格 |
| 图像放大慢 | Real-ESRGAN 纯 CPU 推理，4K 图片约 30-60 秒/张，正常现象 |
| 插件未加载 | 文件名不能以 `_` 开头；类必须继承 `BasePlugin`；查看终端 `[ERR]` 输出 |
| ONNX 模型下载失败 | 检查网络；模型约 5 MB，从 Qualcomm AI Hub 自动下载 |
| PPT 大师 SVG 渲染失败 | 确认 `svglib` + `reportlab` 已安装（在 requirements.txt 中） |

---

## 开发

详见 [PLUGIN_DEV_GUIDE.md](PLUGIN_DEV_GUIDE.md) 获取完整的插件开发指南，包括 API 参考、Worker 模式、共享基础设施用法和代码模板。
