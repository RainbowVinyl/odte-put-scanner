@echo off
REM Windows launcher. Requires Python 3 on PATH.
setlocal
set DIR=%~dp0
if "%~1"=="" (
  python "%DIR%scanner.py" --live
) else (
  python "%DIR%scanner.py" %*
)
echo.
pause
