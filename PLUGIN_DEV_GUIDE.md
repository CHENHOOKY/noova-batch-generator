# Noova AI 插件开发指南

> 适用版本：v1.0.0+
>
> 本文档面向希望在 Noova AI 助手中添加新功能的开发者。阅读完成后，你将能够独立创建、调试、分发一个新插件。

---

## 目录

1. [架构概览](#1-架构概览)
2. [快速上手：5 分钟写出第一个插件](#2-快速上手5-分钟写出第一个插件)
3. [BasePlugin 完整 API 参考](#3-baseplugin-完整-api-参考)
4. [与主程序通信](#4-与主程序通信)
5. [进阶：带后台任务的插件](#5-进阶带后台任务的插件)
6. [进阶：自定义首页卡片](#6-进阶自定义首页卡片)
7. [插件打包与分发](#7-插件打包与分发)
8. [常见问题](#8-常见问题)

---

## 1. 架构概览

```
main.py                 ← 主程序壳（你不需要改这个文件）
  ├── 侧边栏导航
  │   ├── 🏠 Noova应用   ← 始终可见，返回首页
  │   ├── 功能插件       ← 进入工作区后自动显示所有插件
  │   │   ├── 🎨 批量出图
  │   │   └── 📁 文件夹批量出图
  │   └── 🚀 运行监控台  ← 任务运行时显示
  ├── 首页卡片网格      ← 由插件提供的卡片自动填充
  ├── QStackedWidget    ← 页面切换容器
  │   ├── [0] 首页
  │   ├── [1] 插件A 的工作区
  │   ├── [2] 插件B 的工作区
  │   └── [N] 共享监控台
  └── 插件发现机制       ← 启动时自动扫描 plugins/ 目录

plugin_base.py          ← 插件基类（所有插件继承它）
  └── BasePlugin        ← 定义了 create_card() / create_workspace()

plugins/                ← 插件目录（你的新插件放在这里）
  ├── __init__.py       ← 包标记，不要动
  ├── batch_draw.py     ← 参考：批量出图插件
  └── folder_batch_draw.py  ← 参考：文件夹批量出图插件
```

**核心设计原则：**

- **零侵入**：新增功能不需要修改 `main.py` 或任何已有文件
- **热删除**：删除某个插件文件，程序照常运行，只少一个功能卡片
- **自包含**：每个插件文件包含它需要的全部代码（API 调用、UI、线程等）
- **互不影响**：插件之间完全隔离，侧边栏支持一键切换，各工作区状态独立保留

启动时 `main.py` 会：

1. 扫描 `plugins/*.py`
2. 找到所有 `BasePlugin` 子类
3. 实例化每个插件
4. 调用 `create_card()` 生成首页卡片
5. 调用 `create_workspace()` 生成工作区页面
6. 将卡片 → 工作区的路由注册到导航系统
7. 在侧边栏为每个插件创建快捷导航按钮

---

## 2. 快速上手：5 分钟写出第一个插件

### 目标

创建一个"你好世界"插件，首页卡片点击后显示一段问候文字。

### 第一步：创建文件

在 `plugins/` 目录下新建 `hello_world.py`：

```
test/
└── plugins/
    ├── __init__.py
    ├── batch_draw.py        ← 已有
    └── hello_world.py       ← 新建这个文件
```

### 第二步：编写插件代码

```python
"""你好世界插件 —— 最简单的插件示例"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

from plugin_base import BasePlugin


class HelloWorldPlugin(BasePlugin):
    # ═══ 元数据：定义插件在首页卡片上的展示 ═══
    plugin_id = "hello_world"               # 唯一标识符（英文，下划线分隔）
    name = "你好世界"                        # 卡片标题
    icon = "👋"                              # 卡片图标（emoji）
    color = "#10B981"                       # 主题色（hover 时卡片边框颜色）
    description = "一个最简单的示例插件\n点击卡片查看问候语"  # 卡片描述

    # ═══ 工作区页面 ═══
    def create_workspace(self) -> QWidget:
        """创建点击卡片后展示的工作区"""
        page = QWidget()
        page.setStyleSheet("background-color: #F9FAFB;")

        layout = QVBoxLayout(page)
        layout.setContentsMargins(60, 40, 60, 40)

        title = QLabel("👋 你好世界！")
        title.setStyleSheet(
            "font-size: 32px; font-weight: bold; color: #1A1A1A;"
        )
        layout.addWidget(title)
        layout.addSpacing(16)

        desc = QLabel("这是我的第一个 Noova AI 插件！")
        desc.setStyleSheet("font-size: 16px; color: #666;")
        layout.addWidget(desc)
        layout.addStretch()

        return page
```

### 第三步：运行

```bash
python main.py
```

你会看到：
- **首页**：多了一张 "👋 你好世界" 卡片（绿色边框）
- **点击卡片**：进入一个显示问候文字的工作区
- **删除插件**：删掉 `hello_world.py` → 重启 → 卡片消失，程序正常运行

### 这就是全部

你不必写任何其他代码。卡片样式、导航路由、侧边栏——全部由主程序自动处理。

---

## 3. BasePlugin 完整 API 参考

### 3.1 必须设置的类属性（元数据）

| 属性 | 类型 | 说明 |
|---|---|---|
| `plugin_id` | `str` | 唯一标识符，使用英文和下划线，如 `"batch_draw"`、`"image_editor"` |
| `name` | `str` | 卡片标题，显示在首页卡片上 |
| `icon` | `str` | 卡片图标，使用 emoji 字符，如 `"🎨"`、`"🖼️"` |
| `color` | `str` | 主题色，Hex 格式，如 `"#6366F1"`。hover 时卡片边框和背景色变化 |
| `description` | `str` | 卡片描述文字，支持 `\n` 换行。显示在卡片下半部分 |

### 3.2 必须实现的方法

#### `create_workspace() -> QWidget`

```python
def create_workspace(self) -> QWidget:
    """返回插件的工作区页面组件。

    工作区是用户点击首页卡片后看到的完整页面。
    主程序会自动调用此方法并将返回的 QWidget 加入页面栈。

    返回:
        QWidget: 工作区页面，可以包含任意 Qt 控件

    注意:
        - 此方法在插件注册时就被调用（不是在点击卡片时）
        - 所以创建工作区时不能依赖"用户已点击"状态
        - 如需懒加载，在 create_workspace 中返回占位组件，
          在 on_activate() 中填充内容
    """
```

### 3.3 可选覆写的方法

#### `create_card() -> QPushButton`

```python
def create_card(self) -> QPushButton:
    """创建首页卡片按钮。

    默认实现根据插件的元数据（name, icon, color, description）
    自动生成一张符合主程序风格的卡片。

    如果你想要完全自定义卡片外观（比如加预览图、动画等），
    可以覆写此方法。

    返回:
        QPushButton: 卡片按钮。其 clicked 信号会被主程序自动连接到页面切换
    """
```

#### `on_activate()`

```python
def on_activate(self):
    """当用户点击卡片、工作区被展示时调用。

    可用于：
        - 懒加载数据（首次进入时才请求）
        - 刷新工作区内容
        - 记录使用统计
    """
```

#### `on_deactivate()`

```python
def on_deactivate(self):
    """当用户离开插件工作区（切换到其他页面）时调用。

    可用于：
        - 暂停自动刷新
        - 保存草稿
        - 释放临时资源
    """
```

### 3.4 预置的实例属性

| 属性 | 类型 | 说明 |
|---|---|---|
| `self.main_window` | `ModernAppShell` | 主窗口引用。通过它调用监控台、切换页面等 |
| `self._card` | `QPushButton \| None` | 首页卡片缓存（由 `get_card()` 管理） |
| `self._workspace` | `QWidget \| None` | 工作区页面缓存（由 `get_workspace()` 管理） |

### 3.5 预置的实例方法

```python
def set_main_window(self, window):
    """主程序调用，注入主窗口引用。通常不需要手动调用。"""

def get_card(self) -> QPushButton:
    """获取首页卡片（懒创建）。如需自定义卡片，覆写 create_card() 即可。"""

def get_workspace(self) -> QWidget:
    """获取工作区页面（懒创建）。覆写 create_workspace() 即可。"""
```

---

## 4. 与主程序通信

插件通过 `self.main_window` 与主程序交互。以下是你需要知道的所有接口。

### 4.1 页面导航

用户可以通过两种方式在插件间切换：
1. **侧边栏**（推荐）：进入任意插件后，侧边栏自动显示所有已注册插件，点击即可跳转
2. **首页卡片**：返回首页后点击对应卡片

```python
# 切换到首页
self.main_window.switch_page(0)

# 切换到监控台
self.main_window.switch_to_monitor()
```

**侧边栏行为：**
- 插件按钮**始终可见**，无需进入工作区即可从侧边栏跳转
- "🏠 Noova应用"：返回首页
- "功能插件" 分区：列出所有已注册插件，当前所在插件高亮
- 点击任意插件按钮：直接跳转到对应工作区，各工作区状态独立保留
- 任务运行时：额外显示 "🚀 运行监控台" 按钮

带"← 返回首页"按钮的标准做法（保留以提供双重入口）：

```python
def create_workspace(self):
    page = QWidget()
    layout = QVBoxLayout(page)

    back_btn = QPushButton("← 返回首页")
    back_btn.setStyleSheet(
        "background: transparent; border: none; color: #666; font-size: 14px;"
    )
    back_btn.setCursor(Qt.PointingHandCursor)
    back_btn.clicked.connect(lambda: self.main_window.switch_page(0))
    layout.addWidget(back_btn)

    # ... 其余工作区内容
    return page
```

### 4.2 监控台日志

监控台是一个共享的日志/进度页面，所有插件共用。

```python
# 写入日志（自动追加到监控台文本框并滚动到底部）
self.main_window.monitor_log("任务开始处理...")
self.main_window.monitor_log("第 3 行: 提交成功 ✅")

# 更新进度条（current=当前完成数, total=总数）
self.main_window.monitor_progress(5, 10)  # 进度 = 50%

# 清空日志和进度条
self.main_window.monitor_clear()

# 显示/隐藏停止按钮（任务开始时设为 True，完成时设为 False）
self.main_window.monitor_set_running(True)
```

### 4.3 停止按钮

监控台提供了一个红色的"终止任务"按钮。你需要连接主程序的 `stop_requested` Signal 来响应它：

```python
# 在 _start_task 或类似方法中连接停止信号
self.main_window.stop_requested.connect(self._stop_task)

def _stop_task(self):
    """用户点击了监控台的"终止任务"按钮"""
    if self._worker and self._worker.isRunning():
        self._worker.stop()
```

### 4.4 完整接口速查

| 方法 | 说明 |
|---|---|
| `switch_page(index: int)` | 切换到指定页面（0=首页, 1..N=工作区, 末位=监控台） |
| `switch_to_monitor()` | 切换到监控台并显示侧边栏按钮 |
| `monitor_clear()` | 清空监控台日志和进度条 |
| `monitor_log(text: str)` | 追加日志到监控台 |
| `monitor_progress(current: int, total: int)` | 更新进度条百分比 |
| `monitor_set_running(running: bool)` | 显示/隐藏停止按钮 |
| `stop_requested` | Signal — 连接你的取消处理函数 |

---

## 5. 进阶：带后台任务的插件

多数插件需要执行耗时操作（API 调用、文件处理、图片生成）。以下是标准模式。

### 5.1 Worker 线程模板

```python
from PySide6.QtCore import QThread, Signal


class MyWorker(QThread):
    """后台工作线程 —— 不阻塞 UI"""
    log_msg = Signal(str)                   # 日志信号
    progress_update = Signal(int, int)      # 进度信号 (current, total)
    finished_task = Signal(bool)            # 完成信号 (success)

    def __init__(self, ...):
        super().__init__()
        self.is_running = True
        # 保存你的参数...

    def run(self):
        """线程入口，执行耗时任务"""
        try:
            # 你的业务逻辑...
            self.log_msg.emit("开始处理...")

            for i, item in enumerate(items):
                if not self.is_running:
                    break
                # 处理 item...
                self.progress_update.emit(i + 1, len(items))

            self.finished_task.emit(True)
        except Exception as e:
            self.log_msg.emit(f"错误: {e}")
            self.finished_task.emit(False)

    def stop(self):
        """请求停止"""
        self.is_running = False
```

### 5.2 插件的标准启动流程

```python
class MyPlugin(BasePlugin):
    plugin_id = "my_plugin"
    name = "我的插件"
    icon = "🔧"
    color = "#F59E0B"
    description = "做了一些很酷的事情"

    def create_workspace(self):
        # 你的设置表单 UI...
        self.btn_start.clicked.connect(self._start)
        # ...

    def _start(self):
        # 1. 校验输入
        # 2. 创建 worker
        self._worker = MyWorker(...)

        # 3. 连接信号 → 主程序监控台
        self._worker.log_msg.connect(self.main_window.monitor_log)
        self._worker.progress_update.connect(self.main_window.monitor_progress)
        self._worker.finished_task.connect(self._on_finished)

        # 4. 设置监控台状态
        self.main_window.monitor_clear()
        self.main_window.monitor_set_running(True)
        self.main_window.stop_requested.connect(self._stop)

        # 5. 切换到监控台
        self.main_window.switch_to_monitor()

        # 6. 禁用启动按钮，开始执行
        self.btn_start.setDisabled(True)
        self._worker.start()

    def _on_finished(self, success):
        self.main_window.monitor_set_running(False)
        self.btn_start.setDisabled(False)
        if success:
            QMessageBox.information(self.main_window, "完成", "全部处理完毕！")

    def _stop(self):
        if self._worker and self._worker.isRunning():
            self._worker.stop()
```

### 5.3 并发处理模式（ThreadPoolExecutor）

对于批量任务，你可以参考 `plugins/batch_draw.py` 中的实现：

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading


class BatchWorker(QThread):
    def __init__(self, concurrency=5):
        super().__init__()
        self.concurrency = concurrency
        self._lock = threading.Lock()
        self._completed = 0
        self._total = 0

    def _process_one(self, item):
        """处理单个任务（在线程池中并发执行）"""
        if not self.is_running:
            return
        # 处理逻辑...
        with self._lock:
            self._completed += 1
        self.progress_update.emit(self._completed, self._total)

    def run(self):
        with ThreadPoolExecutor(max_workers=self.concurrency) as executor:
            futures = [executor.submit(self._process_one, item) for item in items]
            for future in as_completed(futures):
                if not self.is_running:
                    for f in futures:
                        f.cancel()
                    break
                try:
                    future.result()
                except Exception:
                    pass
```

**注意事项：**

- **每个线程中创建独立的 API 客户端实例**，不要在线程间共享连接
- 使用 `threading.Lock` 保护共享计数器
- 定期检查 `self.is_running` 以支持用户取消
- QThread 的 Signal 是线程安全的，可以在 worker 线程中 `.emit()`

---

## 6. 进阶：自定义首页卡片

默认卡片已经很好看，但如果你想做得更特别（比如加缩略图、动态内容、状态指示），可以覆写 `create_card()`。

### 6.1 完整自定义示例

```python
def create_card(self) -> QPushButton:
    card = QPushButton()
    card.setMinimumHeight(220)
    card.setCursor(Qt.PointingHandCursor)

    # 卡片背景色直接使用主题色
    card.setStyleSheet(f"""
        QPushButton {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {self.color}, stop:1 {self.color}dd);
            border-radius: 16px;
            text-align: left;
            padding: 0px;
        }}
        QPushButton:hover {{
            background: {self.color};
        }}
    """)

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
    inner.addSpacing(8)

    title = QLabel(self.name)
    title.setStyleSheet(
        "font-size: 20px; font-weight: bold; color: #FFFFFF; background: transparent;"
    )
    inner.addWidget(title)

    desc = QLabel(self.description)
    desc.setStyleSheet("font-size: 13px; color: rgba(255,255,255,0.85); background: transparent;")
    desc.setWordWrap(True)
    inner.addWidget(desc)
    inner.addStretch()

    return card
```

### 6.2 默认可用的卡片

如果你的插件很简单 —— 只设置 `plugin_id`、`name`、`icon`、`color`、`description` 这 5 个属性，不覆写 `create_card()` —— 基类会自动生成一张白底圆角卡片，hover 时边框变为你的主题色，效果与"批量出图"卡片一致。

---

## 7. 插件打包与分发

### 7.1 给别人用你的插件

只需将你的 `.py` 文件放入对方的 `plugins/` 目录，启动 `main.py` 即可自动加载。

```
# 发给别人
你的插件.py  →  放入  plugins/
```

### 7.2 打包成 EXE 时包含插件

使用 PyInstaller 打包时，需要显式包含 `plugins/` 包和 `plugin_base.py`：

```bash
pyinstaller --onefile --windowed \
    --add-data "plugins;plugins" \
    --add-data "plugin_base.py;." \
    --hidden-import plugins \
    --hidden-import plugins.batch_draw \
    --hidden-import plugins.你的插件 \
    main.py
```

每新增一个插件，就在 `--hidden-import` 中加上对应模块名。

### 7.3 插件依赖

如果你的插件需要第三方库（如 `PIL`、`requests`），有两种处理方式：

**方式 A：在插件内延迟导入**（推荐）

```python
def create_workspace(self):
    # 只在工作区被创建时才导入
    import some_heavy_library
    # ...
```

**方式 B：在插件文件顶部导入 + try/except 给出友好提示**

```python
try:
    import some_heavy_library
except ImportError:
    some_heavy_library = None

# 在使用时检查
if some_heavy_library is None:
    QMessageBox.warning(self.main_window, "提示", "请先安装 xxx 库: pip install xxx")
```

---

## 8. 常见问题

### Q: 我的插件没有被加载，怎么排查？

检查以下几点：

1. 文件放在 `plugins/` 目录下，文件名不以 `_` 开头（`__init__.py` 除外）
2. 类继承了 `BasePlugin`（不是实例化，是继承）
3. 运行 `python main.py` 时查看终端输出，成功加载会打印 `[OK] 已加载插件: 你的插件名`
4. 如果看到 `[ERR]` 提示，检查你的 Python 语法是否有错误

### Q: 我的插件需要访问另一个插件的功能，怎么做？

插件之间不直接通信。公共逻辑抽取到 `plugins/` 之外的共享模块（如 `shared/api.py`），由两个插件分别导入。

### Q: 能在工作区放多个标签页吗？

可以。插件的工作区是一个普通的 `QWidget`，你可以在里面放任何 Qt 控件，包括 `QTabWidget`。

### Q: 工作区太宽了怎么限制内容宽度？

在 `create_workspace()` 中设置 `setMaximumWidth()`，或用 `QHBoxLayout` + stretch：

```python
layout = QHBoxLayout(page)
layout.addStretch()
content = QWidget()
content.setMaximumWidth(800)
# 在 content 中放入你的表单
layout.addWidget(content)
layout.addStretch()
```

### Q: 插件卸载时如何处理清理？

主程序不会自动调用清理方法。你需要在 `_stop_task()` 或 `on_deactivate()` 中自行处理。对于后台线程，确保 `QThread.wait()` 等待线程结束。

---

## 附录 A：batch_draw.py 关键代码阅读指南

`plugins/batch_draw.py` 是目前最完整的插件实现，建议阅读顺序：

| 行号范围 | 内容 | 适合参考的场景 |
|---|---|---|
| 38-160 | `NoovaAPI` 类 | 编写 API 客户端 |
| 163-248 | `ExcelProcessor` 类 | 文件解析、数据预处理 |
| 253-368 | `BatchDrawWorker(QThread)` | 后台任务线程 + ThreadPoolExecutor 并发 |
| 373-450 | `BatchDrawPlugin` 元数据 + `create_workspace()` | 完整的设置表单 UI |
| 610-680 | `_start_task()` + 信号连接 | 插件启动任务的标准流程 |

---

## 附录 B：插件文件模板

复制以下内容到 `plugins/你的插件名.py`，替换占位符即可开始开发：

```python
"""你的插件名 —— 简短描述"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMessageBox,
)
from PySide6.QtCore import Qt, QThread, Signal

from plugin_base import BasePlugin


class YourPlugin(BasePlugin):
    # ═══ 元数据 ═══
    plugin_id = "your_plugin_id"    # 唯一 ID（英文）
    name = "你的插件名称"             # 卡片标题
    icon = "🔧"                      # 卡片图标
    color = "#6366F1"               # 主题色
    description = "简短描述\n第二行描述"

    # ═══ 工作区 ═══
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

        # 标题
        title = QLabel(f"{self.icon} {self.name}")
        title.setStyleSheet(
            "font-size: 28px; font-weight: bold; color: #1A1A1A;")
        layout.addWidget(title)

        # 你的内容...
        layout.addWidget(QLabel("在这里添加你的 UI 组件"))
        layout.addStretch()

        return page
```

运行 `python main.py`，你的插件就会出现在首页。
