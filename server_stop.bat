@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Booking eSIM server to'xtatilmoqda...
schtasks /End /TN "BookingEsimBot" >nul 2>&1
for %%F in (server.pid bot.pid cloudflared.pid) do (
  if exist "%%F" (
    for /f %%P in (%%F) do taskkill /PID %%P /F >nul 2>&1
    del "%%F" >nul 2>&1
  )
)
echo To'xtadi. Qayta yoqish: kompyuterni qayta yoqing yoki  schtasks /Run /TN "BookingEsimBot"
echo Avtomatik ishga tushishni butunlay o'chirish:  schtasks /Delete /TN "BookingEsimBot" /F
pause
