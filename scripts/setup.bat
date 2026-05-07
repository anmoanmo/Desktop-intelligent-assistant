@echo off
setlocal
cd /d "%~dp0\.."

if "%DESKTOP_ASSISTANT_CONDA_ENV%"=="" (
  set ENV_NAME=desktop-assistant
) else (
  set ENV_NAME=%DESKTOP_ASSISTANT_CONDA_ENV%
)

conda env list | findstr /R /C:"^%ENV_NAME% " >nul 2>nul
if %errorlevel%==0 (
  conda env update -n %ENV_NAME% -f environment.yml --prune
) else (
  conda env create -n %ENV_NAME% -f environment.yml
)

echo 环境已准备完成。请执行：conda activate %ENV_NAME%
endlocal
