@echo off
chcp 65001 >nul
cd /d "%~dp0..\.."

net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

echo ============================================
echo  Left-edge sweep #2 on ShootStage HARD
echo  cycles -50 / -60 / -70 / -80 ms
echo  enable the SAME difficulty MOD as before
echo  F9 = arm, F10 = quit
echo ============================================
py -3.13 tools\replay.py --chart charts\ShootStage_HD.json --sweep=-50,-60,-70,-80 --dump-verdicts --pause

