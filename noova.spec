# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — Noova AI 批量出图助手"""

import sys
from pathlib import Path

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        # 插件目录（importlib 动态加载，必须显式包含）
        ('plugins', 'plugins'),
    ],
    hiddenimports=[
        # 插件模块（动态 import，PyInstaller 无法自动发现）
        'plugins',
        'plugins.__init__',
        'plugins.batch_draw',
        'plugins.folder_batch_draw',
        'plugins.upscale',
        # 插件依赖的三方库
        'pandas',
        'PIL',
        'cv2',
        'openpyxl',
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
    name='Noova_AI_Batch',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # GUI 应用，不显示命令行窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,              # 暂无图标文件
)
