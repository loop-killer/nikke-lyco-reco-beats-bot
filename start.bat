@echo off
chcp 65001 >nul
cd /d "%~dp0"

net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

set "PY=py -3.13"
%PY% -c "" >nul 2>&1
if errorlevel 1 set "PY=python"

%PY% -c "import UnityPy, numpy, scipy, soundcard" >nul 2>&1
if errorlevel 1 (
    echo 正在安装依赖...
    %PY% -m pip install -r requirements.txt
)

%PY% launcher.py
pause
