@echo off
setlocal
cd /d "%~dp0"
where powershell.exe >nul 2>&1
if errorlevel 1 (
    echo Fehler: Windows PowerShell wurde nicht gefunden.
    pause
    exit /b 1
)
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0build-local.ps1" %*
set "BUILD_EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%BUILD_EXIT_CODE%"=="0" (
    echo Lokaler Build fehlgeschlagen. Siehe Fehlermeldung oben.
) else (
    echo Fertig! Die EXE liegt unter dist\ReelShift.exe.
)
pause
exit /b %BUILD_EXIT_CODE%
