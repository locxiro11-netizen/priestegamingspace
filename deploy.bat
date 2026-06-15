@echo off
echo ========================================
echo   PriesteGamingSpace · 一键部署
echo ========================================
echo.

cd /d "C:\Users\enciodesliu\WorkBuddy\2026-06-13-17-38-17"

echo [1/3] 添加所有改动...
git add -A

echo [2/3] 提交...
set d=%date:~0,4%%date:~5,2%%date:~8,2%
set t=%time:~0,2%%time:~3,2%
git commit -m "Update %d%-%t%"

echo [3/3] 推送到 GitHub...
git push origin main

echo.
echo ========================================
echo   部署完成！
echo   网站: https://locxiro11-netizen.github.io/priestegamingspace/
echo ========================================
pause
