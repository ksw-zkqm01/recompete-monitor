@echo off
setlocal
cd /d "%~dp0"
title Recompete Platform - Setup
echo ==================================================
echo   RECOMPETE / CAPTURE-TRIGGER PLATFORM
echo   KR (Narajangteo) + US (DHS APFS) - one engine
echo ==================================================
echo.
set "PYCMD="
py -3.11 --version >nul 2>&1 && set "PYCMD=py -3.11"
if not defined PYCMD ( py -3 --version >nul 2>&1 && set "PYCMD=py -3" )
if not defined PYCMD ( python --version >nul 2>&1 && set "PYCMD=python" )
if not defined PYCMD ( echo [FAIL] Python not found. ^& pause ^& exit /b 1 )

echo [1/3] installing packages ...
%PYCMD% -m pip install --disable-pip-version-check --quiet requests pyyaml
if errorlevel 1 ( echo [FAIL] pip install failed. & pause & exit /b 1 )
echo [2/3] creating databases ...
%PYCMD% run_kr.py init
echo [3/3] change-engine demo on the US sample ...
%PYCMD% run_platform.py --source us --lang en simulate
echo.
echo ==================================================
echo   Open the "out" folder to read the generated brief.
echo ==================================================
if exist out ( start "" explorer "%cd%\out" )
pause
