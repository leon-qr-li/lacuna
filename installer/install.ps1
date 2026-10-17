# LACUNA installer for Windows. Double-click LACUNA-Setup.cmd, or paste into PowerShell:
#   irm https://github.com/leon-qr-li/lacuna/releases/latest/download/install.ps1 | iex
# Installs into %LOCALAPPDATA%\LACUNA (no admin rights), creates Desktop + Start menu shortcuts and
# starts LACUNA. Run it again any time to repair. The workspace is never touched.
# Overrides (tests / offline): LACUNA_RELEASE_BASE (URL or folder), LACUNA_ROOT, LACUNA_WORKSPACE,
# LACUNA_NO_START=1, LACUNA_NO_SHORTCUTS=1.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$UvVersion = '0.11.32'
$Base = if ($env:LACUNA_RELEASE_BASE) { $env:LACUNA_RELEASE_BASE } else { 'https://github.com/leon-qr-li/lacuna/releases/latest/download' }
$Root = if ($env:LACUNA_ROOT) { $env:LACUNA_ROOT } else { Join-Path $env:LOCALAPPDATA 'LACUNA' }

function Fetch($Src, $Dst) {
  if ($Src -match '^https?://') { Invoke-WebRequest -UseBasicParsing -Uri $Src -OutFile $Dst }
  elseif ($Src -match '^file:///') { Copy-Item ([Uri]$Src).LocalPath $Dst }
  else { Copy-Item $Src $Dst }
}

Write-Host "==> LACUNA -> $Root"
New-Item -ItemType Directory -Force -Path (Join-Path $Root 'bin') | Out-Null
$Uv = Join-Path $Root 'bin\uv.exe'
if (-not (Test-Path $Uv)) {
  Write-Host "==> uv $UvVersion"
  $Tmp = Join-Path ([IO.Path]::GetTempPath()) ("lacuna-uv-" + [Guid]::NewGuid())
  New-Item -ItemType Directory -Force -Path $Tmp | Out-Null
  $Zip = Join-Path $Tmp 'uv.zip'
  Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/astral-sh/uv/releases/download/$UvVersion/uv-x86_64-pc-windows-msvc.zip" -OutFile $Zip
  Expand-Archive -Path $Zip -DestinationPath $Tmp -Force
  $Found = Get-ChildItem -Path $Tmp -Recurse -Filter 'uv.exe' | Select-Object -First 1
  Copy-Item $Found.FullName $Uv
  Remove-Item -Recurse -Force $Tmp
}

$Launcher = Join-Path $Root 'lacuna_launcher.py.new'
Fetch "$Base/lacuna_launcher.py" $Launcher

$env:UV_PYTHON_INSTALL_DIR = Join-Path $Root 'python'
$env:UV_CACHE_DIR = Join-Path $Root 'cache'
$env:UV_LINK_MODE = 'copy'
$env:PYTHONUTF8 = '1'
Remove-Item Env:VIRTUAL_ENV -ErrorAction SilentlyContinue
Write-Host "==> Python 3.12"
& $Uv run --no-project --python 3.12 python $Launcher install --root $Root --base $Base
$Status = $LASTEXITCODE
Remove-Item -Force $Launcher -ErrorAction SilentlyContinue
if ($Status -ne 0) { throw "LACUNA install failed ($Status)" }
