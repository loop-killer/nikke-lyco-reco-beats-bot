@echo off
chcp 65001 >nul
cd /d "%~dp0..\.."

net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

echo ============================================
echo  ShootStage HARD - full run, offset -20ms
echo  no MODs selected in game (first validation)
echo  F9 = arm, F10 = quit
echo ============================================
py -3.13 tools\replay.py --chart charts\ShootStage_HD.json --offset-ms -20 --dump-verdicts --pause

