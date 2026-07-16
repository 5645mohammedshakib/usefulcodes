@echo off
cd /d "e:\project student hub"
echo === Git Status ===
git status
echo.
echo === Git Add ===
git add -A
echo.
echo === Git Commit ===
git commit -m "Update: align admin panel and student portal features"
echo.
echo === Git Push ===
git push
echo.
echo === Done! ===
pause
