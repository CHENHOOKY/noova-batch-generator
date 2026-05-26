@echo off
chcp 65001 >nul
echo ╔══════════════════════════════════════════════╗
echo ║     Noova AI — PyInstaller 一键打包         ║
echo ╚══════════════════════════════════════════════╝
echo.

cd /d "%~dp0"

echo [1/3] 清理旧构建...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

echo [2/3] 检查依赖...
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo [WARN] PyInstaller 未安装，正在安装...
    pip install pyinstaller
)

echo [3/3] 开始打包...
pyinstaller --clean --noconfirm noova.spec

echo.
if exist "dist\Noova.exe" (
    echo [DONE] 打包成功！
    echo 输出路径: dist\Noova.exe
) else (
    echo [FAIL] 打包失败，请检查上方错误信息。
)

pause
