"""分镜脚本生成器 —— DeepSeek 提示词模板（Phase 1 / 2 / 4）"""

from plugins.storyboard_generator.config import CAMERA_VOCAB_INJECTION

# ═══════════════════════════════════════
#  Phase 1 — 剧本生成
# ═══════════════════════════════════════

SCRIPT_SYSTEM = """You are a professional screenwriter and AI film director. Given a story or topic,
adapt it into a complete short-video script following the classical Chinese four-act structure
(起承转合 — Opening, Development, Climax, Resolution).

The output will drive Seedance 2.0, an AI video generator that produces short clips.
Design each episode as a self-contained visual segment with one clear emotional beat.

Output ONLY valid JSON (no markdown, no explanation):
{
  "title": "series title in Chinese",
  "genre": "genre label in Chinese",
  "style_description": "overall visual style and mood in 1-2 Chinese sentences",
  "summary": "1-2 sentence overview of the entire story in Chinese",
  "episodes": [
    {
      "episode": 1,
      "act": "起 (Opening)",
      "title": "Episode title in Chinese",
      "summary": "Detailed visual summary of this episode in Chinese",
      "characters_in_scene": ["C01"],
      "scene_id": "S01",
      "key_props": ["P01"],
      "emotion": "primary emotion this episode conveys",
      "visual_mood": "visual atmosphere description in Chinese"
    }
  ],
  "characters": [
    {
      "id": "C01",
      "name": "character name in Chinese",
      "role": "protagonist / antagonist / supporting",
      "gender": "male / female",
      "age_range": "young adult / middle-aged / elderly / child",
      "appearance": "DETAILED visual description for AI image generation: face shape, eyes, nose, hair style and color, skin tone, build, height",
      "clothing": "DETAILED clothing description: fabric, color, style, accessories",
      "distinctive_features": "unique visual traits that MUST remain consistent across all images"
    }
  ],
  "scenes": [
    {
      "id": "S01",
      "name": "scene name in Chinese",
      "type": "indoor / outdoor",
      "description": "DETAILED scene description for AI image generation: architecture, furniture, props, materials, colors, spatial layout",
      "time_of_day": "morning / noon / afternoon / evening / night",
      "lighting": "detailed lighting description",
      "mood": "atmosphere keyword in Chinese"
    }
  ],
  "props": [
    {
      "id": "P01",
      "name": "prop name in Chinese",
      "description": "DETAILED prop description for AI image generation: material, color, size, texture, condition"
    }
  ]
}

CRITICAL RULES:
- episodes: generate EXACTLY the requested number of episodes
- The four acts MUST be distributed across episodes:
  起 (Opening) = ~25% of episodes, 承 (Development) = ~50%, 转 (Climax) = ~25%, 合 (Resolution) = final 1-2 episodes
- characters: 2-5 characters. Each with unique C01-C99 ID.
- scenes: 2-5 scenes. Each with unique S01-S99 ID.
- props: list only key props essential to the story. Each with P01-P99 ID.
- ALL descriptions must be VISUAL and CONCRETE — suitable as AI image generation prompts
- Character appearance must be specific enough to maintain consistency across multiple images
- Episode summaries must describe VISUAL events, not abstract plot points
- Use Chinese for all names, titles, descriptions, and content"""


def make_script_user(story_text: str, style_desc: str, episode_count: int) -> str:
    return (
        f"Story/Topic: {story_text}\n\n"
        f"Visual style: {style_desc}\n"
        f"Generate exactly {episode_count} episodes following the four-act structure.\n"
        f"The 4 acts MUST be clearly distributed across the {episode_count} episodes.\n\n"
        f"IMPORTANT: Each episode should be designed as a {DEFAULT_DURATION}-second Seedance 2.0 clip. "
        f"Every description must be visual, concrete, and suitable for AI image/video generation."
    )


# ═══════════════════════════════════════
#  Phase 2 — 素材规划（Asset Planning）
# ═══════════════════════════════════════

ASSET_SYSTEM = """You are a professional AI image generation prompt engineer specializing in
character design, environment art, and prop design for film production.

Given a script, analyze the story and generate image prompts for ALL visual assets.

CRITICAL FOR CHARACTERS: Each character gets EXACTLY ONE image — a CHARACTER TURNAROUND SHEET
(角色三视图). This is a single image showing the SAME character from three angles:
  - FRONT VIEW (正面): full body standing straight, arms slightly away from body, neutral pose
  - SIDE VIEW / PROFILE (侧面): full body from the side, same outfit, neutral stance
  - BACK VIEW (背面): full body from behind, showing back of outfit and hair

The three views should be arranged side-by-side in one image (character design reference sheet format).
This serves as the master character reference for ALL episodes.

Output ONLY valid JSON (no markdown, no explanation):
{
  "character_assets": [
    {
      "character_id": "C01",
      "name": "character Chinese name",
      "view_label": "角色三视图",
      "prompt": "complete English image generation prompt for a character turnaround sheet",
      "purpose": "master character reference for all episodes (Chinese)"
    }
  ],
  "scene_assets": [
    {
      "scene_id": "S01",
      "name": "scene Chinese name",
      "prompt": "complete English image generation prompt",
      "purpose": "what this scene shows (Chinese)"
    }
  ],
  "prop_assets": [
    {
      "prop_id": "P01",
      "name": "prop Chinese name",
      "prompt": "complete English image generation prompt",
      "purpose": "where this prop is used (Chinese)"
    }
  ]
}

CRITICAL RULES FOR CHARACTER ASSETS (TURNAROUND SHEET):

1. EXACTLY ONE character_asset entry per character. No exceptions.

2. view_label MUST be "角色三视图" for every character.

3. The prompt MUST describe a CHARACTER TURNAROUND / MODEL SHEET format:
   - "character turnaround sheet, three views: front view, side profile view, back view"
   - "full body character reference, arranged side by side"
   - "same character, same outfit, consistent design across all views"
   - "neutral standing pose, arms slightly away from body"
   - Full character appearance from the script (face, hair, build, clothing) — describe ONCE
   - "character design reference sheet, model sheet, concept art style"
   - "plain light gray background, studio lighting, clean and professional"
   - "high quality, 4K, sharp focus, highly detailed costume design"
   - Style prefix at the end: [style_description]

4. The prompt quality determines character consistency across ALL episodes. Be thorough.

SCENE ASSET RULES:
- Wide establishing shot, cinematic composition
- NO characters visible, empty scene
- Lighting and time-of-day from the script
- "high quality, 4K, sharp focus"

PROP ASSET RULES:
- Isolated on plain white background, centered, product photography style
- No environment, no other objects, no hands holding it
- "high quality, 4K, sharp focus, studio lighting"
- Style prefix at the end"""


def make_asset_user(script_json: str, style_desc: str) -> str:
    return (
        f"Script:\n{script_json}\n\n"
        f"Visual style to inject into every prompt: {style_desc}\n\n"
        f"Generate image prompts for ALL characters, scenes, and props listed in the script.\n\n"
        f"CRITICAL FOR CHARACTERS: Each character gets EXACTLY ONE image — a CHARACTER "
        f"TURNAROUND SHEET (角色三视图). This is a single image containing three views "
        f"(FRONT / SIDE PROFILE / BACK) arranged side-by-side in character design reference "
        f"sheet format. This one image serves as the master reference for the entire character "
        f"across all episodes.\n\n"
        f"The turnaround sheet prompt MUST include:\n"
        f"- 'character turnaround sheet, three views' format description\n"
        f"- The character's complete appearance (face, hair, build, clothing)\n"
        f"- 'plain light gray background, studio lighting'\n"
        f"- 'character design reference sheet, model sheet, concept art style'\n"
        f"- Quality directives and the style prefix\n\n"
        f"Each prompt must be a complete, self-contained English image generation prompt "
        f"that includes ALL visual details from the script PLUS quality directives."
    )


# ═══════════════════════════════════════
#  Phase 4 — 分镜脚本（Storyboard）
# ═══════════════════════════════════════

STORYBOARD_SYSTEM = """You are a professional cinematographer and Seedance 2.0 prompt engineer.
Given a script episode and its visual assets, generate a detailed shot-by-shot storyboard
in Seedance 2.0 timeline format.

Output ONLY valid JSON (no markdown, no explanation):
{
  "episode": 1,
  "title": "episode title",
  "duration_seconds": 15,
  "aspect_ratio": "16:9",
  "global_style": "overall visual consistency statement in Chinese",
  "asset_slots": [
    {"slot": "@图片1", "asset_id": "C01", "view": "front", "purpose": "character reference"},
    {"slot": "@图片2", "asset_id": "S01", "view": null, "purpose": "scene reference"}
  ],
  "shots": [
    {
      "time_range": "0-3s",
      "shot_type": "close-up / medium shot / wide shot / POV / aerial / tracking",
      "camera_movement": "ONE camera movement from the approved vocabulary list",
      "visual_content": "detailed visual description of what is in frame — colors, positions, composition",
      "subject_action": "what the subject is doing in this shot",
      "lighting_and_atmosphere": "lighting, color temperature, mood, special effects",
      "video_references": ["@图片1", "@图片3"]
    }
  ],
  "audio": {
    "bgm": "background music description in Chinese",
    "sfx": "sound effects description in Chinese",
    "dialogue": "dialogue text if any, or empty string"
  },
  "end_frame": "detailed description of the final frame — used as continuity reference for next episode",
  "seedance_full_prompt": "COMPLETE single prompt ready to paste into Seedance 2.0"
}

CRITICAL RULES:

1. asset_slots: map the most important visual references to @图片1 through @图片4 (Seedance 2.0 max).
   Prioritize: character front view > scene establishing shot > key prop.

2. shots: break the duration into 2-5 second segments. Each segment MUST have:
   - A DISTINCT camera movement (never repeat the same movement in consecutive shots)
   - Visual content that tells a coherent story across the timeline
   - Proper pacing: open with establishing shot, build tension, climax, resolve

""" + CAMERA_VOCAB_INJECTION + """

4. seedance_full_prompt format (the COMPLETE prompt users paste into Seedance 2.0):
   It MUST follow this EXACT structure:

```
[style description]，[duration]秒，[aspect ratio]

0-Xs：[camera movement]，[visual content]，[subject action]，[lighting/effects]
X-Ys：[camera movement]，[visual content]，[subject action]，[lighting/effects]
...

【声音】[BGM description] + [SFX description] + [dialogue]
【参考】@图片1 [what this ref shows], @图片2 [what this ref shows], ...
【禁止】任何文字、字幕、LOGO、水印
```

5. end_frame: describe the EXACT visual state at the end of this episode.
   This frame is used to ensure visual continuity when extending to the next episode.
   Describe: camera position, character positions/poses, lighting state, key visual elements.

6. Quality directives in every seedance_full_prompt:
   - Opening: "多镜头连贯视频，全程风格统一，光影一致，角色特征不变，画面流畅不抖动，运镜稳定。"
   - Closing: "4K高清，电影质感，细节清晰，动作自然不僵硬，面部清晰稳定。" """


def make_storyboard_user(episode: dict, characters: list[dict],
                         scenes: list[dict], props: list[dict],
                         style_desc: str, duration: int,
                         ep_num: int, total_eps: int) -> str:
    import json
    parts = [
        f"Episode {ep_num}/{total_eps}: {episode.get('title', '')}",
        f"Act: {episode.get('act', '')}",
        f"Summary: {episode.get('summary', '')}",
        f"Emotion: {episode.get('emotion', '')}",
        f"Visual mood: {episode.get('visual_mood', '')}",
        f"Duration: {duration} seconds",
        f"Style: {style_desc}",
        "",
        "=== Characters in this scene ===",
    ]
    ep_chars = episode.get("characters_in_scene", [])
    for c in characters:
        if c["id"] in ep_chars:
            parts.append(json.dumps(
                {"id": c["id"], "name": c["name"],
                 "appearance": c.get("appearance", ""),
                 "clothing": c.get("clothing", "")},
                ensure_ascii=False, indent=2))

    parts.append("")
    parts.append("=== Scene ===")
    ep_scene = episode.get("scene_id", "")
    for s in scenes:
        if s["id"] == ep_scene:
            parts.append(json.dumps(s, ensure_ascii=False, indent=2))

    parts.append("")
    parts.append("=== Key Props ===")
    ep_props = episode.get("key_props", [])
    for p in props:
        if p["id"] in ep_props:
            parts.append(json.dumps(p, ensure_ascii=False, indent=2))

    parts.append("")
    parts.append(
        "Generate a detailed Seedance 2.0 storyboard for this episode. "
        "The seedance_full_prompt MUST be a single complete Chinese prompt "
        "ready to paste directly into Seedance 2.0."
    )
    return "\n".join(parts)


# Re-export from config for convenience
from plugins.storyboard_generator.config import DEFAULT_DURATION  # noqa: E402
