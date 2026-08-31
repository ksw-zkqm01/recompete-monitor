@echo off
setlocal
cd /d "%~dp0"
title US - DHS Capture Trigger
set "PYCMD="
py -3.11 --version >nul 2>&1 && set "PYCMD=py -3.11"
if not defined PYCMD ( py -3 --version >nul 2>&1 && set "PYCMD=py -3" )
if not defined PYCMD ( python --version >nul 2>&1 && set "PYCMD=python" )
if not defined PYCMD ( echo [FAIL] Python not found. ^& pause ^& exit /b 1 )

:MENU
cls
echo ==================================================
echo   US  -  DHS APFS CAPTURE TRIGGER
echo ==================================================
echo   1  SNAPSHOT (live APFS)   today's forecast
echo   0P PROBE                  check the live source right now
echo   2  SNAPSHOT (sample)      offline 20-record sample
echo   3  DIFF                   yesterday vs today
echo   4  BRIEF                  write capture-trigger brief
echo   5  PIPELINE               1 + 3 + 4
echo   9  SIMULATE               demo the engine on the sample
echo   0  quit
echo ==================================================
set "SEL="
set /p "SEL=Select: "
if /i "%SEL%"=="0P" ( %PYCMD% run_platform.py --source us probe & pause & goto MENU )
if "%SEL%"=="1" ( %PYCMD% run_platform.py --source us snapshot & pause & goto MENU )
if "%SEL%"=="2" ( %PYCMD% run_platform.py --source us --sample dhs_recompete_sample_20.json snapshot & pause & goto MENU )
if "%SEL%"=="3" ( %PYCMD% run_platform.py --source us diff & pause & goto MENU )
if "%SEL%"=="4" ( %PYCMD% run_platform.py --source us --lang en --min medium --show brief & if exist out start "" explorer "%cd%\out" & pause & goto MENU )
if "%SEL%"=="5" ( %PYCMD% run_platform.py --source us --lang en --show pipeline & pause & goto MENU )
if "%SEL%"=="9" ( %PYCMD% run_platform.py --source us --lang en simulate & pause & goto MENU )
if "%SEL%"=="0" exit /b 0
goto MENU
