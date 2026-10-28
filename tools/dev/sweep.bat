@echo off
chcp 65001 >nul
cd /d "%~dp0..\.."

net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

echo ============================================
echo  Full-run offset sweep on ShootStage HARD
echo  cycles -30 / -20 / -10 / 0 ms (negative = earlier)
echo  no MODs selected in game
echo  F9 = arm, F10 = quit
echo ============================================
py -3.13 tools\replay.py --chart charts\ShootStage_HD.json --sweep=-30,-20,-10,0 --dump-verdicts --pause

