@echo off
cd /d "%~dp0\.."

where desktop-assistant >nul 2>nul
if %errorlevel%==0 (
  desktop-assistant %*
) else (
  python -m desktop_assistant %*
)
