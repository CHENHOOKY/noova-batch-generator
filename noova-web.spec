# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — Noova Web 版（pywebview + FastAPI + Vue 前端）"""
import os
from pathlib import Path

_ROOT = Path('.').resolve()

a = Analysis(
    ['launcher.py'],
    pathex=[str(_ROOT)],
    binaries=[],
    datas=[
        ('plugins', 'plugins'),
        ('plugin_base.py', '.'),
        ('ppt-master', 'ppt-master'),
        ('models', 'models'),
        ('kart-io-picture-book-wizard', 'kart-io-picture-book-wizard'),
        ('config', 'config'),
        ('server', 'server'),
        ('core', 'core'),
        ('web/dist', 'web/dist'),
        ('logo.ico', '.'),
    ],
    hiddenimports=[
        # server & core
        'server', 'server.app', 'server.dialogs', 'server.registry', 'server.task_manager',
        'core', 'core.upscale_service', 'core.qt_worker_runner',
        # config
        'config', 'config.settings_manager',
        'plugin_base',
        # 插件（动态 import）
        'plugins', 'plugins.batch_draw', 'plugins.folder_batch_draw', 'plugins.upscale',
        'plugins.picture_book',
        'plugins.ppt_master', 'plugins.ppt_master.config', 'plugins.ppt_master.api_client',
        'plugins.ppt_master.prompts', 'plugins.ppt_master.parsers', 'plugins.ppt_master.style_extractor',
        'plugins.ppt_master.widgets', 'plugins.ppt_master.worker', 'plugins.ppt_master.plugin',
        'plugins.storyboard_generator', 'plugins.storyboard_generator.config',
        'plugins.storyboard_generator.worker', 'plugins.storyboard_generator.widgets',
        'plugins.storyboard_generator.plugin', 'plugins.storyboard_generator.api_client',
        'plugins.storyboard_generator.prompts', 'plugins.storyboard_generator.asset_manager',
        'plugins.ecommerce_planner', 'plugins.ecommerce_planner.config',
        'plugins.ecommerce_planner.prompts', 'plugins.ecommerce_planner.worker',
        'plugins.ecommerce_planner.plugin',
        'plugins.user_manual', 'plugins.user_manual.htmlkit',
        'plugins.user_manual.content', 'plugins.user_manual.plugin',
        'plugins._noova_api', 'plugins._text_api', 'plugins._utils', 'plugins._design',
        # 插件依赖
        'pandas', 'PIL', 'cv2', 'openpyxl', 'pptx', 'svglib', 'reportlab', 'numpy', 'onnxruntime',
        # Web 后端依赖
        'fastapi', 'starlette', 'pydantic', 'pydantic_core',
        'uvicorn', 'uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.auto',
        'uvicorn.protocols', 'uvicorn.protocols.http.auto', 'uvicorn.protocols.websockets.auto',
        'uvicorn.protocols.websockets.websockets_impl', 'uvicorn.lifespan', 'uvicorn.lifespan.on',
        'websockets',
        # tkinter（Web 版用原生文件对话框，必须保留）
        'tkinter', 'tkinter.filedialog',
        'pkgutil',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib', 'scipy', 'sqlalchemy', 'jedi', 'ipython',
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
    name='Noova',
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
