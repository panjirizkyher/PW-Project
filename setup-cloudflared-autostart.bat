@echo off
REM Jalankan sebagai Administrator (klik kanan -> Run as Admin)
REM Bikin scheduled task auto-start Cloudflared tunnel (survive reboot/logoff)

schtasks.exe /Create /TN "PEWE-Cloudflared-Tunnel" ^
 /TR "C:\Users\USER\trading-desk\cloudflared.exe tunnel run pewe-desk" ^
 /SC ONSTART /RL HIGHEST /RU "%USERNAME%" /F

IF %ERRORLEVEL% NEQ 0 (
  echo GAGAL buat task. Pastikan dijalankan sebagai Administrator.
  pause
  exit /b 1
)

REM trigger tambahan: pas user logon
schtasks.exe /Change /TN "PEWE-Cloudflared-Tunnel" /ENABLE
schtasks.exe /Run /TN "PEWE-Cloudflared-Tunnel"

echo.
echo Task "PEWE-Cloudflared-Tunnel" dibuat + dijalankan.
echo Cek: schtasks /Query /TN "PEWE-Cloudflared-Tunnel"
echo Tunnel pwproject.my.id -> http://localhost:8731
pause
