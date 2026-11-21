@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [1/2] Trip.com kirish holati chiqarilmoqda...
python trip_export.py || (echo XATO: python yoki playwright topilmadi & pause & exit /b 1)
echo [2/2] Serverga yuklanmoqda...
scp trip_state.json sardor@100.113.45.73:~/esim-data/trip_state.json || (echo XATO: serverga yuklab bo'lmadi & pause & exit /b 1)
del trip_state.json
echo.
echo Tayyor! Endi Claude'ga "bo'ldi" deb yozing.
pause
