@echo off
REM Launch the US Equity Entry-Timing dashboard.
cd /d "%~dp0"
echo Installing/verifying dependencies...
python -m pip install -r requirements.txt --quiet --disable-pip-version-check
echo Starting dashboard...
python app.py
pause
