$ErrorActionPreference = "SilentlyContinue"
Set-Location "C:\Users\Administrator\trading-desk"
$exe = "C:\Users\Administrator\trading-desk\.venv\Scripts\python.exe"
$arg = "C:\Users\Administrator\trading-desk\bot.py"
# loop: restart kalau crash (max sederhana, biar survive)
while ($true) {
    & $exe $arg
    Start-Sleep 5
}
