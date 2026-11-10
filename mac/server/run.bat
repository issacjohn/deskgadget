@echo off
title DESKGadget server
cd /d "%~dp0.."
python -m server.main
echo.
echo Server stopped. Press any key to close.
pause >nul
