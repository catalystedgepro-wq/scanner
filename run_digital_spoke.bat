@echo off
:: Cerebro Digital Footprint Spoke — Residential Automation Node
:: Runs spoke_digital.py (Google Trends) and pushes spark_velocities.json to GitHub
:: Schedule: Every 4 hours via Windows Task Scheduler (6 AM – 8 PM)

cd /d "%~dp0"

echo [%date% %time%] ============================================
echo [%date% %time%] Cerebro Digital Footprint Spoke Starting...
echo [%date% %time%] ============================================

echo [1/4] Pulling latest pipeline state from GitHub...
git pull --rebase origin main
if %ERRORLEVEL% NEQ 0 (
    echo WARN: git pull failed — continuing with local state
)

echo [2/4] Running Google Trends velocity scan...
python spoke_digital.py --limit=100
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: spoke_digital.py failed
    exit /b 1
)

echo [3/4] Staging spark velocities...
git add spark_velocities.json digital_footprint.json
git diff --cached --quiet
if %ERRORLEVEL% EQU 0 (
    echo INFO: No changes to push — all velocities unchanged
    goto :done
)

echo [4/4] Committing and pushing to GitHub...
git commit -m "auto: digital velocity update %date% %time%"
git push origin main
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: git push failed
    exit /b 1
)

:done
echo [%date% %time%] Digital spoke complete.
