<#
.SYNOPSIS
  PC에서 반다이남코코리아몰 목록을 읽어 docs/data/mall-scan.json "만" 커밋·push 한다. (작업 스케줄러가 하루 1번 호출)

.DESCRIPTION
  몰의 웹 방화벽이 GitHub Actions(클라우드 IP)를 막아서(Request Rejected) 몰 목록은 한국 IP인 이 PC에서 받는다.
  VPN·프록시·헤더 위장은 하지 않는다. 이 PC에서도 차단되면 mall-scan.json에 blocked:true만 기록한다(재시도·우회 없음).

  안전 규칙
  - 커밋은 `git commit -- docs/data/mall-scan.json`(경로 지정 커밋)이라 작업 중인 다른 파일이 staged 되어 있어도 절대 같이 들어가지 않는다.
    커밋 직후 HEAD가 이 파일 하나만 담았는지 다시 확인하고, 아니면 되돌리고(reset --soft) 중단한다.
  - 현재 브랜치가 main이 아니거나 rebase/merge 중이면 아무것도 하지 않고 로그만 남긴다(작업 중인 저장소를 건드리지 않는다).
  - 순서: 파이썬 실행 → mall-scan.json만 add/commit → git pull --rebase --autostash → git push (실패하면 1회 재시도)
  - 로그: crawler\out\mall_local.log (gitignore). 종료 코드: 0 정상(변경 없음 포함), 2 파이썬 못 찾음, 3 브랜치/상태로 건너뜀, 4 수집 실패,
    5 커밋 검사 실패, 6 pull/push 실패

.PARAMETER Python
  conda env `plamo`의 python.exe 경로. 비우면 환경변수 PLAMO_PYTHON, 그다음 흔한 conda 설치 위치에서 envs\plamo\python.exe를 찾는다.
  (Windows에서 `conda run`은 한글 출력을 깨뜨려 쓰지 않는다)

.PARAMETER NoPush
  커밋까지만 하고 push 하지 않는다(시험용).
#>
[CmdletBinding()]
param(
  [string]$RepoRoot = '',
  [string]$Python = $env:PLAMO_PYTHON,
  [string]$EnvName = 'plamo',
  [string]$Branch = 'main',
  [string]$Remote = 'origin',
  [switch]$NoPush
)

$ErrorActionPreference = 'Continue'
if (-not $RepoRoot) {       # 파라미터 기본값에서는 $PSScriptRoot 가 비는 경우가 있어(Windows PowerShell 5.1) 여기서 계산한다: scripts\ 의 부모 = 저장소 루트
  $self = $MyInvocation.MyCommand.Path
  $RepoRoot = Split-Path -Parent (Split-Path -Parent $self)
}
$ScanRel = 'docs/data/mall-scan.json'
$LogPath = Join-Path $RepoRoot 'crawler\out\mall_local.log'
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $LogPath) | Out-Null
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

function Log([string]$Message) {
  $line = '{0}  {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
  Add-Content -LiteralPath $LogPath -Value $line -Encoding UTF8
  Write-Host $line
}

# 로그가 너무 커지면 뒤쪽 2000줄만 남긴다
if ((Test-Path -LiteralPath $LogPath) -and ((Get-Item -LiteralPath $LogPath).Length -gt 512KB)) {
  $tail = Get-Content -LiteralPath $LogPath -Tail 2000 -Encoding UTF8
  Set-Content -LiteralPath $LogPath -Value $tail -Encoding UTF8
}

# git 실행: 출력은 로그에 남기고, 종료 코드는 $script:GitExit 에 둔다
function Invoke-Git([string[]]$GitArgs) {
  $out = & git -C $RepoRoot @GitArgs 2>&1 | ForEach-Object { "$_" }
  $script:GitExit = $LASTEXITCODE
  foreach ($l in $out) { if ($l) { Log ('  git {0}: {1}' -f $GitArgs[0], $l) } }
  return $out
}

function Test-GitBusy {
  $gd = (& git -C $RepoRoot rev-parse --git-dir 2>$null)
  if (-not $gd) { return 'git 저장소가 아님' }
  if (-not [System.IO.Path]::IsPathRooted($gd)) { $gd = Join-Path $RepoRoot $gd }
  foreach ($n in 'rebase-merge', 'rebase-apply', 'MERGE_HEAD', 'CHERRY_PICK_HEAD', 'REVERT_HEAD') {
    if (Test-Path -LiteralPath (Join-Path $gd $n)) { return "진행 중인 git 작업($n)이 있음" }
  }
  return $null
}

Log '=== 몰 수집(PC) 시작 ==='

# 1. 저장소 상태: main 이고 rebase/merge 중이 아닐 때만
$busy = Test-GitBusy
if ($busy) { Log "건너뜀: $busy"; exit 3 }
$cur = (& git -C $RepoRoot rev-parse --abbrev-ref HEAD 2>$null)
if ($cur -ne $Branch) { Log "건너뜀: 현재 브랜치가 '$cur' (필요: $Branch) — 작업 중인 브랜치는 건드리지 않습니다"; exit 3 }

# 2. 파이썬 (conda env plamo)
if (-not $Python) {
  $roots = @("$env:USERPROFILE\miniconda3", "$env:USERPROFILE\anaconda3", "$env:USERPROFILE\miniforge3", "$env:USERPROFILE\mambaforge",
             "$env:LOCALAPPDATA\miniconda3", "$env:LOCALAPPDATA\anaconda3", 'C:\ProgramData\miniconda3', 'C:\ProgramData\anaconda3')
  $conda = Get-Command conda -ErrorAction SilentlyContinue
  if ($conda) { $b = (& conda info --base 2>$null); if ($b) { $roots = @($b) + $roots } }
  foreach ($r in $roots) {
    $cand = Join-Path $r "envs\$EnvName\python.exe"
    if (Test-Path -LiteralPath $cand) { $Python = $cand; break }
  }
}
if (-not $Python -or -not (Test-Path -LiteralPath $Python)) {
  Log "중단: conda env '$EnvName'의 python.exe를 찾지 못했습니다. -Python 경로를 주거나 환경변수 PLAMO_PYTHON을 설정하세요"
  exit 2
}
Log "python: $Python"

# 3. 몰 목록 수집 → docs/data/mall-scan.json (카탈로그·mall.json은 건드리지 않는다)
Push-Location $RepoRoot
try {
  $out = & $Python main.py --only mall --mall-local 2>&1 | ForEach-Object { "$_" }
  $pyExit = $LASTEXITCODE
} finally { Pop-Location }
foreach ($l in $out) { if ($l) { Log "  py: $l" } }
if ($pyExit -ne 0) { Log "중단: main.py 종료 코드 $pyExit — 커밋하지 않습니다"; exit 4 }

# 4. mall-scan.json 만 add/commit (경로 지정 커밋: 다른 staged 파일은 절대 함께 커밋되지 않는다)
$st = Invoke-Git @('status', '--porcelain', '--', $ScanRel)
if (-not ($st | Where-Object { $_ })) { Log '변경 없음 — 커밋하지 않습니다'; exit 0 }
$null = Invoke-Git @('add', '--', $ScanRel)
$msg = 'data: mall scan {0}' -f (Get-Date -Format 'yyyy-MM-dd')
$null = Invoke-Git @('commit', '-m', $msg, '--', $ScanRel)
if ($script:GitExit -ne 0) { Log '중단: 커밋 실패'; exit 5 }
$files = @(& git -C $RepoRoot show --name-only --pretty=format: HEAD 2>$null | Where-Object { $_ })
if (($files.Count -ne 1) -or ($files[0] -ne $ScanRel)) {
  Log ('중단: 방금 커밋에 예상 밖의 파일이 있습니다: ' + ($files -join ', ') + ' — 커밋을 되돌립니다(reset --soft)')
  $null = Invoke-Git @('reset', '--soft', 'HEAD~1')
  exit 5
}
Log "커밋: $msg"
if ($NoPush) { Log '-NoPush: push 하지 않습니다'; exit 0 }

# 5. pull --rebase --autostash → push (실패하면 1회 재시도)
$pushed = $false
foreach ($attempt in 1, 2) {
  $null = Invoke-Git @('pull', '--rebase', '--autostash', $Remote, $Branch)
  if ($script:GitExit -ne 0) {
    if (Test-GitBusy) {                       # rebase 충돌 등 — 중단 상태로 두지 않는다
      Log "pull --rebase 실패($attempt/2) — rebase를 취소합니다"
      $null = Invoke-Git @('rebase', '--abort')
      continue
    }
    Log "경고: pull 이 0이 아닌 코드로 끝났습니다(autostash 복원 충돌일 수 있음 — 'git stash list' 확인). push 를 시도합니다"
  }
  $null = Invoke-Git @('push', $Remote, "HEAD:$Branch")
  if ($script:GitExit -eq 0) { $pushed = $true; break }
  Log "push 실패($attempt/2)"
}
if (-not $pushed) { Log '중단: push 에 실패했습니다 (커밋은 로컬에 남아 있어 다음 실행에서 함께 올라갑니다)'; exit 6 }
Log '=== 완료: push 됨 ==='
exit 0
