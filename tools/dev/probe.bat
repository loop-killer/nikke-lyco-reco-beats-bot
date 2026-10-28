@echo off
chcp 65001 >nul
cd /d "%~dp0..\.."

net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

echo ============================================
echo  Offset sweep on ShootStage NORMAL
echo  positive = press LATER (ms)
echo  3 samples each at -20 / 0 / 20 / 40 / 60
echo  F9 = arm, F10 = quit
echo ============================================
py -3.13 tools\replay.py --chart charts\ShootStage_NM.json --probe=-20,0,20,40,60,-20,0,20,40,60,-20,0,20,40,60 --pause


