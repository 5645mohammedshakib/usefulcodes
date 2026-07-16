@echo off
cd /d "e:\project student hub"

echo [1] Checking remote...
git remote -v

echo.
echo [2] Setting remote if not set...
git remote add origin https://github.com/5645mohammedshakib/usefulcodes.git 2>nul
git remote set-url origin https://github.com/5645mohammedshakib/usefulcodes.git

echo.
echo [3] Adding all files...
git add -A

echo.
echo [4] Committing...
git commit -m "Update: Student Hub - admin panel aligned with student portal"

echo.
echo [5] Pushing to main...
git push -u origin main

echo.
echo ============================
echo   PUSH COMPLETE!
echo ============================
pause
