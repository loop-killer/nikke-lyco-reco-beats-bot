@echo off
chcp 65001 >nul
cd /d "%~dp0..\.."

net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

echo ============================================
echo  Stage 2 TrainingHD - ALL MODs, offset -45ms
echo  F9 = arm, F10 = quit
echo ============================================
py -3.13 tools\replay.py --chart charts\TrainingHD.json --offset-ms -45 --dump-verdicts --pause

