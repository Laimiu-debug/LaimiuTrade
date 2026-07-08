@echo off
chcp 65001 >nul
title LaimiuTrade
cd /d "%~dp0"

if not exist backend\.venv (
    echo [首次运行] 正在创建 Python 虚拟环境并安装依赖...
    python -m venv backend\.venv
    backend\.venv\Scripts\pip install -r backend\requirements.txt
)

if not exist frontend\dist (
    echo [提示] 未找到前端构建产物 frontend\dist
    echo 请先执行: cd frontend ^&^& npm install ^&^& npm run build
    pause
    exit /b 1
)

echo 启动 LaimiuTrade ...
start "" http://127.0.0.1:8000
backend\.venv\Scripts\python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
