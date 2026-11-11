@echo off
setlocal
cd /d "%~dp0"

echo Iniciando VPS Host Panel...
echo.

if not exist "backend\venv\Scripts\activate.bat" (
    echo [ERRO] Virtualenv do backend nao encontrado.
    echo Execute: cd backend ^&^& python -m venv venv ^&^& venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

if not exist "frontend\node_modules" (
    echo [ERRO] Dependencias do frontend nao encontradas.
    echo Execute: cd frontend ^&^& npm install
    pause
    exit /b 1
)

echo Encerrando backends antigos nas portas 8000, 8800 e 8810...
powershell -NoProfile -Command ^
  "$ports = 8000,8800,8810; Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $ports -contains $_.LocalPort } | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000" ^| findstr LISTENING') do (
    taskkill /F /PID %%a >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8800" ^| findstr LISTENING') do (
    taskkill /F /PID %%a >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8810" ^| findstr LISTENING') do (
    taskkill /F /PID %%a >nul 2>&1
)
timeout /t 2 /nobreak >nul

start "VPS Host - Backend" cmd /k "cd /d %~dp0backend && call venv\Scripts\activate.bat && python -m uvicorn app.main:app --host 127.0.0.1 --port 8810"

timeout /t 2 /nobreak >nul

start "VPS Host - Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo Backend:  http://localhost:8810
echo Frontend: http://localhost:3000
echo.
echo Duas janelas foram abertas. Feche-as para encerrar os servidores.
pause
