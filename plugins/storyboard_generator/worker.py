"""分镜脚本生成器 —— 后台 Worker（4 阶段编排）"""

import json
import os
from datetime import datetime

from PySide6.QtCore import QThread, Signal

from plugins._utils import extract_json, safe_traceback
from plugins.storyboard_generator.api_client import call_deepseek
from plugins.storyboard_generator.prompts import (
    SCRIPT_SYSTEM, make_script_user,
    ASSET_SYSTEM, make_asset_user,
    STORYBOARD_SYSTEM, make_storyboard_user,
)
from plugins.storyboard_generator.asset_manager import (
    ImageTask, build_asset_queue, generate_all_assets,
)
from plugins.storyboard_generator.config import (
    sanitize_filename, get_asset_dir,
)


class StoryboardWorker(QThread):
    # Phase 1
    script_ready = Signal(dict)
    # Phase 2
    asset_plan_ready = Signal(dict)
    # Phase 3
    asset_generated = Signal(str, str, bool)  # (asset_id, filepath, success)
    asset_progress = Signal(int, int)          # (done, total)
    # Phase 4
    storyboard_episode_ready = Signal(int, dict)  # (ep_num, sb_data)
    # Generic
    log = Signal(str)
    progress = Signal(int, str)    # (pct, label)
    finished = Signal(bool, str)

    def __init__(self, api_key: str, base_url: str, ds_model: str,
                 noova_api, image_model: str, image_size: str, image_ratio: str,
                 story_text: str, style_label: str, style_desc: str,
                 episode_count: int, duration: int, project_dir: str,
                 run_images: bool = True, parent=None):
        super().__init__(parent)
        self._api_key = api_key
        self._base_url = base_url
        self._ds_model = ds_model
        self._noova = noova_api
        self._img_model = image_model
        self._img_size = image_size
        self._img_ratio = image_ratio
        self._story = story_text
        self._style_label = style_label
        self._style_desc = style_desc
        self._ep_count = episode_count
        self._duration = duration
        self._proj_dir = project_dir
        self._run_images = run_images
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            self._do_all()
        except Exception as e:
            if not self._cancel:
                self.log.emit(f"[FATAL] {e}")
                self.log.emit(safe_traceback())
                self.finished.emit(False, str(e))

    def _ds(self, system: str, user: str, max_tokens: int = 32768,
            json_mode: bool = True, temperature: float = 0.7) -> str:
        return call_deepseek(
            self._api_key, self._base_url, self._ds_model,
            system, user,
            temperature=temperature, max_tokens=max_tokens,
            json_mode=json_mode, log_fn=self.log.emit)

    def _do_all(self):
        # ═══ Phase 1: Script ═══
        self.log.emit("📝 Phase 1/4: 生成四幕剧本...")
        self.progress.emit(5, "生成剧本中...")

        raw = self._ds(SCRIPT_SYSTEM,
                       make_script_user(self._story, self._style_desc, self._ep_count),
                       max_tokens=32768)
        script = extract_json(raw)
        ep_count = len(script.get("episodes", []))
        self.log.emit(f"  ✓ 剧本生成完成: {script.get('title', '')} ({ep_count} 集)")
        self._save_md(f"{sanitize_filename(script.get('title', 'untitled'))}_剧本.md",
                      self._fmt_script_md(script))
        self.script_ready.emit(script)

        if self._cancel:
            return

        # ═══ Phase 2: Asset Planning ═══
        self.log.emit("📋 Phase 2/4: 规划素材提示词...")
        self.progress.emit(25, "规划素材中...")

        raw = self._ds(ASSET_SYSTEM,
                       make_asset_user(json.dumps(script, ensure_ascii=False, indent=2),
                                       self._style_desc),
                       max_tokens=32768)
        asset_plan = extract_json(raw)
        ca_count = len(asset_plan.get("character_assets", []))
        sa_count = len(asset_plan.get("scene_assets", []))
        pa_count = len(asset_plan.get("prop_assets", []))
        self.log.emit(f"  ✓ 素材规划完成: {ca_count}角色图, {sa_count}场景, {pa_count}道具")
        self._save_md(f"{sanitize_filename(script.get('title', 'untitled'))}_素材清单.md",
                      self._fmt_asset_md(asset_plan, script.get("title", "")))
        self.asset_plan_ready.emit(asset_plan)

        if self._cancel:
            return

        # ═══ Phase 3: Image Generation ═══
        if self._run_images and self._noova:
            self.log.emit("🎨 Phase 3/4: 生成素材图片...")
            self.progress.emit(40, "生成素材图中...")

            asset_dir = get_asset_dir(self._proj_dir)
            safe_title = sanitize_filename(script.get("title", "untitled"))
            tasks = build_asset_queue(asset_plan, asset_dir, safe_title)
            self.log.emit(f"  待生成: {len(tasks)} 张图片 (并发: 3)")

            for task, ok, result in generate_all_assets(
                    self._noova, tasks,
                    self._img_model, self._img_size, self._img_ratio,
                    log_fn=self.log.emit,
                    progress_fn=lambda d, t: self.asset_progress.emit(d, t),
                    cancel_check=lambda: self._cancel):
                if self._cancel:
                    return
                if ok:
                    self.log.emit(f"    ✅ {task.asset_id} {task.asset_name} ({task.view})")
                else:
                    self.log.emit(f"    ❌ {task.asset_id} {task.asset_name}: {result}")
                self.asset_generated.emit(task.asset_id, result if ok else "", ok)
                pct = 40 + int(30 * (self._asset_done_count(tasks)) / max(len(tasks), 1))
                self.progress.emit(pct, f"生成素材图...")
        else:
            self.log.emit("⏭ Phase 3/4: 跳过图片生成")

        if self._cancel:
            return

        # ═══ Phase 4: Storyboard ═══
        self.log.emit("🎬 Phase 4/4: 生成分镜脚本...")
        self.progress.emit(75, "生成分镜脚本中...")

        episodes = script.get("episodes", [])
        characters = script.get("characters", [])
        scenes = script.get("scenes", [])
        props = script.get("props", [])
        all_sb = []
        total = len(episodes)

        for i, ep in enumerate(episodes):
            if self._cancel:
                return

            ep_num = ep.get("episode", i + 1)
            self.log.emit(f"  🎥 第 {ep_num}/{total} 集: {ep.get('title', '')}")

            raw = self._ds(STORYBOARD_SYSTEM,
                           make_storyboard_user(
                               ep, characters, scenes, props,
                               self._style_desc, self._duration, ep_num, total),
                           max_tokens=32768)
            sb = extract_json(raw)
            all_sb.append(sb)

            self._save_md(
                f"{sanitize_filename(script.get('title', 'untitled'))}_E{ep_num:02d}_分镜.md",
                self._fmt_storyboard_md(sb, ep))
            self.storyboard_episode_ready.emit(ep_num, sb)

            pct = 75 + int(25 * (i + 1) / total)
            self.progress.emit(pct, f"分镜: {ep_num}/{total}")

        self.log.emit("  ✓ 全部分镜脚本生成完成")

        # Assemble final output
        final = {
            **script,
            "asset_plan": asset_plan,
            "storyboards": all_sb,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "style": self._style_label,
            "duration_per_episode": self._duration,
        }
        self._save_json("project.json", final)
        self._save_md("使用指南.md", self._fmt_guide(script))

        self.progress.emit(100, "完成!")
        self.finished.emit(True, "全部分镜脚本生成完成！")

    # ── helpers ──

    def _asset_done_count(self, tasks: list[ImageTask]) -> int:
        return sum(1 for t in tasks if os.path.exists(t.save_path))

    def _save_md(self, filename: str, content: str):
        with open(os.path.join(self._proj_dir, filename), "w", encoding="utf-8") as f:
            f.write(content)

    def _save_json(self, filename: str, data: dict):
        with open(os.path.join(self._proj_dir, filename), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ── Markdown formatters ──

    def _fmt_script_md(self, d: dict) -> str:
        lines = [
            f"# {d.get('title', '未命名')}",
            "",
            f"> {d.get('summary', '')}",
            "",
            f"- **类型**: {d.get('genre', '')}",
            f"- **风格**: {d.get('style_description', '')}",
            "",
            "---",
            "## 📜 角色",
        ]
        for c in d.get("characters", []):
            lines += [
                f"### {c['id']} — {c.get('name', '')} ({c.get('role', '')})",
                f"- 性别: {c.get('gender', '')} | 年龄: {c.get('age_range', '')}",
                f"- 外貌: {c.get('appearance', '')}",
                f"- 服装: {c.get('clothing', '')}",
                f"- 特征: {c.get('distinctive_features', '')}",
                "",
            ]
        lines += ["---", "## 🏠 场景"]
        for s in d.get("scenes", []):
            lines += [
                f"### {s['id']} — {s.get('name', '')}",
                f"- 类型: {s.get('type', '')} | 时间: {s.get('time_of_day', '')}",
                f"- 光线: {s.get('lighting', '')}",
                f"- 描述: {s.get('description', '')}",
                f"- 氛围: {s.get('mood', '')}",
                "",
            ]
        lines += ["---", "## 📦 道具"]
        for p in d.get("props", []):
            lines.append(f"- **{p['id']}** — {p.get('name', '')}: {p.get('description', '')}")
        lines += ["", "---", "## 🎬 四幕剧本", ""]
        for ep in d.get("episodes", []):
            lines += [
                f"### 第 {ep.get('episode', '?')} 集 — {ep.get('act', '')}",
                f"**{ep.get('title', '')}**",
                "",
                ep.get("summary", ""),
                "",
                f"- 角色: {', '.join(ep.get('characters_in_scene', []))}",
                f"- 场景: {ep.get('scene_id', '')} | 道具: {', '.join(ep.get('key_props', []))}",
                f"- 情感: {ep.get('emotion', '')} | 氛围: {ep.get('visual_mood', '')}",
                "",
            ]
        return "\n".join(lines)

    def _fmt_asset_md(self, a: dict, title: str) -> str:
        lines = [
            f"# {title} — 素材清单",
            "",
            "## 👤 角色素材",
            "",
            "| ID | 名称 | 构图 | 用途 | 出图提示词 |",
            "|----|------|------|------|-----------|",
        ]
        for ca in a.get("character_assets", []):
            prompt = ca.get("prompt", "")
            lines.append(
                f"| {ca.get('character_id', '')} | {ca.get('name', '')} | "
                f"{ca.get('view_label', '')} | {ca.get('purpose', '')} | "
                f"{prompt[:100]}{'...' if len(prompt) > 100 else ''} |")
        lines += ["", "---", "", "## 🏠 场景素材", "",
                  "| ID | 名称 | 用途 | 出图提示词 |",
                  "|----|------|------|-----------|"]
        for sa in a.get("scene_assets", []):
            prompt = sa.get("prompt", "")
            lines.append(
                f"| {sa.get('scene_id', '')} | {sa.get('name', '')} | "
                f"{sa.get('purpose', '')} | "
                f"{prompt[:120]}{'...' if len(prompt) > 120 else ''} |")
        lines += ["", "---", "", "## 📦 道具素材", "",
                  "| ID | 名称 | 用途 | 出图提示词 |",
                  "|----|------|------|-----------|"]
        for pa in a.get("prop_assets", []):
            prompt = pa.get("prompt", "")
            lines.append(
                f"| {pa.get('prop_id', '')} | {pa.get('name', '')} | "
                f"{pa.get('purpose', '')} | "
                f"{prompt[:120]}{'...' if len(prompt) > 120 else ''} |")
        return "\n".join(lines)

    def _fmt_storyboard_md(self, sb: dict, ep: dict) -> str:
        lines = [
            f"# 第 {sb.get('episode', '?')} 集: {sb.get('title', '')}",
            f"时长: {sb.get('duration_seconds', '?')}s | 画幅: {sb.get('aspect_ratio', '16:9')}",
            "",
            "## 素材槽位",
            "",
            "| 槽位 | 资产 | 用途 |",
            "|------|------|------|",
        ]
        for s in sb.get("asset_slots", []):
            lines.append(f"| {s.get('slot', '')} | {s.get('asset_id', '')} | {s.get('purpose', '')} |")
        lines += ["", "## 分镜时间轴", ""]
        for s in sb.get("shots", []):
            lines += [
                f"**{s.get('time_range', '')}** {s.get('shot_type', '')} · {s.get('camera_movement', '')}",
                f"- 画面: {s.get('visual_content', '')}",
                f"- 动作: {s.get('subject_action', '')}",
                f"- 光影: {s.get('lighting_and_atmosphere', '')}",
                f"- 参考: {', '.join(s.get('video_references', []))}",
                "",
            ]
        audio = sb.get("audio", {})
        lines += ["## 🔊 音频设计", "",
                  f"- BGM: {audio.get('bgm', '')}",
                  f"- SFX: {audio.get('sfx', '')}"]
        if audio.get("dialogue"):
            lines.append(f"- 对白: {audio['dialogue']}")
        lines += ["", "## 🔗 尾帧", "", sb.get("end_frame", ""),
                  "", "## 📋 Seedance 2.0 完整提示词", "",
                  "```", sb.get("seedance_full_prompt", ""), "```", ""]
        return "\n".join(lines)

    def _fmt_guide(self, script: dict) -> str:
        title = script.get("title", "未命名")
        return f"""# {title} — 使用指南

## 如何使用这些文件

### 1. 素材图 (素材/ 目录)
将角色图(C##)、场景图(S##)、道具图(P##)上传到 Seedance 2.0 或同类 AI 视频工具作为参考。

### 2. 分镜脚本 (_分镜.md 文件)
每个分镜文件包含完整的 Seedance 2.0 提示词，直接复制 `seedance_full_prompt` 粘贴到 Seedance 2.0 即可生成视频。

### 3. 集间衔接
第 2 集起，使用 Seedance 2.0 的"视频延长"功能：
- 上传上一集的视频作为 @视频1 参考
- 上传上一集的尾帧截图作为参考
- 粘贴当前集的 seedance_full_prompt
- 选择"延长15s"

### 4. 素材槽位分配
每个分镜脚本的素材槽位表已标明每张参考图的 @图片 编号，
按照表格上传对应的 C##/S##/P## 素材图即可。

---

*由 Noova 分镜脚本生成器自动生成 · {datetime.now().strftime('%Y-%m-%d %H:%M')}*
"""
