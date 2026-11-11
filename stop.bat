@echo off
setlocal
cd /d "%~dp0"

echo Encerrando VPS Host Panel...

powershell -NoProfile -Command ^
  "$ports = 8000,8800,8810; Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $ports -contains $_.LocalPort } | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"

for %%P in (8000 8800 8810) do (
  for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%%P" ^| findstr LISTENING') do (
    taskkill /F /PID %%a >nul 2>&1
  )
)

taskkill /F /FI "WINDOWTITLE eq VPS Host - Backend*" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq VPS Host - Frontend*" >nul 2>&1

echo Pronto. Portas 8000, 8800 e 8810 liberadas.
timeout /t 1 /nobreak >nul
