@echo off
chcp 65001 >nul
title Netlify CLI AI - 智慧部署助手

echo.
echo ============================================================
echo   Netlify CLI AI - 智慧部署助手
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

REM 執行主程式
if "%~1"=="" (
    python "%~dp0netlify_ai.py"
) else (
    python "%~dp0netlify_ai.py" "%~1"
)

echo.
pause
