# สร้าง Cafe-WiFi OS บน Windows ด้วย Docker Desktop (M3) -- ผลอยู่ที่ image\deploy\
#   powershell -ExecutionPolicy Bypass -File image\build.ps1            # build เต็ม
#   powershell -ExecutionPolicy Bypass -File image\build.ps1 -Reuse     # ใช้ stage0-2 จากรอบก่อน (แก้แค่ stage ของเรา)
# build จาก commit ปัจจุบัน (git archive HEAD) ไม่ใช่ working tree -- ของที่ยังไม่ commit ไม่ติดไป
#   powershell -ExecutionPolicy Bypass -File image\build.ps1 -Reuse -Fast   # build ทดสอบ: .img ไม่บีบอัด (~15 นาที)
param([switch]$Reuse, [switch]$Fast)
$ErrorActionPreference = 'Stop'
$dockerBin = 'C:\Program Files\Docker\Docker\resources\bin'
if (Test-Path $dockerBin) { $env:Path = "$dockerBin;$env:Path" }

$repo = (Resolve-Path "$PSScriptRoot\..").Path
$out  = Join-Path $PSScriptRoot 'deploy'
New-Item -ItemType Directory -Force $out | Out-Null

if (git -C $repo status --porcelain) {
    Write-Warning 'มีไฟล์ที่ยังไม่ commit -- จะไม่ติดไปกับ image (build จาก HEAD)'
}
$hash = (git -C $repo rev-parse --short HEAD).Trim()
git -C $repo archive --format=tar -o "$out\src.tar" HEAD
if ($LASTEXITCODE -ne 0) { throw 'git archive ล้มเหลว' }

$reuseFlag = if ($Reuse) { '1' } else { '0' }
$fastFlag = if ($Fast) { '1' } else { '0' }
Write-Host "==> build Cafe-WiFi OS จาก $hash (reuse=$reuseFlag fast=$fastFlag)"
docker run --rm --privileged --platform linux/amd64 `
    -v cafewifi-pigen-work:/work `
    -v "${out}:/out" `
    -e CAFEWIFI_GIT=$hash -e CAFEWIFI_REUSE=$reuseFlag -e CAFEWIFI_FAST=$fastFlag `
    debian:trixie-slim `
    bash -c 'set -e; mkdir -p /cafewifi/src; tar -xf /out/src.tar -C /cafewifi/src; bash /cafewifi/src/image/build.sh'
if ($LASTEXITCODE -ne 0) { throw "build ล้มเหลว (ดู $out\build.log)" }
Remove-Item "$out\src.tar"
Get-ChildItem $out -Filter "*$hash*" | Format-Table Name, Length
