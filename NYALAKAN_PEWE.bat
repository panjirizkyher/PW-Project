@echo off
REM ================================================================
REM   PEWE Trading Desk - Nyalakan SEMUA (bot + WARP + tunnel)
REM   Klik 2x file ini setelah PC restart/sleep.
REM ================================================================
echo [1/3] Menyalakan Cloudflare WARP (biar Binance kebuka)...
"C:\Program Files\Cloudflare\Cloudflare WARP\warp-cli.exe" connect
timeout /t 5 /nobreak >nul

echo [2/3] Menyalakan BOT (port 8731)...
cd /d C:\Users\USER\trading-desk
set PEWE_PORT=8731
start "PEWE-BOT" C:\Users\USER\trading-desk\.venv\Scripts\python.exe bot.py
timeout /t 8 /nobreak >nul

echo [3/3] Menyalakan TUNNEL PERMANEN (ngrok)...
start "PEWE-TUNNEL" "C:\Users\USER\AppData\Local\Microsoft\WinGet\Packages\Ngrok.Ngrok_Microsoft.Winget.Source_8wekyb3d8bbwe\ngrok.exe" http 8731 --domain=pry-unraveled-mustang.ngrok-free.dev

echo.
echo ================================================================
echo  SELESAI! Buka dashboard di:
echo  https://pry-unraveled-mustang.ngrok-free.dev/dashboard.html?t=c7ef3d74be231a5ccddbf29f3b92793d
echo ================================================================
pause
