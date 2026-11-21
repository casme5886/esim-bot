# Booking eSIM bot - bir bosishda ishga tushirish (start.bat orqali chaqiriladi)
# MUHIM: Cloudflare tunnel botdan ALOHIDA ishlaydi. Botni qayta ishga tushirganda tunnel (va Mini App manzili)
# o'zgarmaydi - mijozlar /start bosmasdan ishlashda davom etadi. Manzil faqat kompyuter qayta yonganda o'zgaradi.
$ErrorActionPreference = "Continue"
Set-Location -Path $PSScriptRoot
$Host.UI.RawUI.WindowTitle = "Booking eSIM bot"

Write-Host ""
Write-Host "=== Booking eSIM bot ishga tushirilmoqda ===" -ForegroundColor Cyan

function Test-Tunnel($url) {
    # bot hali yoqilmagan bo'lsa Cloudflare 502 qaytaradi - bu tunnel tirik degani.
    # 530 (Error 1033) yoki manzil topilmasa - tunnel o'lgan, yangisi kerak.
    try {
        Invoke-WebRequest -Uri "$url/" -UseBasicParsing -TimeoutSec 15 | Out-Null
        return $true
    } catch {
        $code = $null
        try { $code = [int]$_.Exception.Response.StatusCode } catch {}
        if ($code -and $code -ne 530) { return $true }
        return $false
    }
}

# 1) Faqat SHU botning eski nusxasini yopish (tunnelga tegmaymiz)
Write-Host "[1/5] Eski nusxa yopilmoqda..."
$f = Join-Path $PSScriptRoot "bot.pid"
if (Test-Path $f) {
    $oldPid = (Get-Content $f -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($oldPid) { Stop-Process -Id ([int]$oldPid) -Force -ErrorAction SilentlyContinue }
    Remove-Item $f -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 1

# 2) Kutubxonalar (o'rnatilgan bo'lsa tez o'tadi)
Write-Host "[2/5] Kutubxonalar tekshirilmoqda..."
python -m pip install -q -r requirements.txt --disable-pip-version-check
python -m playwright install chromium | Out-Null

# 3) Cloudflare tunnel: ishlab turgan bo'lsa - o'sha manzil qoladi
Write-Host "[3/5] Cloudflare tunnel..."
$cfLog = Join-Path $PSScriptRoot "cloudflared.log"
$cfPidFile = Join-Path $PSScriptRoot "cloudflared.pid"
$url = $null
$tunnelAlive = $false
if ((Test-Path $cfPidFile) -and (Test-Path $cfLog)) {
    $tp = Get-Content $cfPidFile -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($tp -and (Get-Process -Id ([int]$tp) -ErrorAction SilentlyContinue)) {
        $m = Select-String -Path $cfLog -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($m -and (Test-Tunnel $m.Matches[0].Value)) { $url = $m.Matches[0].Value; $tunnelAlive = $true }
    }
}
if ($tunnelAlive) {
    Write-Host "      Tunnel ishlab turibdi - manzil o'zgarmaydi: $url" -ForegroundColor Green
} else {
    if (Test-Path $cfPidFile) {
        $tp = Get-Content $cfPidFile -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($tp) { Stop-Process -Id ([int]$tp) -Force -ErrorAction SilentlyContinue }
        Remove-Item $cfPidFile -Force -ErrorAction SilentlyContinue
    }
    if (Test-Path $cfLog) { Remove-Item $cfLog -Force -ErrorAction SilentlyContinue }
    $cf = Get-Command cloudflared -ErrorAction SilentlyContinue
    if (-not $cf) {
        Write-Host "cloudflared topilmadi. O'rnatish: winget install Cloudflare.cloudflared" -ForegroundColor Red
        Read-Host "Chiqish uchun Enter"
        exit 1
    }
    # alohida yashirin oynada - bot oynasi yopilsa ham tunnel ishlayveradi
    $tunnel = Start-Process -FilePath $cf.Source -ArgumentList "tunnel --url http://localhost:8080" `
        -RedirectStandardError $cfLog -RedirectStandardOutput "$cfLog.out" -WindowStyle Hidden -PassThru
    Set-Content -Path $cfPidFile -Value $tunnel.Id
    for ($i = 0; $i -lt 40; $i++) {
        Start-Sleep -Seconds 1
        if (Test-Path $cfLog) {
            $m = Select-String -Path $cfLog -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($m) { $url = $m.Matches[0].Value; break }
        }
    }
    if (-not $url) {
        Write-Host "Tunnel manzili olinmadi. cloudflared.log faylini tekshiring." -ForegroundColor Red
        Stop-Process -Id $tunnel.Id -Force -ErrorAction SilentlyContinue
        Read-Host "Chiqish uchun Enter"
        exit 1
    }
    Write-Host "      Yangi Mini App manzili: $url" -ForegroundColor Green
}

# 4) .env dagi WEBAPP_URL ni yangilash
Write-Host "[4/5] .env yangilanmoqda..."
python update_env.py $url

# 5) Bot
Write-Host "[5/5] Bot ishga tushdi. Bu oynani YOPMANG (yopsangiz bot to'xtaydi, tunnel esa ishlayveradi)." -ForegroundColor Cyan
Write-Host ""
while ($true) {
    python main.py
    if ($LASTEXITCODE -eq 0) { break }
    Write-Host ""
    Write-Host "Bot xato bilan to'xtadi (internet uzilgan bo'lishi mumkin). 10 soniyadan keyin qayta ishga tushiriladi... (to'xtatish: oynani yoping)" -ForegroundColor Yellow
    Start-Sleep -Seconds 10
}
Write-Host ""
Write-Host "Bot to'xtadi." -ForegroundColor Yellow
