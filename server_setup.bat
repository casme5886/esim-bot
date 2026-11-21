@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Booking eSIM - server sozlash

net session >nul 2>&1
if errorlevel 1 (
  echo.
  echo  Bu faylni ADMINISTRATOR sifatida ishga tushiring:
  echo  faylni sichqonchaning o'ng tugmasi bilan bosing -^> "Run as administrator"
  echo.
  pause
  exit /b 1
)

echo.
echo === Booking eSIM: kompyuterni server qilib sozlash ===
echo.

echo [1/4] Uxlash va gibernatsiya o'chirilmoqda (ekran 10 daqiqada o'chadi, kompyuter esa yo'q)...
powercfg /change standby-timeout-ac 0
powercfg /change standby-timeout-dc 0
powercfg /change hibernate-timeout-ac 0
powercfg /change monitor-timeout-ac 10
powercfg /hibernate off

echo [2/4] Windows yangilanishi kunduzi qayta yoqmasligi uchun "faol soatlar" 08:00-02:00...
reg add "HKLM\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings" /v SmartActiveHoursState /t REG_DWORD /d 0 /f >nul
reg add "HKLM\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings" /v ActiveHoursStart /t REG_DWORD /d 8 /f >nul
reg add "HKLM\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings" /v ActiveHoursEnd /t REG_DWORD /d 2 /f >nul

echo [3/4] Windows'ga kirganda bot o'zi ishga tushadigan qilinmoqda...
schtasks /Create /TN "BookingEsimBot" /SC ONLOGON /DELAY 0000:30 /RL HIGHEST /F ^
  /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Minimized -File \"%~dp0server.ps1\"" >nul
if errorlevel 1 (
  echo     XATO: vazifa yaratilmadi.
) else (
  echo     OK: "BookingEsimBot" vazifasi yaratildi.
)

echo [4/4] Bot hozir ishga tushirilmoqda...
schtasks /Run /TN "BookingEsimBot" >nul

echo.
echo ============================================================
echo  Tayyor! Yana 2 ta ishni O'ZINGIZ qiling (SERVER.md da batafsil):
echo   1) Windows parolsiz o'zi kiradigan qilish:  Win+R -^> netplwiz
echo   2) BIOS: "Restore on AC Power Loss" -^> "Power On"
echo ============================================================
echo.
pause
