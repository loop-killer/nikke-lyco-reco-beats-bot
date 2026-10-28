@echo off
chcp 65001 >nul
cd /d "%~dp0"
title LYCO RECO BEATS Bot

net session >nul 2>&1
if not "%errorlevel%"=="0" goto :elevate
goto :run

:elevate
powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
exit /b

:run
set "PY="
py -3.13 -c "" >nul 2>&1
if not errorlevel 1 set "PY=py -3.13"
if not defined PY (
    python -c "" >nul 2>&1
    if not errorlevel 1 set "PY=python"
)
if not defined PY goto :nopython

%PY% -c "import UnityPy, numpy, scipy, soundcard" >nul 2>&1
if errorlevel 1 (
    echo 正在安装依赖，请稍候...
    %PY% -m pip install -r requirements.txt
    if errorlevel 1 goto :pipfail
)

%PY% launcher.py
pause
exit /b

:pipfail
echo.
echo [错误] 依赖安装失败。请手动运行：
echo   %PY% -m pip install -r requirements.txt
pause
exit /b 1

:nopython
echo.
echo [错误] 没有找到 Python。请先安装 Python 3.10 或更高版本，
echo        安装时勾选 "Add Python to PATH"，然后重新运行 start.bat。
pause
exit /b 1