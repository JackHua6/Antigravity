@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ==================================================
echo   AI Token 工作台看板 · 本地扫描与刷新工具
echo ==================================================
echo.

set "PY_CMD="
where python >nul 2>&1
if not errorlevel 1 (
    python -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1
    if not errorlevel 1 set "PY_CMD=python"
)

if not defined PY_CMD (
    where py >nul 2>&1
    if not errorlevel 1 (
        py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1
        if not errorlevel 1 set "PY_CMD=py -3"
    )
)

if not defined PY_CMD (
    echo [错误] 未检测到可用的 Python 3.9+ 运行环境。
    echo 请先前往 https://www.python.org/downloads/ 安装 Python 3（勾选 Add Python to PATH）后重试。
    echo.
    pause
    exit /b 1
)

%PY_CMD% -B -X utf8 "%~dp0refresh_dashboard.py" --no-open
if errorlevel 1 (
    echo.
    echo [提示] 如遇缺依赖或路径报错，可将本目录 README.md 交给你的 AI 助手一键排查。
    pause
    exit /b 1
)

echo.
echo 刷新完成，正在打开看板...
start "" "%~dp0token_dashboard.html"
exit /b 0
