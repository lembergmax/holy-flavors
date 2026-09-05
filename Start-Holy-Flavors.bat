@echo off
cd /d "%~dp0"
start "" pyw -3 "%~dp0Holy-Flavors.pyw"
if errorlevel 1 (
    echo.
    echo HOLY Flavors could not be started.
    echo Install missing packages with: py -3 -m pip install -r requirements.txt
    pause
)
exit /b
