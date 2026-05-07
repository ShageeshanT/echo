@echo off
rem Tkinter desktop UI (legacy fallback). The default UI is now the web one
rem launched by run.bat. This script keeps Tkinter accessible for regression
rem testing or offline scenarios.
cd /d "%~dp0"
echo.
echo ====================================================================
echo   E.C.H.O. (Tkinter desktop UI - legacy fallback)
echo   For the new web UI, just use run.bat
echo ====================================================================
echo.
python jarvis.py
pause
