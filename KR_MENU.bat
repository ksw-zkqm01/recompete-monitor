@echo off
setlocal
cd /d "%~dp0"
title KR - Narajangteo D-90
set "PYCMD="
py -3.11 --version >nul 2>&1 && set "PYCMD=py -3.11"
if not defined PYCMD ( py -3 --version >nul 2>&1 && set "PYCMD=py -3" )
if not defined PYCMD ( python --version >nul 2>&1 && set "PYCMD=python" )
if not defined PYCMD ( echo [FAIL] Python not found. ^& pause ^& exit /b 1 )

:MENU
cls
echo ==================================================
echo   KR  -  NARAJANGTEO  (D-90)
echo ==================================================
echo   -- collect raw data --
echo   1  BIDS        7 days of bid notices
echo   2  CONTRACTS   90 days  (fuel for renewal radar)
echo   3  SCSBID      7 days of awards (optional, heavy)
echo.
echo   -- change engine --
echo   4  SNAPSHOT    today's normalized records
echo   5  DIFF        yesterday vs today
echo   6  BRIEF       write today's change brief
echo   7  PIPELINE    4 + 5 + 6
echo.
echo   -- classic --
echo   8  LEADS       contractor call-list CSV
echo   9  DIAG        what is in the database
echo   0P PROBE       is the change engine getting any records
echo   0  quit
echo ==================================================
set "SEL="
set /p "SEL=Select: "
if "%SEL%"=="1" ( %PYCMD% run_kr.py collect --days 7 & pause & goto MENU )
if "%SEL%"=="2" ( %PYCMD% run_kr.py collect-contracts --days 90 & pause & goto MENU )
if "%SEL%"=="3" ( %PYCMD% run_kr.py collect-scsbid --days 7 & pause & goto MENU )
if "%SEL%"=="4" ( %PYCMD% run_platform.py --source kr snapshot & pause & goto MENU )
if "%SEL%"=="5" ( %PYCMD% run_platform.py --source kr diff & pause & goto MENU )
if "%SEL%"=="6" ( %PYCMD% run_platform.py --source kr --min medium --show brief & if exist out start "" explorer "%cd%\out" & pause & goto MENU )
if "%SEL%"=="7" ( %PYCMD% run_platform.py --source kr --show pipeline & pause & goto MENU )
if "%SEL%"=="8" ( %PYCMD% run_kr.py leads & if exist out start "" explorer "%cd%\out" & pause & goto MENU )
if /i "%SEL%"=="0P" ( %PYCMD% run_platform.py --source kr probe & pause & goto MENU )
if "%SEL%"=="9" ( %PYCMD% diag.py & pause & goto MENU )
if "%SEL%"=="0" exit /b 0
goto MENU
