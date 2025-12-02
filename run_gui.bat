@echo off
chcp 65001 >nul
title Netlify CLI AI - 智慧部署助手 (GUI)

echo.
echo ============================================================
echo   Netlify CLI AI - 智慧部署助手 (GUI 版本)
echo   曾慶良(阿亮老師)建置
echo ============================================================
echo.

REM 檢查 Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [錯誤] 未偵測到 Python，請先安裝 Python 3.7+
    echo 下載：https://www.python.org/downloads/
    pause
    exit /b 1
)

REM 檢查 Flask
python -c "import flask" >nul 2>&1
if %errorlevel% neq 0 (
    echo [提示] 正在安裝 Flask...
    pip install flask
    echo.
)

echo   啟動中...
echo   網址: http://127.0.0.1:5886
echo.
echo   瀏覽器將自動開啟，如未開啟請手動訪問上述網址
echo   按 Ctrl+C 可停止伺服器
echo.
echo ============================================================
echo.

REM 執行 Flask 應用
python "%~dp0app.py"

pause
