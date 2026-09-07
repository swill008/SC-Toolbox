@echo off
setlocal enabledelayedexpansion
title SC_Toolbox Installer
color 0B

echo.
echo  =============================================
echo   SC_Toolbox Beta V1 - Installer ^& Launcher
echo  =============================================
echo.

:: ── Find Python ──
set "PYTHON_EXE="
call :find_python
if defined PYTHON_EXE goto :python_ready

:: ── Python not found — attempt automatic install ──
echo  [!] Python not found on this system.
echo.

where winget >nul 2>&1
if !errorlevel!==0 (
    echo  [*] Installing Python 3.12 via winget...
    echo      This may take a few minutes. Please wait...
    echo.
    winget install Python.Python.3.12 --accept-source-agreements --accept-package-agreements --silent
    if !errorlevel!==0 (
        echo  [OK] Python installed via winget.
        echo.
        call :refresh_path
        call :find_python
        if defined PYTHON_EXE goto :python_ready
    )
    echo  [!] winget install did not succeed or Python not yet on PATH.
    echo.
)

echo  [*] Downloading Python 3.12.9 installer from python.org...
set "INSTALLER=%TEMP%\python-3.12.9-amd64.exe"
set "PYTHON_URL=https://www.python.org/ftp/python/3.12.9/python-3.12.9-amd64.exe"

where curl >nul 2>&1
if !errorlevel!==0 (
    curl -L -o "%INSTALLER%" "%PYTHON_URL%"
) else (
    powershell -Command "Invoke-WebRequest -Uri '%PYTHON_URL%' -OutFile '%INSTALLER%'"
)

if not exist "%INSTALLER%" (
    echo  [!] Failed to download Python installer.
    echo      Please install Python 3.10+ manually from https://www.python.org/downloads/
    goto :done
)

echo  [*] Running Python installer (silent, adds to PATH)...
echo      This may take a few minutes. Please wait...
echo.
"%INSTALLER%" /passive InstallAllUsers=0 PrependPath=1 Include_pip=1 Include_tcltk=1
if !errorlevel! neq 0 (
    echo  [!] Python installer exited with an error.
    echo      Trying interactive install — please follow the prompts.
    echo      IMPORTANT: Check "Add Python to PATH" during installation!
    echo.
    "%INSTALLER%" InstallAllUsers=0 PrependPath=1 Include_pip=1 Include_tcltk=1
)

del "%INSTALLER%" >nul 2>&1

call :refresh_path
call :find_python
if not defined PYTHON_EXE (
    echo  [!] Python still not found after installation.
    echo      Please restart this script, or install Python manually from:
    echo      https://www.python.org/downloads/
    echo      Make sure to check "Add Python to PATH" during installation.
    goto :done
)

:python_ready
echo  [OK] Python: %PYTHON_EXE%

"%PYTHON_EXE%" -m pip install --upgrade pip --quiet >nul 2>&1

echo.
echo  [*] Checking dependencies...

"%PYTHON_EXE%" -c "import PySide6" >nul 2>&1
if !errorlevel! neq 0 goto :install_deps
"%PYTHON_EXE%" -c "import requests" >nul 2>&1
if !errorlevel! neq 0 goto :install_deps
"%PYTHON_EXE%" -c "import pynput" >nul 2>&1
if !errorlevel! neq 0 goto :install_deps
"%PYTHON_EXE%" -c "import mss" >nul 2>&1
if !errorlevel! neq 0 goto :install_deps
"%PYTHON_EXE%" -c "import pytesseract" >nul 2>&1
if !errorlevel! neq 0 goto :install_deps
"%PYTHON_EXE%" -c "import PIL" >nul 2>&1
if !errorlevel! neq 0 goto :install_deps
"%PYTHON_EXE%" -c "import numpy" >nul 2>&1
if !errorlevel! neq 0 goto :install_deps
"%PYTHON_EXE%" -c "import onnxruntime" >nul 2>&1
if !errorlevel! neq 0 goto :install_deps
goto :deps_ok

:install_deps
echo  [*] Installing dependencies (including numpy and onnxruntime for Mining Signals)...
echo      This may take a few minutes on first run...
"%PYTHON_EXE%" -m pip install -r "%~dp0requirements.txt" --quiet
if !errorlevel! neq 0 (
    echo  [!] Quiet install failed. Retrying with verbose output...
    "%PYTHON_EXE%" -m pip install -r "%~dp0requirements.txt"
)

"%PYTHON_EXE%" -c "import PySide6" >nul 2>&1
if !errorlevel! neq 0 (
    echo  [!] PySide6 failed to install. Please check errors above.
    goto :done
)

:deps_ok
echo  [OK] PySide6
echo  [OK] requests
echo  [OK] pynput
echo  [OK] mss
echo  [OK] pytesseract
echo  [OK] Pillow
echo  [OK] numpy
echo  [OK] onnxruntime
echo.
echo  =============================================
echo   Launching SC_Toolbox...
echo  =============================================
echo.

"%PYTHON_EXE%" "%~dp0skill_launcher.py" 100 100 500 550 0.95 nul

echo.
echo  SC_Toolbox closed.

:done
echo.
echo  Press any key to close this window...
pause >nul
exit /b

:find_python
if exist "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe" (
    set "PYTHON_EXE=%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe"
    exit /b
)

for %%V in (314 313 312 311 310 39 38) do (
    if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" (
        set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
        exit /b
    )
)

if exist "%LOCALAPPDATA%\Python" (
    for /d %%D in ("%LOCALAPPDATA%\Python\*") do (
        if exist "%%~D\python.exe" (
            set "PYTHON_EXE=%%~D\python.exe"
            exit /b
        )
        for /d %%E in ("%%~D\*") do (
            if exist "%%~E\python.exe" (
                set "PYTHON_EXE=%%~E\python.exe"
                exit /b
            )
        )
    )
)

where python >nul 2>&1
if !errorlevel!==0 (
    for /f "delims=" %%P in ('where python 2^>nul') do (
        echo %%P | findstr /i "WindowsApps" >nul
        if errorlevel 1 (
            set "PYTHON_EXE=%%P"
            exit /b
        )
    )
)

for %%V in (314 313 312 311 310 39 38) do (
    if exist "%ProgramFiles%\Python\Python%%V\python.exe" (
        set "PYTHON_EXE=%ProgramFiles%\Python\Python%%V\python.exe"
        exit /b
    )
    if exist "%ProgramFiles%\Python%%V\python.exe" (
        set "PYTHON_EXE=%ProgramFiles%\Python%%V\python.exe"
        exit /b
    )
)

for %%V in (314 313 312 311 310 39 38) do (
    if exist "C:\Python%%V\python.exe" (
        set "PYTHON_EXE=C:\Python%%V\python.exe"
        exit /b
    )
)

where py >nul 2>&1
if !errorlevel!==0 (
    for /f "delims=" %%P in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do (
        if exist "%%P" (
            set "PYTHON_EXE=%%P"
            exit /b
        )
    )
)

exit /b

:refresh_path
set "USER_PATH="
set "SYS_PATH="
for /f "tokens=2*" %%A in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "USER_PATH=%%B"
for /f "tokens=2*" %%A in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do set "SYS_PATH=%%B"
if not defined USER_PATH set "USER_PATH="
if not defined SYS_PATH set "SYS_PATH=%PATH%"
if "!USER_PATH!"=="" (
    set "PATH=!SYS_PATH!"
) else (
    set "PATH=!USER_PATH!;!SYS_PATH!"
)
exit /b
