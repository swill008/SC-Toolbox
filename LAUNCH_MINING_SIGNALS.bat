@echo off
setlocal enabledelayedexpansion
title Mining Signals
cd /d "%~dp0"

:: Same Python search order as LAUNCH.bat. Opens Mining Signals only.
set "PY="

if exist "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe" (
    set "PY=%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe"
    goto :run
)

for %%V in (314 313 312 311 310 39 38) do (
    if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" (
        set "PY=%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
        goto :run
    )
)

if exist "%LOCALAPPDATA%\Python" (
    for /d %%D in ("%LOCALAPPDATA%\Python\*") do (
        if exist "%%~D\python.exe" (
            set "PY=%%~D\python.exe"
            goto :run
        )
        for /d %%E in ("%%~D\*") do (
            if exist "%%~E\python.exe" (
                set "PY=%%~E\python.exe"
                goto :run
            )
        )
    )
)

where python >nul 2>&1
if !errorlevel!==0 (
    for /f "delims=" %%P in ('where python 2^>nul') do (
        echo %%P | findstr /i "WindowsApps" >nul
        if errorlevel 1 (
            set "PY=%%P"
            goto :run
        )
    )
)

for %%V in (314 313 312 311 310 39 38) do (
    if exist "%ProgramFiles%\Python\Python%%V\python.exe" (
        set "PY=%ProgramFiles%\Python\Python%%V\python.exe"
        goto :run
    )
    if exist "%ProgramFiles%\Python%%V\python.exe" (
        set "PY=%ProgramFiles%\Python%%V\python.exe"
        goto :run
    )
)

for %%V in (314 313 312 311 310 39 38) do (
    if exist "C:\Python%%V\python.exe" (
        set "PY=C:\Python%%V\python.exe"
        goto :run
    )
)

where py >nul 2>&1
if !errorlevel!==0 (
    for /f "delims=" %%P in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do (
        if exist "%%P" (
            set "PY=%%P"
            goto :run
        )
    )
)

echo.
echo  Python not found. Run INSTALL_AND_LAUNCH.bat once, then try this again.
echo.
pause
exit /b 1

:run
echo Using Python: %PY%
echo Verifying dependencies...
set "NEED_INSTALL=0"
"%PY%" -c "import PySide6" >nul 2>&1
if !errorlevel! neq 0 set "NEED_INSTALL=1"
"%PY%" -c "import requests" >nul 2>&1
if !errorlevel! neq 0 set "NEED_INSTALL=1"
"%PY%" -c "import pynput" >nul 2>&1
if !errorlevel! neq 0 set "NEED_INSTALL=1"
"%PY%" -c "import mss" >nul 2>&1
if !errorlevel! neq 0 set "NEED_INSTALL=1"
"%PY%" -c "import pytesseract" >nul 2>&1
if !errorlevel! neq 0 set "NEED_INSTALL=1"
"%PY%" -c "import PIL" >nul 2>&1
if !errorlevel! neq 0 set "NEED_INSTALL=1"

if "!NEED_INSTALL!"=="1" (
    echo  Dependencies missing. Installing from requirements.txt...
    "%PY%" -m pip install -r "%~dp0requirements.txt"
    "%PY%" -c "import PySide6" >nul 2>&1
    if !errorlevel! neq 0 (
        echo  Dependencies could not be installed. Run INSTALL_AND_LAUNCH.bat first.
        pause
        exit /b 1
    )
)

echo Launching Mining Signals...
"%PY%" "%~dp0tools\Mining_Signals\mining_signals_app.py"
echo.
echo  Mining Signals exited with code !errorlevel!
pause
