@echo off
chcp 65001 >nul
cd /d "%~dp0..\.."

net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

echo ============================================
echo  Record a manual Normal run (with the guide bar)
echo  F9 = arm, then play the whole stage yourself
echo  F10 = stop
echo ============================================
py -3.13 tools\record.py --chart charts\ShootStage_NM.json --pause

