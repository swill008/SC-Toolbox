@echo off
setlocal enabledelayedexpansion
title SC_Toolbox
cd /d "%~dp0"

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

where python >nul 2>&1
if !errorlevel!==0 (
    for /f "delims=" %%P in ('where python 2^>nul') do (
        "%%P" -c "import sys; assert sys.version_info >= (3, 9)" >nul 2>&1
        if !errorlevel!==0 (
            set "PY=%%P"
            goto :run
        )
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
echo  Python not found. Running installer (will auto-install Python)...
echo.
call "%~dp0INSTALL_AND_LAUNCH.bat"
exit /b

:run
echo Using Python: %PY%
echo Verifying dependencies...
set "NEED_INSTALL=0"
echo  - PySide6
"%PY%" -c "import PySide6"
if !errorlevel! neq 0 set "NEED_INSTALL=1"
echo  - requests
"%PY%" -c "import requests"
if !errorlevel! neq 0 set "NEED_INSTALL=1"
echo  - pynput
"%PY%" -c "import pynput"
if !errorlevel! neq 0 set "NEED_INSTALL=1"
echo  - mss
"%PY%" -c "import mss"
if !errorlevel! neq 0 set "NEED_INSTALL=1"
echo  - pytesseract
"%PY%" -c "import pytesseract"
if !errorlevel! neq 0 set "NEED_INSTALL=1"
echo  - PIL
"%PY%" -c "import PIL"
if !errorlevel! neq 0 set "NEED_INSTALL=1"
echo  - numpy
"%PY%" -c "import numpy"
if !errorlevel! neq 0 set "NEED_INSTALL=1"
echo  - onnxruntime
"%PY%" -c "import onnxruntime"
if !errorlevel! neq 0 set "NEED_INSTALL=1"
echo Dependency check complete.

if "!NEED_INSTALL!"=="1" (
    echo  Dependencies missing. Installing from requirements.txt...
    "%PY%" -m pip install -r "%~dp0requirements.txt" --quiet 2>nul
    if !errorlevel! neq 0 (
        "%PY%" -m pip install -r "%~dp0requirements.txt"
    )
    "%PY%" -c "import PySide6" >nul 2>&1
    if !errorlevel! neq 0 (
        echo  Dependencies could not be installed.
        echo  Running full installer...
        echo.
        call "%~dp0INSTALL_AND_LAUNCH.bat"
        exit /b
    )
)

echo Launching skill_launcher.py...
"%PY%" "%~dp0skill_launcher.py" 100 100 500 550 0.95 nul
echo.
echo  skill_launcher exited with code !errorlevel!
pause
