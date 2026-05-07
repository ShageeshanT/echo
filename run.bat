@echo off
cd /d "%~dp0"
echo.
echo ====================================================================
echo   E.C.H.O. starting at http://127.0.0.1:8765
echo   The page will open in your default browser.
echo   Ctrl+C in this window to stop.
echo ====================================================================
echo.
rem Open the page after a small delay so uvicorn has time to bind the port.
start "" /b cmd /c "timeout /t 2 /nobreak > nul && start http://127.0.0.1:8765"
python -m uvicorn echo.web.server:app --host 127.0.0.1 --port 8765
pause
