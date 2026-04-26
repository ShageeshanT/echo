@echo off
cd /d "%~dp0"
echo.
echo ===================================================================
echo   E.C.H.O. web UI starting at http://127.0.0.1:8765
echo   Open that URL in Chrome / Edge / Firefox.
echo   Ctrl+C to stop.
echo ===================================================================
echo.
python -m uvicorn echo.web.server:app --host 127.0.0.1 --port 8765
pause
