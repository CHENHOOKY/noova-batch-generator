# Noova AI 插件开发指南

> 适用版本：v2.4.0+
>
> 本文档面向希望在 Noova AI 中添加新功能的开发者。读完你将掌握：单文件插件和 package 插件的创建方法、共享基础设施的复用方式、Worker 线程模式、以及打包分发流程。

---

## 目录

1. [架构概览](#1-架构概览)
2. [快速上手](#2-快速上手)
   - [2a. 单文件插件（Hello World）](#2a-单文件插件hello-world)
   - [2b. Package 插件](#2b-package-插件)
3. [BasePlugin 完整 API 参考](#3-baseplugin-完整-api-参考)
4. [与主程序通信](#4-与主程序通信)
5. [进阶：带后台任务的插件](#5-进阶带后台任务的插件)
6. [共享基础设施](#6-共享基础设施)
7. [进阶：自定义首页卡片](#7-进阶自定义首页卡片)
8. [插件打包与分发](#8-插件打包与分发)
9. [插件自动发现机制](#9-插件自动发现机制)
10. [常见问题](#10-常见问题)
- [附录 A：batch_draw.py 代码阅读指南](#附录-abatch_drawpy-代码阅读指南)
- [附录 B：插件模板](#附录-b插件模板)
- [附录 C：共享工具速查表](#附录-c共享工具速查表)

---

## 1. 架构概览

```
main.py                    ← 应用主壳（无需修改）
  ├── 侧边栏导航
  │   ├── 🏠 Noova应用       ← 返回首页
  │   ├── 功能插件           ← 所有已注册插件
  │   │   ├── 🎨 批量出图      （单文件插件）
  │   │   ├── 📁 文件夹批量出图 （单文件插件）
  │   │   ├── 🔍 图像放大      （单文件插件）
  │   │   ├── 📖 绘本魔法师    （单文件插件）
  │   │   ├── 📊 PPT大师       （package 插件）
  │   │   └── 🎬 分镜脚本生成器（package 插件）
  │   └── 🚀 运行监控台  ← 任务运行时显示
  ├── 首页卡片网格            ← 由插件自动填充
  ├── QStackedWidget         ← 页面切换容器
  │   ├── [0] 首页
  │   ├── [1..N] 各插件工作区
  │   └── [末位] 共享监控台
  └── 插件发现机制            ← pkgutil + 文件扫描，启动时自动执行

plugin_base.py              ← 插件基类（BasePlugin）

plugins/                    ← 插件目录
  ├── __init__.py           ← 包标记
  ├── _design.py            ← 共享设计令牌（字体 / 颜色 / NoScrollComboBox / QSS）
  ├── _noova_api.py         ← 共享 Noova 图片 API 客户端
  ├── _text_api.py          ← 共享文本 API 客户端
  ├── _utils.py             ← 共享工具函数
  ├── batch_draw.py         ← 单文件插件
  ├── ppt_master/           ← Package 插件（多文件）
  └── storyboard_generator/ ← Package 插件（多文件）
```

**核心设计原则：**

- **零侵入**：新增功能不需要修改 `main.py` 或任何已有文件
- **热删除**：删除某个插件文件/目录，程序照常运行
- **自包含**：每个插件的代码自成体系；共享逻辑下沉到 `plugins/_*.py`
- **互不影响**：插件之间完全隔离，侧边栏一键切换，各工作区状态独立保留
- **共享优先**：`plugins/` 下以 `_` 开头的文件是共享基础设施，所有插件复用

启动时 `main.py` 会：

1. 通过 `pkgutil.iter_modules` + 文件系统扫描发现所有插件模块（排除 `_` 开头的）
2. 找到所有 `BasePlugin` 子类 → 实例化
3. 调用 `set_main_window()` 注入主窗口引用
4. 调用 `get_card()` 生成首页卡片
5. 调用 `get_workspace()` 生成工作区页面
6. 注册路由到导航系统

---

## 2. 快速上手

### 2a. 单文件插件（Hello World）

**第一步：创建文件**

在 `plugins/` 目录下新建 `hello_world.py`：

```python
"""你好世界插件 —— 最简单的插件示例"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt

from plugin_base import BasePlugin
from plugins._design import NoScrollComboBox as QComboBox, COMBO_STYLE, INPUT_STYLE


class HelloWorldPlugin(BasePlugin):
    # ═══ 元数据 ═══
    plugin_id = "hello_world"
    name = "你好世界"
    icon = "👋"
    color = "#10B981"
    description = "一个最简单的示例插件\n点击卡片查看问候语"

    # ═══ 工作区页面 ═══
    def create_workspace(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background-color: #F9FAFB;")

        layout = QVBoxLayout(page)
        layout.setContentsMargins(60, 40, 60, 40)

        # 返回首页按钮
        back_btn = QPushButton("← 返回首页")
        back_btn.setStyleSheet(
            "background: transparent; border: none; color: #666; font-size: 14px;")
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.clicked.connect(lambda: self.main_window.switch_page(0))
        layout.addWidget(back_btn)
        layout.addSpacing(16)

        title = QLabel("👋 你好世界！")
        title.setStyleSheet(
            "font-size: 32px; font-weight: bold; color: #1A1A1A;")
        layout.addWidget(title)
        layout.addSpacing(16)

        desc = QLabel("这是我的第一个 Noova AI 插件！")
        desc.setStyleSheet("font-size: 16px; color: #666;")
        layout.addWidget(desc)
        layout.addStretch()

        return page
```

**第二步：运行**

```bash
python main.py
```

你会看到首页多了一张 "👋 你好世界" 卡片（绿色边框），点击卡片进入工作区。删除 `hello_world.py` 重启，卡片消失，程序正常运行。

> **注意**：从 `_design` 导入 `NoScrollComboBox as QComboBox`，后续代码即可无缝使用 `QComboBox()` — 实际得到的是一个不响应滚轮的版本。这是项目统一约定。

---

### 2b. Package 插件

当插件逻辑复杂（多 API 层、多组件、多阶段流水线），建议使用 package 结构而非单文件。`ppt_master` 和 `storyboard_generator` 都采用此模式。

**目录结构：**

```
plugins/my_plugin/
├── __init__.py      # 必须 re-export 插件类
├── plugin.py        # 插件主类（继承 BasePlugin，实现 create_workspace）
├── worker.py        # QThread 后台工作线程
├── config.py        # 常量、默认值、路径
├── prompts.py       # LLM system/user 提示词模板
├── widgets.py       # 自定义 Qt 组件
└── api_client.py    # API 通信薄封装（可选）
```

**关键：`__init__.py` 必须导出插件类**

这是插件发现机制的要求 —— `pkgutil.iter_modules` 发现 package 后，`importlib.import_module` 导入的是 `__init__.py`。只有 `__init__.py` 导入了插件类，`dir()` 才能找到它：

```python
# plugins/my_plugin/__init__.py
"""我的插件包"""
from plugins.my_plugin.plugin import MyPlugin
```

**plugin.py 主类示例：**

```python
"""我的插件 —— 主插件类"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMessageBox,
)
from PySide6.QtCore import Qt

from plugin_base import BasePlugin
from plugins._design import NoScrollComboBox as QComboBox, COMBO_STYLE, INPUT_STYLE

from plugins.my_plugin.worker import MyWorker
from plugins.my_plugin.config import DEFAULT_VALUE


class MyPlugin(BasePlugin):
    plugin_id = "my_plugin"
    name = "我的插件"
    icon = "🔧"
    color = "#F59E0B"
    description = "做了很酷的事情"

    def __init__(self):
        super().__init__()
        self._worker = None

    def create_workspace(self) -> QWidget:
        page = QWidget()
        # ... 构建 UI ...
        return page
```

**何时用 package 而非单文件：**

| 场景 | 单文件 | Package |
|------|--------|---------|
| 插件 < 500 行 | 推荐 | 也可以 |
| 多个自定义 QWidget 子类 | — | 推荐（widgets.py） |
| 大量常量/预设（>50行） | — | 推荐（config.py） |
| 多套 LLM 提示词 | — | 推荐（prompts.py） |
| 复杂 Worker 编排（多阶段） | — | 推荐（worker.py） |

---

## 3. BasePlugin 完整 API 参考

### 3.1 必须设置的类属性（元数据）

| 属性 | 类型 | 说明 |
|------|------|------|
| `plugin_id` | `str` | 唯一标识符，英文下划线分隔，如 `"batch_draw"` |
| `name` | `str` | 卡片标题，显示在首页卡片上 |
| `icon` | `str` | 卡片图标，emoji 字符，如 `"🎨"` |
| `color` | `str` | 主题色，Hex 格式。hover 时卡片边框变色 |
| `description` | `str` | 卡片描述，支持 `\n` 换行 |

### 3.2 必须实现的方法

**`create_workspace() -> QWidget`**

返回插件的工作区页面。主程序通过 `get_workspace()` 懒调用，结果被缓存。此方法在插件首次被打开时才会被调用（非注册时）。

### 3.3 可选覆写的方法

**`create_card() -> QPushButton`**

创建首页卡片。默认实现根据元数据自动生成白底圆角卡片。如需完全自定义外观（渐变背景、缩略图等），覆写此方法。

**`get_workspace() -> QWidget`**

通常不需要覆写。基类实现调用 `create_workspace()` 并缓存结果。`storyboard_generator` 覆写了它以在布局中加入 `QSplitter` 等顶层结构。如果你覆写它，直接返回 `QWidget` 即可。

**`on_activate()`** / **`on_deactivate()`**

工作区被展示 / 离开时调用。可用于懒加载数据、暂停刷新、保存草稿。

### 3.4 预置实例属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `self.main_window` | `ModernAppShell` | 主窗口引用。**注意：无下划线**，由 `set_main_window()` 注入 |
| `self._card` | `QPushButton \| None` | 首页卡片缓存 |
| `self._workspace` | `QWidget \| None` | 工作区页面缓存 |

### 3.5 预置方法

```python
def set_main_window(self, window):
    """主程序调用，注入主窗口引用。不要手动调用。"""

def get_card(self) -> QPushButton:
    """获取首页卡片（懒创建）。"""

def get_workspace(self) -> QWidget:
    """获取工作区页面（懒创建，调用 create_workspace 并缓存）。"""
```

---

## 4. 与主程序通信

插件通过 `self.main_window` 与主程序壳交互。

### 4.1 页面导航

```python
# 返回首页
self.main_window.switch_page(0)

# 切换到监控台
self.main_window.switch_to_monitor()
```

侧边栏插件按钮始终可见，无需手动处理。习惯上可在工作区顶部加一个"← 返回首页"按钮作为双重入口。

### 4.2 监控台日志

```python
# 写入日志（自动滚动到底部）
self.main_window.monitor_log("任务开始处理...")

# 更新进度条
self.main_window.monitor_progress(5, 10)  # current=5, total=10 → 50%

# 清空日志和进度
self.main_window.monitor_clear()

# 显示 / 隐藏停止按钮
self.main_window.monitor_set_running(True)   # 任务开始
self.main_window.monitor_set_running(False)  # 任务结束
```

### 4.3 停止按钮

监控台有红色"终止任务"按钮，通过 Signal 通知插件：

```python
# 在 _start 中连接
self.main_window.stop_requested.connect(self._stop)

def _stop(self):
    if self._worker and self._worker.isRunning():
        self._worker.cancel()  # 或 self._worker.stop()
```

### 4.4 接口速查

| 方法 / Signal | 说明 |
|--------------|------|
| `switch_page(index)` | 切换到指定页面（0=首页） |
| `switch_to_monitor()` | 切换到监控台 |
| `monitor_clear()` | 清空日志和进度 |
| `monitor_log(text)` | 追加日志 |
| `monitor_progress(current, total)` | 更新进度条 |
| `monitor_set_running(bool)` | 显示/隐藏停止按钮 |
| `stop_requested` | Signal — 连接取消处理函数 |

---

## 5. 进阶：带后台任务的插件

多数插件需要执行耗时操作。以下是项目中实际使用的几种 Worker 模式。

### 5a. 基础 Worker 模板（`cancel()` 推荐模式）

`storyboard_generator` 使用的模式，用 `_cancel` 标志位控制取消，`cancel()` 方法供外部调用：

```python
from PySide6.QtCore import QThread, Signal


class MyWorker(QThread):
    log = Signal(str)
    progress = Signal(int, str)    # (百分比 0-100, 阶段标签)
    finished = Signal(bool, str)   # (成功?, 消息)

    def __init__(self, ...):
        super().__init__()
        self._cancel = False
        # 保存参数...

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            # 阶段 1
            if self._cancel:
                return
            self.log.emit("开始阶段 1...")
            self.progress.emit(10, "处理中...")
            # ...

            # 阶段 2
            if self._cancel:
                return
            # ...

            self.progress.emit(100, "完成!")
            self.finished.emit(True, "全部完成！")
        except Exception as e:
            self.finished.emit(False, str(e))
```

### 5b. 基础 Worker 模板（`stop()` 模式）

`batch_draw` 和 `folder_batch_draw` 使用的模式，用 `is_running` 标志位 + `stop()` 方法：

```python
class BatchWorker(QThread):
    log_msg = Signal(str)
    progress_update = Signal(int, int)  # (current, total)
    finished_task = Signal(bool)

    def __init__(self, ...):
        super().__init__()
        self.is_running = True

    def stop(self):
        self.is_running = False

    def run(self):
        try:
            for i, item in enumerate(items):
                if not self.is_running:
                    break
                # 处理 item...
                self.progress_update.emit(i + 1, len(items))
            self.finished_task.emit(True)
        except Exception as e:
            self.log_msg.emit(f"错误: {e}")
            self.finished_task.emit(False)
```

> **推荐新插件使用 `cancel()` 模式** — 方法名与 QThread 内置方法无冲突，且 `_cancel` 前缀比 `is_running` 语义更清晰。

### 5c. Signal 进度模式

项目中有两种进度 Signal 约定，都是合法的：

| 模式 | Signal 签名 | 使用场景 | 示例插件 |
|------|------------|---------|---------|
| 百分比模式 | `Signal(int, str)` | 多阶段流水线，各阶段占比不同 | storyboard_generator |
| 计数模式 | `Signal(int, int)` | 等权任务队列（如逐行处理 Excel） | batch_draw |

**百分比模式**适合不知道总任务数的场景（如 LLM 生成 + 图片生成的混合流水线）。
**计数模式**适合总任务数已知的批量处理（如 N 张图片逐一生成）。

两种都可以直接连接 `self.main_window.monitor_progress`（接收 `(int, int)`）。

### 5d. 多阶段编排模式

`storyboard_generator` 展示了复杂的四阶段流水线：

```
Phase 1 (剧本) → Phase 2 (素材规划) → Phase 3 (图片生成) → Phase 4 (分镜脚本)
```

每个阶段有独立的 Signal，使 UI 能对各阶段做出差异化响应：

```python
class StoryboardWorker(QThread):
    script_ready = Signal(dict)                  # Phase 1 完成
    asset_plan_ready = Signal(dict)              # Phase 2 完成
    asset_generated = Signal(str, str, bool)     # Phase 3 每张图完成
    storyboard_episode_ready = Signal(int, dict) # Phase 4 每集完成
    finished = Signal(bool, str)
```

### 5e. 插件中完整的启动 / 取消流程

```python
class MyPlugin(BasePlugin):
    def _start(self):
        # 1. 校验输入
        if not validate():
            QMessageBox.warning(self.main_window, "提示", "输入不完整")
            return

        # 2. 准备输出目录
        self._project_dir = create_output_dir()

        # 3. 创建 Worker，传入所有参数
        self._worker = MyWorker(param1, param2, ...)

        # 4. 连接信号
        self._worker.log.connect(self.main_window.monitor_log)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)

        # 5. 设置监控台状态
        self.main_window.monitor_clear()
        self.main_window.monitor_set_running(True)
        self.main_window.stop_requested.connect(self._stop)

        # 6. 切换到监控台 + 禁用按钮 + 启动
        self.main_window.switch_to_monitor()
        self._btn_start.setDisabled(True)
        self._worker.start()

    def _stop(self):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.quit()
            self._worker.wait(3000)

    def _on_finished(self, success: bool, message: str):
        self.main_window.monitor_set_running(False)
        self.main_window.stop_requested.disconnect(self._stop)
        self._btn_start.setDisabled(False)
        if success:
            QMessageBox.information(self.main_window, "完成", message)
        else:
            QMessageBox.critical(self.main_window, "失败", message)

    def _on_progress(self, pct: int, label: str):
        self.main_window.monitor_progress(pct, 100)
        self._progress_bar.setValue(pct)
        self._phase_label.setText(label)
```

**关键细节：**
- 完成后务必 `disconnect` `stop_requested`，否则下次启动会重复连接
- `cancel()` 设置标志位后调用 `quit()` + `wait(3000)` 给线程 3 秒清理时间
- 每个阶段开始前检查 `self._cancel`，及时退出

---

## 6. 共享基础设施

`plugins/` 下有 4 个以 `_` 开头的模块，为所有插件提供共享能力。新插件应优先复用它们而非自己实现。

### 6a. `_design.py` — 设计令牌

```python
from plugins._design import (
    NoScrollComboBox as QComboBox,  # 替代 QComboBox，禁用滚轮切换
    COMBO_STYLE,                     # 统一的 QComboBox QSS
    INPUT_STYLE,                     # 统一的 QLineEdit QSS
    FONT_FAMILY,                     # 跨平台字体字符串
    C_BG, C_SIDEBAR_BG, C_CARD_BG,  # 颜色常量
    C_PRIMARY, C_TEXT, C_TEXT_SUB,
)
```

**约定：所有插件的下拉框都应使用 `NoScrollComboBox as QComboBox`**（而非 PySide6 的 `QComboBox`）。这防止用户滑动滚轮时误触切换选项。因为 `NoScrollComboBox` 继承 `QComboBox`，所有现有 QSS 样式（如 `COMBO_STYLE`）无需修改即可适用。

```python
# 正确做法
from plugins._design import NoScrollComboBox as QComboBox, COMBO_STYLE

combo = QComboBox()
combo.setStyleSheet(COMBO_STYLE)

# 错误做法（会导致滚轮误触）
from PySide6.QtWidgets import QComboBox
```

**颜色常量：**

| 常量 | 值 | 用途 |
|------|-----|------|
| `C_BG` | `#F8F9FC` | 页面背景 |
| `C_SIDEBAR_BG` | `#FFFFFF` | 侧边栏背景 |
| `C_CARD_BG` | `#FFFFFF` | 卡片背景 |
| `C_PRIMARY` | `#6366F1` | 主色调（按钮、选中态） |
| `C_TEXT` | `#1E1E2E` | 主文字色 |
| `C_TEXT_SUB` | `#6B7280` | 次要文字色 |

### 6b. `_noova_api.py` — 图片 API 客户端

```python
from plugins._noova_api import NoovaAPI, MODEL_CONFIG, MAX_CONCURRENCY

# 创建客户端
api = NoovaAPI(api_key_string)

# 查看可用模型及其支持的比例/画质
print(MODEL_CONFIG.keys())  # ['gpt-image-2', 'nano-banana-pro', ...]
config = MODEL_CONFIG['nano-banana-pro']
print(config['ratios'])     # ['1:1', '4:3', '3:2', '16:9', ...]
print(config['sizes'])      # ['1K', '2K', '4K']

# 生成图片（三步）
task_id, _ = api.create_draw_task(model, prompt, aspect_ratio, image_size, urls=[])
result = api.poll_task_result(task_id, poll_interval=20, log_callback=log_fn)
api.download_image(result["data"]["results"][0]["url"], save_path)
```

**并发注意事项：**
- 每个线程应创建自己的 `NoovaAPI` 实例，不要跨线程共享
- `MAX_CONCURRENCY = 10` 是 API 允许的最大并发数
- 项目实际使用 `ThreadPoolExecutor(max_workers=3)` 控制并发

### 6c. `_text_api.py` — 文本 / LLM API 客户端

```python
from plugins._text_api import call_text_api, call_text_api_with_retry

# 单次调用
result = call_text_api(
    api_key, base_url, model,
    system_prompt, user_prompt,
    temperature=0.7, max_tokens=16384,
    json_mode=True,  # 自动添加 response_format: json_object
    log_fn=self.log.emit,
)

# 带重试的调用（推荐）
result = call_text_api_with_retry(
    api_key, base_url, model,
    system_prompt, user_prompt,
    temperature=0.7, max_tokens=32768,
    json_mode=True,
    log_fn=self.log.emit,
)
```

**`call_text_api_with_retry` 自动处理：**
- **429 限流**：指数退避重试（最多 3 次）
- **输出截断**：自动将 `max_tokens` 翻倍后重试（上限 524288）
- **401 认证错误**：立即抛出，不重试
- **其他错误**：随机延迟后重试

**基础 URL 格式：**
- DeepSeek: `https://api.deepseek.com`
- 其他 OpenAI 兼容 API 类似，只需改 base_url

### 6d. `_utils.py` — 工具函数

```python
from plugins._utils import extract_json, safe_traceback

# 从 LLM 输出中提取 JSON（自动处理 markdown 代码块）
raw = '```json\n{"title": "hello"}\n```'
data = extract_json(raw)  # → {"title": "hello"}

# 也支持裸 JSON
raw2 = '{"key": "value"}'
data2 = extract_json(raw2)  # → {"key": "value"}

# 获取脱敏后的 traceback 字符串（API Key 替换为 ***REDACTED***）
try:
    risky_operation()
except Exception:
    self.log.emit(safe_traceback())  # 安全输出到日志
```

### 6e. 代码约定总结

| 约定 | 说明 |
|------|------|
| 下拉框 | 始终从 `_design` 导入 `NoScrollComboBox as QComboBox` |
| 输入框/下拉框样式 | 应用 `COMBO_STYLE` 和 `INPUT_STYLE` |
| 图片生成 | 复用 `NoovaAPI`，不自建 HTTP 调用 |
| 文本 API | 复用 `call_text_api_with_retry`，包含重试和截断恢复 |
| LLM JSON 解析 | 用 `extract_json()` 而非裸 `json.loads()` |
| 错误日志 | 用 `safe_traceback()` 避免泄露 API Key |
| Worker 取消 | 新插件推荐 `cancel()` + `_cancel` 模式 |
| 主窗口引用 | `self.main_window`（无下划线） |
| 输出目录 | `NoovaProjects/[plugin_id]_[timestamp]/` 格式 |

---

## 7. 进阶：自定义首页卡片

默认卡片已符合设计风格。如需完全自定义（渐变背景、缩略图、状态指示），覆写 `create_card()`：

```python
def create_card(self) -> QPushButton:
    card = QPushButton()
    card.setMinimumHeight(220)
    card.setCursor(Qt.PointingHandCursor)
    card.setStyleSheet(f"""
        QPushButton {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {self.color}, stop:1 {self.color}dd);
            border-radius: 16px;
            text-align: left;
            padding: 0px;
        }}
        QPushButton:hover {{ background: {self.color}; }}
    """)

    # 阴影
    shadow = QGraphicsDropShadowEffect()
    shadow.setBlurRadius(20)
    shadow.setColor(QColor(0, 0, 0, 30))
    shadow.setOffset(0, 4)
    card.setGraphicsEffect(shadow)

    inner = QVBoxLayout(card)
    inner.setContentsMargins(28, 28, 28, 28)

    icon_lbl = QLabel(self.icon)
    icon_lbl.setStyleSheet("font-size: 48px; background: transparent;")
    inner.addWidget(icon_lbl)

    title = QLabel(self.name)
    title.setStyleSheet(
        "font-size: 20px; font-weight: bold; color: #FFFFFF; background: transparent;")
    inner.addWidget(title)

    desc = QLabel(self.description)
    desc.setStyleSheet(
        "font-size: 13px; color: rgba(255,255,255,0.85); background: transparent;")
    desc.setWordWrap(True)
    inner.addWidget(desc)
    inner.addStretch()

    return card
```

---

## 8. 插件打包与分发

### 8.1 分发源码

将你的 `.py` 文件（或 package 目录）放入对方的 `plugins/` 目录，启动 `main.py` 即可自动加载。

### 8.2 打包成 EXE

项目使用 PyInstaller + `noova.spec` 文件打包。新增插件后，需在 `noova.spec` 中注册：

**单文件插件：**

```python
# 在 hiddenimports 列表中添加
hiddenimports=[
    # ... 已有的 ...
    'plugins.your_plugin',      # 单文件
]
```

**Package 插件：**

```python
hiddenimports=[
    # ... 已有的 ...
    'plugins.your_plugin',
    'plugins.your_plugin.config',
    'plugins.your_plugin.worker',
    'plugins.your_plugin.widgets',
    # ... 每个子模块一行
],

# datas 中添加整个 package 目录
datas=[
    # ... 已有的 ...
    ('plugins/your_plugin', 'plugins/your_plugin'),
],
```

### 8.3 插件依赖

如果插件需要额外的第三方库：

**方式 A：延迟导入（推荐）**

```python
def create_workspace(self):
    import some_heavy_library  # 只在用到时才导入
```

**方式 B：顶部导入 + 友好提示**

```python
try:
    import some_heavy_library
except ImportError:
    some_heavy_library = None

# 使用时检查
if some_heavy_library is None:
    QMessageBox.warning(self.main_window, "提示", "请安装: pip install xxx")
```

---

## 9. 插件自动发现机制

理解发现机制有助于排查"插件未加载"的问题。

### 两阶段扫描

`main.py._load_plugins()` 执行两阶段扫描：

**第一阶段：`pkgutil.iter_modules`**

```python
import pkgutil
for info in pkgutil.iter_modules(plugins.__path__):
    if info.name == "__init__":
        continue
    # 发现所有模块（.py 文件 和 package 目录）
```

这能找到：
- `plugins/batch_draw.py` → 模块名 `batch_draw`
- `plugins/ppt_master/` → 模块名 `ppt_master`（前提是有 `__init__.py`）

**第二阶段：文件系统扫描（PyInstaller 兼容）**

作为 `pkgutil` 在打包环境中可能失效的兜底方案，直接扫描 `plugins/*.py`：

```python
for py_file in plugins_dir.glob("*.py"):
    if py_file.name.startswith("_"):
        continue  # 排除 _开头 的共享模块
```

### 排除规则

文件名以 `_` 开头的模块 **不会被注册为插件**：
- `_design.py` ❌ 不注册
- `_noova_api.py` ❌ 不注册
- `_text_api.py` ❌ 不注册
- `_utils.py` ❌ 不注册
- `batch_draw.py` ✅ 注册
- `__init__.py` ✅ 跳过（硬编码排除）

### Package 插件的关键要求

对于 package 插件，`importlib.import_module("plugins.ppt_master")` 实际导入的是 `plugins/ppt_master/__init__.py`。因此 `__init__.py` **必须**导入插件类，使其在模块的 `dir()` 中可见：

```python
# ✅ 正确：__init__.py 导出了插件类
from plugins.storyboard_generator.plugin import Seedance2Plugin

# ❌ 错误：__init__.py 为空，插件类不会被发现
```

### 注册流程

对每个发现的模块：

1. `importlib.import_module(module_name)` 导入
2. `dir(module)` 遍历所有属性
3. 检查每个属性：`isinstance(attr, type) and issubclass(attr, BasePlugin) and attr is not BasePlugin`
4. 找到第一个匹配的类 → 实例化 → `set_main_window()` → 注册

---

## 10. 常见问题

### Q: 我的插件没有被加载，怎么排查？

1. 文件/目录在 `plugins/` 下，名称不以 `_` 开头
2. 类继承了 `BasePlugin`
3. Package 插件的 `__init__.py` 是否导出了插件类？
4. 运行 `python main.py`，查看终端 `[OK]` / `[ERR]` 输出

### Q: 应该用单文件还是 Package？

- 单文件：<500 行，UI + 一个 Worker，逻辑简单
- Package：多组件、多阶段流水线、大量常量/提示词、团队协作

### Q: 如何正确引用主窗口？

用 `self.main_window`（**无下划线**）。它由 `BasePlugin.set_main_window()` 在注册时自动注入。

### Q: `get_workspace()` 和 `create_workspace()` 有什么区别？

`create_workspace()` 是你覆写的方法，返回 `QWidget`。`get_workspace()` 是基类的懒加载包装器：首次调用时调用 `create_workspace()` 并缓存结果，后续直接返回缓存。大多数情况只需覆写 `create_workspace()`。如果你的插件需要顶层 `QSplitter` 等复杂布局，可以直接覆写 `get_workspace()`。

### Q: 如何复用 Noova 图片生成 API？

```python
from plugins._noova_api import NoovaAPI
api = NoovaAPI(api_key)
task_id, _ = api.create_draw_task(model, prompt, ratio, size, urls)
```
每个线程创建独立实例。

### Q: 如何调用 LLM 文本 API？

```python
from plugins._text_api import call_text_api_with_retry
result = call_text_api_with_retry(
    api_key, base_url, model,
    system_prompt, user_prompt,
    json_mode=True, log_fn=self.log.emit,
)
```

### Q: 如何解析 LLM 返回的 JSON？

```python
from plugins._utils import extract_json
data = extract_json(raw_response)  # 自动处理 ```json ... ``` 包裹
```

### Q: 如何让下拉框不响应滚轮？

从 `_design` 导入 `NoScrollComboBox as QComboBox` 替代 PySide6 的 `QComboBox`。这是项目统一要求。

### Q: 如何给所有下拉框和输入框统一风格？

```python
from plugins._design import COMBO_STYLE, INPUT_STYLE, NoScrollComboBox as QComboBox

combo = QComboBox()
combo.setStyleSheet(COMBO_STYLE)

line_edit = QLineEdit()
line_edit.setStyleSheet(INPUT_STYLE)
```

### Q: 工作区太宽怎么限制？

```python
layout = QHBoxLayout(page)
layout.addStretch()
content = QWidget()
content.setMaximumWidth(800)
layout.addWidget(content)
layout.addStretch()
```

### Q: 插件卸载时如何清理？

主程序不会自动调用清理。在 `_stop` 或 `on_deactivate` 中自行处理。对 Worker 线程，确保 `quit()` + `wait()`。

---

## 附录 A：batch_draw.py 代码阅读指南

`batch_draw.py` 是最成熟的单文件插件。参照以下顺序阅读：

| 阅读顺序 | 文件 / 类 | 学习内容 |
|---------|----------|---------|
| 1 | `plugins/_noova_api.py` → `NoovaAPI` | 图片生成 API：创建任务、轮询、下载 |
| 2 | `plugins/batch_draw.py` → `ExcelProcessor` | Excel 解析、嵌入图片提取 |
| 3 | `plugins/batch_draw.py` → `BatchDrawWorker` | ThreadPoolExecutor 并发 + `stop()` 取消模式 |
| 4 | `plugins/batch_draw.py` → `BatchDrawPlugin.create_workspace()` | 完整设置表单（模型联动下拉框、文件选择器） |
| 5 | `plugins/batch_draw.py` → `_start_task()` / `_on_finished()` | 启动/停止信号连接、监控台集成 |

以及 package 插件的参考：

| 阅读顺序 | 文件 | 学习内容 |
|---------|------|---------|
| 1 | `plugins/storyboard_generator/plugin.py` | QSplitter 左右面板布局、4 Tab 工作区 |
| 2 | `plugins/storyboard_generator/worker.py` | 多阶段编排（Phase 1→4）+ `cancel()` 模式 |
| 3 | `plugins/storyboard_generator/asset_manager.py` | 并发图片生成 + 取消回调 |

---

## 附录 B：插件模板

### B1. 单文件插件模板

```python
"""你的插件名 —— 简短描述"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMessageBox,
)
from PySide6.QtCore import Qt, QThread, Signal

from plugin_base import BasePlugin
from plugins._design import NoScrollComboBox as QComboBox, COMBO_STYLE, INPUT_STYLE


class YourPlugin(BasePlugin):
    plugin_id = "your_plugin_id"
    name = "你的插件名称"
    icon = "🔧"
    color = "#6366F1"
    description = "简短描述\n第二行描述"

    def create_workspace(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background-color: #F9FAFB;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(60, 40, 60, 40)

        back_btn = QPushButton("← 返回首页")
        back_btn.setStyleSheet(
            "background: transparent; border: none; color: #666; font-size: 14px;")
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.clicked.connect(lambda: self.main_window.switch_page(0))
        layout.addWidget(back_btn)
        layout.addSpacing(16)

        title = QLabel(f"{self.icon} {self.name}")
        title.setStyleSheet("font-size: 28px; font-weight: bold; color: #1A1A1A;")
        layout.addWidget(title)

        layout.addWidget(QLabel("在这里添加你的 UI 组件"))
        layout.addStretch()

        return page
```

### B2. Package 插件模板

**`plugins/my_plugin/__init__.py`：**

```python
"""我的插件包"""
from plugins.my_plugin.plugin import MyPlugin
```

**`plugins/my_plugin/config.py`：**

```python
"""常量与配置"""

DEFAULT_VALUE = 42
MY_API_BASE_URL = "https://api.example.com"
```

**`plugins/my_plugin/worker.py`：**

```python
"""后台 Worker"""

from PySide6.QtCore import QThread, Signal


class MyWorker(QThread):
    log = Signal(str)
    progress = Signal(int, str)
    finished = Signal(bool, str)

    def __init__(self, param1, parent=None):
        super().__init__(parent)
        self._param1 = param1
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            self.log.emit("开始处理...")
            # 你的业务逻辑...
            self.finished.emit(True, "完成！")
        except Exception as e:
            self.finished.emit(False, str(e))
```

**`plugins/my_plugin/plugin.py`：**

```python
"""我的插件 —— 主插件类"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMessageBox,
)
from PySide6.QtCore import Qt

from plugin_base import BasePlugin
from plugins._design import NoScrollComboBox as QComboBox, COMBO_STYLE, INPUT_STYLE

from plugins.my_plugin.worker import MyWorker
from plugins.my_plugin.config import DEFAULT_VALUE


class MyPlugin(BasePlugin):
    plugin_id = "my_plugin"
    name = "我的插件"
    icon = "🔧"
    color = "#F59E0B"
    description = "一个 package 结构的插件示例"

    def __init__(self):
        super().__init__()
        self._worker = None

    def create_workspace(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background-color: #F9FAFB;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(60, 40, 60, 40)

        back_btn = QPushButton("← 返回首页")
        back_btn.setStyleSheet(
            "background: transparent; border: none; color: #666; font-size: 14px;")
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.clicked.connect(lambda: self.main_window.switch_page(0))
        layout.addWidget(back_btn)
        layout.addSpacing(16)

        title = QLabel(f"{self.icon} {self.name}")
        title.setStyleSheet("font-size: 28px; font-weight: bold; color: #1A1A1A;")
        layout.addWidget(title)

        layout.addWidget(QLabel("package 插件工作区"))
        layout.addStretch()

        return page
```

---

## 附录 C：共享工具速查表

| 工具 | 导入路径 | 用途 |
|------|---------|------|
| `NoScrollComboBox` | `plugins._design` | 替代 QComboBox，禁用滚轮切换 |
| `COMBO_STYLE` | `plugins._design` | 统一的下拉框 QSS 样式 |
| `INPUT_STYLE` | `plugins._design` | 统一的输入框 QSS 样式 |
| `FONT_FAMILY` | `plugins._design` | 跨平台中文字体字符串 |
| `C_PRIMARY` / `C_TEXT` / `C_BG` 等 | `plugins._design` | 颜色常量 |
| `NoovaAPI` | `plugins._noova_api` | Noova 图片生成 API 客户端 |
| `MODEL_CONFIG` | `plugins._noova_api` | 可用模型及其支持的画质/比例 |
| `MAX_CONCURRENCY` | `plugins._noova_api` | API 最大并发数（10） |
| `call_text_api` | `plugins._text_api` | 单次 OpenAI 兼容 API 调用 |
| `call_text_api_with_retry` | `plugins._text_api` | 带重试的 API 调用（推荐） |
| `extract_json` | `plugins._utils` | 从 LLM 输出中提取 JSON（处理 markdown 代码块） |
| `safe_traceback` | `plugins._utils` | 获取 API Key 已脱敏的 traceback 字符串 |
