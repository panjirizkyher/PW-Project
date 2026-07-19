@echo off
REM Jalankan sebagai Administrator (klik kanan -> Run as administrator)
REM Bikin scheduled task auto-start PEWE bot (DEMO ONLY) saat boot/logon.

schtasks.exe /Create /TN "PEWE-Bot-Demo" /TR "C:\Users\USER\trading-desk\start-bot-demo.bat" /SC ONLOGON /RL HIGHEST /F
if errorlevel 1 (
    echo.
    echo GAGAL bikin task. Pastikan lu klik kanan -^> Run as administrator.
    pause
    exit /b 1
)

echo.
echo SUCCESS: Task "PEWE-Bot-Demo" dibuat ^(auto-start saat login, DEMO ONLY^).
echo Menjalankan task sekarang...
schtasks.exe /Run /TN "PEWE-Bot-Demo"
echo.
echo Selesai. Bot auto-start aktif ^(mode demo, guard preflight ON^).
pause
