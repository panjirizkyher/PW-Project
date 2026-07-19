$ErrorActionPreference = "SilentlyContinue"
Set-Location "C:\Users\Administrator\trading-desk"
$exe = "C:\Users\Administrator\trading-desk\cloudflared.exe"
$arg = "tunnel run pewe-desk"
# jalanin sebagai detached process (survive walaupun ps1 exit)
Start-Process -FilePath $exe -ArgumentList $arg -WindowStyle Hidden -WorkingDirectory "C:\Users\Administrator\trading-desk"
# ps1 exit, tapi cloudflared tetap jalan (anak process detach)
