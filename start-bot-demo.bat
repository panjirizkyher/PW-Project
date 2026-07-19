@echo off
REM Auto-start launcher untuk PEWE trading bot (DEMO ONLY).
REM Preflight guard cek mode demo dulu; kalau LIVE -> ABORT, bot TIDAK jalan.
cd /d "C:\Users\USER\trading-desk"

echo [START-BOT] Running preflight demo guard...
".venv\Scripts\python.exe" preflight_demo.py
if errorlevel 1 (
    echo [START-BOT] ABORT: preflight gagal ^(mode bukan demo^). Bot TIDAK dijalankan.
    exit /b 1
)

echo [START-BOT] Preflight OK. Starting bot.py in demo mode...
".venv\Scripts\python.exe" bot.py
