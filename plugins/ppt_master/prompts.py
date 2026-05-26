"""PPT 大师 —— Prompt 模板与格式化函数"""

import json
import os

from plugins.ppt_master.config import _SHARED_STANDARDS_CACHE

# ═══════════════════════════════════════
#  大纲生成 Prompt
# ═══════════════════════════════════════

OUTLINE_SYSTEM = """You are a professional presentation strategist. Given a user's topic,
generate a structured PPT outline in JSON format.

Output ONLY valid JSON (no markdown, no explanation):
{{
  "title": "presentation title",
  "subtitle": "optional subtitle for cover",
  "slides": [
    {{
      "type": "cover",
      "title": "Slide Title",
      "subtitle": "Subtitle or presenter name",
      "content": ["key point 1", "key point 2"],
      "notes": "speaker notes"
    }},
    {{
      "type": "content",
      "title": "Section Title",
      "content": ["bullet 1", "bullet 2", "bullet 3"],
      "notes": "speaker notes"
    }},
    {{
      "type": "ending",
      "title": "Thank You",
      "content": ["contact info", "Q&A"],
      "notes": ""
    }}
  ]
}}

Rules:
- First slide must be type "cover", last slide type "ending"
- content array: 3-5 items per slide, concise (each 5-15 words)
- Use the user's language (Chinese for Chinese topics, English for English topics)
- If a specific slide count is given, match it. If the user asks for "auto" or does not specify, determine the appropriate number based solely on content depth and complexity.
- If reference materials contain "=== Sheet:" headers, extract and use data from ALL sheets, not just the first one
{style_section}"""


def make_outline_user(topic: str, design_label: str, industry_label: str,
                      layout_label: str, custom_style: str,
                      page_count: int, files_text: str = "") -> str:
    parts = [
        f"Topic: {topic}",
        f"Design scheme: {design_label}",
    ]
    if industry_label and industry_label != "None":
        parts.append(f"Industry: {industry_label}")
    if layout_label and layout_label != "（默认布局）":
        parts.append(f"Layout reference: {layout_label}")
    if custom_style:
        parts.append(f"Custom style notes: {custom_style}")
    if page_count > 0:
        parts.append(f"Requested slides: {page_count}")
    else:
        parts.append(
            "Slides: auto — determine the appropriate number based on "
            "content depth and complexity. Be flexible.")
    p = "\n".join(parts) + "\n"
    if files_text:
        p += f"\nReference materials:\n{files_text[:2000000]}\n"
    p += "\nPlease generate the outline now."
    return p


def format_palette(scheme: dict, industry: dict | None) -> str:
    """将配色方案格式化为 prompt 中的色彩规范"""
    lines = []
    if scheme:
        lines.append(f"Primary: {scheme.get('primary', '#333')}")
        lines.append(f"Secondary: {scheme.get('secondary', '#666')}")
        lines.append(f"Accent: {scheme.get('accent', '#F5A623')}")
        lines.append(f"Background: {scheme.get('bg', '#FFFFFF')}")
        lines.append(f"Background alt: {scheme.get('bg_alt', '#F8F9FA')}")
        lines.append(f"Text dark: {scheme.get('text_dark', '#1A1A1A')}")
        lines.append(f"Text muted: {scheme.get('text_muted', '#888888')}")
        if scheme.get("text_light"):
            lines.append(f"Text light: {scheme['text_light']}")
    if industry and industry.get("primary"):
        lines.append(f"Industry primary: {industry['primary']}")
        lines.append(f"Industry secondary: {industry['secondary']}")
        lines.append(f"Industry accent: {industry['accent']}")
    return "\n".join(f"  - {line}" for line in lines) if lines else ""


# ═══════════════════════════════════════
#  SVG 生成 Prompt
# ═══════════════════════════════════════

SVG_SYSTEM = """You are a world-class presentation SVG designer. Generate ONE slide as
pure SVG code for a professional presentation.

{spec_lock_injection}

DESIGN CONTEXT:
- Slide type: {slide_type}
- Design scheme: {design_scheme}
- Industry: {industry}
- Layout reference: {layout_template}
- Custom style notes: {custom_style}
- Page rhythm: {page_rhythm_directive}
{layout_examples}

COLOR PALETTE (use these exact colors — DO NOT introduce new colors):
{palette}

TECHNICAL REQUIREMENTS:
1. viewBox="{viewbox}" — NO XML declaration, NO <!DOCTYPE, NO HTML wrapper
2. Output ONLY a ```svg code block, nothing else before or after
3. Background: use a <rect> covering the full viewBox with bg color
4. Fonts: every font-family stack MUST end with a Windows pre-installed font
   (Microsoft YaHei, SimSun, Arial, Times New Roman, Consolas). Lead with
   the spec's font families, add fallbacks.
5. Use clean geometric shapes, lines, and proper text hierarchy
6. Semantic <g> groups: 3-8 top-level <g id="..."> groups per slide.
   Wrap logically related elements (card, list item, icon+text, header, footer).
   Chrome groups (id tokens: bg, header, footer, decoration, page-number, nav, logo)
   are auto-skipped by animation — use these naming conventions.
7. Page numbers in footer (except cover): "PAGE {page_num} / {total_pages}"
8. Footer must include a thin rule line and right-aligned page number
9. Cover slides: bold, dramatic, big title, NO footer. Anchor rhythm.
10. Use font-weight explicitly (bold=700, black=900). No fake weights.
11. ALL text properly aligned (text-anchor where needed)
12. Icons: use `<use data-icon="<library>/<name>" x="..." y="..."
    width="48" height="48" fill="#HEX"/>` format (ONLY for icons listed in inventory)
13. Images (if spec allows): `<image href="../images/file.png"
    preserveAspectRatio="xMidYMid slice" .../>` with optional clipPath for crops

BANNED FEATURES (SVG will be invalid if used):
- NO <style>, class, <foreignObject>, textPath, @font-face
- NO <animate*>, <script>, <iframe>, <symbol>+<use> (except data-icon)
- NO mask on non-image elements
- NO rgba() — use fill="#HEX" fill-opacity="N"
- NO <g opacity="..."> — set fill-opacity/stroke-opacity on each child
- NO <image opacity="..."> — use overlay rect for image opacity
- NO HTML named entities (&nbsp;, &mdash;, &copy;, &hellip;, &bull;) —
  write raw Unicode characters (—, ©, →, ·, NBSP)
- clipPath ONLY on <image> elements, not shapes

SHADOW RESTRAINT:
- Max 2-3 shadowed elements per page
- Single light source per page (all shadows share same dx/dy direction)
- Two-tier elevation only: resting (flood-opacity 0.06-0.10, dy=2-4) and
  raised (flood-opacity 0.12-0.20, dy=6-10). NEVER exceed 0.20
- Shadow only on floating elements over photo/colored panels, NOT on
  background panels, dividers, peer-grid cards, or body-text containers
- For shadows use filter with feGaussianBlur + feOffset + feFlood pattern

TEXT STYLING RULES:
- Single logical line = single <text> with inline <tspan> children.
  NEVER use multiple adjacent <text> elements for one visual line.
- Wrap key data (percentages, multipliers, amounts, load-bearing nouns)
  in `<tspan fill="accent-color" font-weight="bold">...</tspan>`
- Inline tspans must NOT carry x/y/dy (those start new lines). dx is safe.
- For multi-line text: one <text> with per-line <tspan x="..." dy="...">
- Columns = separate <text> elements (two-column layout = two <text>)

PAGE RHYTHM DIRECTIVE:
{runtime_rhythm}

Keep shapes elegant but deliberate — rects, lines, circles with proper
stroke widths, rounded corners where appropriate. Think like a designer."""


STRATEGIST_SYSTEM = """You are a world-class presentation design strategist. Your job is to
analyze a PPT outline and produce a comprehensive design specification and execution lock.

You will receive:
- A confirmed PPT outline (JSON with title, slides, content)
- Design context (style notes, canvas format, reference materials)

INSTRUCTIONS:
1. Analyze the outline deeply — identify content patterns, data density per slide,
   narrative flow, and audience type
2. Produce TWO sections in the exact format below

---SECTION: design_spec.md---
(A complete design narrative in markdown covering these areas:
## I. Project Info — title, canvas, page count, style direction
## II. Canvas — viewBox, format, margins
## III. Visual Theme — color scheme with HEX values, 60-30-10 rule, light/dark mode,
     style objective in 1-2 sentences
## IV. Typography — font stacks per role (title/body/emphasis/code),
     every stack MUST end with a pre-installed font (Microsoft YaHei / SimSun / Arial /
     Times New Roman / Consolas). Body baseline px. Size ramp table.
## V. Layout Principles — page structure zones, rhythm approach
## VI. Icon Spec — chosen library (exactly one of: chunk-filled / tabler-filled /
     tabler-outline / phosphor-duotone), inventory of 6-15 icon names needed across the deck
## VII. Visualization Reference — per-page chart template assignments (if any)
## VIII. Image Resource List — placeholder `<image>` usage strategy (if any)
## IX. Content Outline — the confirmed outline with per-page layout notes
## X. Speaker Notes — style and structure
## XI. Tech Constraints — SVG compatibility and PPT export rules)

---SECTION: spec_lock.md---
(Machine-readable execution contract. Format EXACTLY as:

## canvas
- viewBox: <value>
- format: <value>

## colors
- bg: #HEX
- primary: #HEX
- accent: #HEX
- secondary_accent: #HEX (if needed)
- text: #HEX
- text_secondary: #HEX
- border: #HEX (if needed)

## typography
- font_family: "<Font>", <fallback>, sans-serif
- title_family: "<Font>", <fallback>, sans-serif
- body_family: "<Font>", "<Font>", <fallback>, sans-serif
- emphasis_family: "<Font>", <fallback>, serif
- code_family: "<Font>", "<Font>", monospace
- body: <N>px
- title: <N>px
- subtitle: <N>px
- annotation: <N>px

## icons
- library: <chunk-filled|tabler-filled|tabler-outline|phosphor-duotone>
- stroke_width: <1.5|2|3>  (ONLY for tabler-outline; omit otherwise)
- inventory: <icon1>, <icon2>, ..., <iconN>

## page_rhythm
- P01: <anchor|dense|breathing>
- P02: <anchor|dense|breathing>
... (one entry per slide, including cover and ending)

## page_charts
- P<NN>: <chart_template_key>
... (only for slides that use a charts/ template; omit section if none)

## forbidden
- Mixing icon libraries
- rgba()
- <style>, class, <foreignObject>, textPath, @font-face, <animate*>,
  <script>, <iframe>, <symbol>+<use>
- <g opacity> (set opacity on each child individually)
- HTML named entities in text (&nbsp;, &mdash;, &copy;, etc.) — use raw Unicode
)

CRITICAL RULES:
- spec_lock.md MUST be parseable: every `## section` followed by `- key: value` lines
- Colors: exactly 4-6 hex values. Follow 60-30-10 rule. Text contrast ratio >= 4.5:1
- Typography: every font-family stack MUST end with a Windows pre-installed font
  (Microsoft YaHei / SimSun / Arial / Times New Roman / Consolas / SimHei / Georgia)
- Icons: pick exactly ONE stylistic library. Do NOT mix. Inventory lists icon names
  without library prefix.
- Page rhythm: assign EVERY slide one of {{anchor, dense, breathing}}:
  * anchor — cover, ending, chapter/section openers. Bold, dramatic. Follow template.
  * dense — data-heavy, multi-point, comparisons. Card grids, multi-column allowed.
  * breathing — single concept, hero quote, transition. NO multi-card grid layouts.
    Use whitespace, dividers, full-bleed imagery, single emphasis.
  * Rhythm follows narrative: breathing pages mark genuine pauses. Do not invent
    filler pages. A data report may be nearly all dense — that's fine.
- Chart matching (page_charts section): scan the outline for pages whose content
  shape matches a visualization type (bar chart, line chart, timeline, process flow,
  matrix/quadrant, funnel, etc.). Reference these common chart template keys:
  bar_chart, line_chart, pie_chart, donut_chart, timeline_horizontal, process_flow,
  vertical_pillars, quadrant_bubble_scatter, matrix_2x2, funnel_chart, sankey_chart,
  numbered_steps, hub_spokes, comparison_table, waterfall_chart, kpi_dashboard,
  chevron_chain, swot_quadrant, team_roster, agenda_list, roadmap_horizontal.
  Only assign a chart when the page's content genuinely matches. Leave non-data
  pages unassigned (they get free design).

SVG TECHNICAL STANDARDS (enforced in spec_lock forbidden section):
{banned_features}
{replacements}
{shadow_rules}
{text_rules}"""


_STRATEGIST_SYSTEM_CACHED = STRATEGIST_SYSTEM.format(
    banned_features=_SHARED_STANDARDS_CACHE.get("banned_features", ""),
    replacements=_SHARED_STANDARDS_CACHE.get("replacements", ""),
    shadow_rules=_SHARED_STANDARDS_CACHE.get("shadow_rules", "")[:3000],
    text_rules=_SHARED_STANDARDS_CACHE.get("text_rules", "")[:2000],
)


def make_svg_system(slide_type: str, scheme_label: str, industry_label: str,
                    layout_label: str, layout_key: str, custom_style: str,
                    scheme: dict, industry: dict | None,
                    viewbox: str, page_num: int, total_pages: int,
                    spec_lock: dict | None = None) -> str:
    from plugins.ppt_master.prompts import format_palette
    from plugins.ppt_master.style_extractor import load_layout_examples

    palette = format_palette(scheme, industry)
    examples = load_layout_examples(layout_key)

    spec_injection = ""
    page_rhythm_label = ""
    runtime_rhythm = ""

    if spec_lock:
        colors = spec_lock.get("colors", {})
        typo = spec_lock.get("typography", {})
        icons = spec_lock.get("icons", {})
        page_rhythm_map = spec_lock.get("page_rhythm", {})
        page_key = f"P{page_num:02d}"
        rhythm = page_rhythm_map.get(page_key, "dense")
        page_rhythm_label = f"{rhythm} (page {page_num}/{total_pages})"

        color_lines = [f"- {k}: {v}" for k, v in colors.items() if v and v != "#......"]
        font_lines = [f"- {k}: {v}" for k, v in typo.items() if v]
        icon_lib = icons.get("library", "")
        icon_inv = icons.get("inventory", [])
        icon_stroke = icons.get("stroke_width", "")

        spec_injection = f"""EXECUTION LOCK (READ BEFORE GENERATING):
Colors (do NOT deviate):
{chr(10).join(color_lines) if color_lines else '- Use the palette listed below'}

Typography:
{chr(10).join(font_lines) if font_lines else '- Use the fonts listed below'}

Icons: library={icon_lib}, inventory={icon_inv if icon_inv else 'use judgment'}
{f'Icons stroke-width: {icon_stroke}' if icon_stroke else ''}
"""

        rhythm_directives = {
            "anchor": ("This is an ANCHOR page (cover/ending/chapter). "
                       "Bold, dramatic layout. Follow the structural template. "
                       "Make a strong visual statement. Large typography, "
                       "generous spacing, single focal point."),
            "dense": ("This is a DENSE page (data/multi-point/comparison). "
                      "Card grids, multi-column layouts, and tables are ALLOWED. "
                      "Use cards, panels, or columns to organize information. "
                      "4-6 cards max. Keep each card focused with 1-3 data points."),
            "breathing": ("This is a BREATHING page (single concept/hero/transition). "
                          "NO multi-card grid layouts. Use generous whitespace, "
                          "dividers, a single emphasis element, or full-bleed imagery. "
                          "The page says ONE thing. Single rounded elements are fine. "
                          "Organize via naked text, rules, and negative space."),
        }
        runtime_rhythm = rhythm_directives.get(rhythm, rhythm_directives["dense"])
    else:
        runtime_rhythm = ("Free design — choose layout density based on content. "
                          "Cover/ending: bold and dramatic. Content: clear structure.")

    return SVG_SYSTEM.format(
        spec_lock_injection=spec_injection,
        slide_type=slide_type,
        design_scheme=scheme_label,
        industry=industry_label or "None",
        layout_template=layout_label or "Default",
        custom_style=custom_style or "None",
        page_rhythm_directive=page_rhythm_label,
        layout_examples=examples,
        palette=palette,
        viewbox=viewbox,
        page_num=page_num,
        total_pages=total_pages,
        runtime_rhythm=runtime_rhythm,
    )


def make_svg_user(slide_data: dict) -> str:
    """根据单页大纲数据构造 SVG 生成 prompt"""
    stype = slide_data.get("type", "content")
    title = slide_data.get("title", "")
    subtitle = slide_data.get("subtitle", "")
    content = slide_data.get("content", [])

    parts = [f"Generate a {stype} slide.", f"Title: {title}"]
    if subtitle and stype == "cover":
        parts.append(f"Subtitle: {subtitle}")
    if content:
        parts.append("Content:")
        for item in content:
            parts.append(f"  - {item}")
    if stype == "cover":
        parts.append("This is the COVER slide — make it bold and dramatic.")
    elif stype == "ending":
        parts.append("This is the ENDING slide — clean, memorable closing.")
    else:
        parts.append("This is a CONTENT slide — clear layout with bullet points.")
    return "\n".join(parts)


def make_strategist_user(outline: dict, canvas_key: str, page_count: int,
                         custom_style: str, files_text: str) -> str:
    """构造策略师阶段的用户提示"""
    slides = outline.get("slides", [])
    title = outline.get("title", "未命名")
    outline_text = json.dumps(outline, ensure_ascii=False, indent=2)

    parts = [
        f"PPT Title: {title}",
        f"Slide Count: {len(slides)}",
        f"Canvas: {canvas_key}",
    ]
    if custom_style:
        parts.append(f"Style Direction: {custom_style}")
    parts.append(f"\nFull Outline:\n```json\n{outline_text}\n```")

    if files_text:
        truncated = files_text[:500000]
        parts.append(f"\nReference Materials:\n{truncated}")

    parts.append(
        "\nBased on the outline above, generate the design specification "
        "and execution lock. Follow the STRATEGIST_SYSTEM instructions exactly. "
        "Output BOTH sections: design_spec.md and spec_lock.md."
    )
    return "\n".join(parts)
