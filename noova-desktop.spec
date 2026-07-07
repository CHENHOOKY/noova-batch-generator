# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — Noova AI 批量出图助手"""

import os
import sys
from pathlib import Path

# 项目根目录（PyInstaller 会将工作目录设为 spec 所在目录）
_ROOT = Path('.').resolve()

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        # 插件目录（importlib 动态加载，必须显式包含）
        ('plugins', 'plugins'),
        # 插件基类（单文件）
        ('plugin_base.py', '.'),
        # ppt-master（PPT 大师插件）
        ('ppt-master', 'ppt-master'),
        # 模型文件（超分插件）
        ('models', 'models'),
        # kart-io 绘本引擎（importlib 动态加载）
        ('kart-io-picture-book-wizard', 'kart-io-picture-book-wizard'),
        # 窗口图标（运行时读取）
        ('logo.ico', '.'),
        # 设置模块
        ('config', 'config'),
    ],
    hiddenimports=[
        # 插件模块（动态 import，PyInstaller 无法自动发现）
        'plugins',
        'plugins.__init__',
        'plugins.batch_draw',
        'plugins.folder_batch_draw',
        'plugins.upscale',
        'plugins.ppt_master',
        'plugins.ppt_master.config',
        'plugins.ppt_master.api_client',
        'plugins.ppt_master.prompts',
        'plugins.ppt_master.parsers',
        'plugins.ppt_master.style_extractor',
        'plugins.ppt_master.widgets',
        'plugins.ppt_master.worker',
        'plugins.ppt_master.plugin',
        'plugins.picture_book',
        'plugins.storyboard_generator',
        'plugins.storyboard_generator.config',
        'plugins.storyboard_generator.worker',
        'plugins.storyboard_generator.widgets',
        'plugins.storyboard_generator.plugin',
        'plugins.storyboard_generator.api_client',
        'plugins.storyboard_generator.prompts',
        'plugins.storyboard_generator.asset_manager',
        'plugins.ecommerce_planner',
        'plugins.ecommerce_planner.config',
        'plugins.ecommerce_planner.prompts',
        'plugins.ecommerce_planner.worker',
        'plugins.ecommerce_planner.plugin',
        'plugins.user_manual',
        'plugins.user_manual.htmlkit',
        'plugins.user_manual.content',
        'plugins.user_manual.plugin',
        # 插件依赖的三方库
        'pandas',
        'PIL',
        'cv2',
        'openpyxl',
        # ppt-master (PPT 大师插件)
        'pptx',
        'svglib',
        'reportlab',
        # ppt-master 脚本模块（动态 import）
        'svg_to_pptx',
        'svg_to_pptx.__init__',
        'svg_to_pptx.drawingml_context',
        'svg_to_pptx.drawingml_converter',
        'svg_to_pptx.drawingml_elements',
        'svg_to_pptx.drawingml_paths',
        'svg_to_pptx.drawingml_styles',
        'svg_to_pptx.drawingml_utils',
        'svg_to_pptx.pptx_builder',
        'svg_to_pptx.pptx_cli',
        'svg_to_pptx.pptx_dimensions',
        'svg_to_pptx.pptx_discovery',
        'svg_to_pptx.pptx_media',
        'svg_to_pptx.pptx_narration',
        'svg_to_pptx.pptx_notes',
        'svg_to_pptx.pptx_slide_xml',
        'svg_to_pptx.tspan_flattener',
        'svg_to_pptx.use_expander',
        'svg_finalize',
        'svg_finalize.__init__',
        'svg_finalize.align_embed_images',
        'svg_finalize.crop_images',
        'svg_finalize.embed_icons',
        'svg_finalize.embed_images',
        'svg_finalize.fix_image_aspect',
        'svg_finalize.flatten_tspan',
        'svg_finalize.svg_rect_to_path',
        # 内部工具模块（下划线前缀，PyInstaller 可能遗漏）
        'plugins._noova_api',
        'plugins._text_api',
        'plugins._utils',
        'plugins._design',
        # 设置模块
        'config',
        'config.settings_manager',
        'config.settings_dialog',
        # upscale 插件依赖
        'numpy',
        'onnxruntime',
        # main.py 使用 pkgutil.iter_modules 动态发现插件
        'pkgutil',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'scipy',
        'sqlalchemy',
        'jedi',
        'ipython',
    ],
    no_warn=False,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Noova-Desktop',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(_ROOT / 'logo.ico'),
)
