@echo off
setlocal
cd /d "%~dp0"
title Capture Trigger - Web Dashboard
set "PYCMD="
py -3.11 --version >nul 2>&1 && set "PYCMD=py -3.11"
if not defined PYCMD ( py -3 --version >nul 2>&1 && set "PYCMD=py -3" )
if not defined PYCMD ( python --version >nul 2>&1 && set "PYCMD=python" )
if not defined PYCMD ( echo [FAIL] Python not found. Run START.bat first. & pause & exit /b 1 )
echo Opening http://127.0.0.1:8787 ...
echo Close this window (or Ctrl+C) to stop the server.
%PYCMD% webapp.py
pause
