<#
    chay.ps1 - mot lenh duy nhat de chay he thong.

    File nay chi ASCII (khong dau) co y: Windows PowerShell 5.1 doc file .ps1
    bang codepage he thong khi file khong co BOM, nen chu tieng Viet co dau se
    hien ra thanh rac. Giai thich day du de trong README/QUY_TAC_THIET_KE.md.

    Vi sao can:
      1. Quen kich hoat venv la loi hay gap nhat - da gay ra 4 loi khac nhau
         trong mot buoi lam (xem TRUOC_KHI_CHAY.md, Phan 1). Script tu kich hoat.
      2. Research Agent nay tra loi bang TIENG VIET. Console Windows mac dinh
         khong chay UTF-8, nen chu co dau bi vo hoac nem UnicodeEncodeError.
         Script bat UTF-8 truoc khi goi python.

    Cach dung:
      .\chay.ps1 "machine learning la gi?"        # qua supervisor (~5 luot LLM)
      .\chay.ps1 -r "rotary positional encoding"  # thang research agent (~4 luot Groq)
      .\chay.ps1 -v "May con cho trong anh? .\assets\dogs.jpg"   # thang vision agent
      .\chay.ps1 -Agent ten_agent "cau hoi"       # bat ky agent nao trong registry
      .\chay.ps1 -Test                            # pytest, khong ton luot nao
      .\chay.ps1 -Config                          # xem 5 vai tro / 5 model / 2 key
      .\chay.ps1 -Models                          # model ma key cua ban dung duoc
      .\chay.ps1 -Graph                           # in state graph (mermaid)

    Bao "running scripts is disabled"? Chay mot lan trong cua so nay:
      Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#>

# PositionalBinding = $false: khong co no thi $Agent (string, khong danh dau
# vi tri) am tham "nuot" cau hoi lam tham so vi tri dau tien cua no, con
# $CauHoi (ValueFromRemainingArguments) nhan duoc mang RONG -> luon bao
# "Thieu cau hoi" du go dung cu phap. Da kiem chung bang script test rieng.
[CmdletBinding(PositionalBinding = $false)]
param(
    [Alias('r')][switch]$Research,
    [Alias('v')][switch]$Vision,
    [string]$Agent = '',
    [switch]$Test,
    [switch]$Config,
    [switch]$Models,
    [switch]$Graph,
    [switch]$Quiet,
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$CauHoi
)

$ErrorActionPreference = 'Stop'
$Repo = $PSScriptRoot
Set-Location $Repo

# --- 1. UTF-8 cho console + cho python -------------------------------------
# Ba thu nay phai lam ca ba, thieu cai nao cung con vo chu o mot cho khac.
$null = chcp 65001
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

# --- 2. Xac dinh python cua venv -------------------------------------------
$PyExe    = Join-Path $Repo '.venv\Scripts\python.exe'

if (-not (Test-Path $PyExe)) {
    Write-Host "Khong thay .venv trong $Repo" -ForegroundColor Red
    Write-Host "Tao truoc bang dung Python 3.11:" -ForegroundColor Yellow
    Write-Host "    py -3.11 -m venv .venv"
    Write-Host "    .\.venv\Scripts\python.exe -m pip install -r requirements.txt"
    exit 1
}

# KHONG dot-source Activate.ps1: goi thang .venv\Scripts\python.exe la tuong
# duong khi chay 'python -m ...', lai khong phu thuoc ExecutionPolicy va khong
# the chay nham Python he thong. Doi lai dau dong lenh se KHONG hien '(.venv)' -
# khong sao, vi script luon dung dung python trong .venv.

# --- 3. Canh bao som thay vi de python nem traceback ------------------------
if (-not (Test-Path (Join-Path $Repo '.env')) -and -not $Test) {
    Write-Host "Chua co file .env - copy tu .env.example roi dien 2 key:" -ForegroundColor Yellow
    Write-Host "    Copy-Item .env.example .env; notepad .env"
    Write-Host ""
}

# --- 4. Dung lenh -----------------------------------------------------------
if ($Test) {
    Write-Host "pytest -m 'not network' (khong ton luot API nao)" -ForegroundColor Cyan
    & $PyExe -m pytest -q -m "not network"
    exit $LASTEXITCODE
}

$PyArgs = @('-m', 'app.main')
if ($Config)   { $PyArgs += '--config' }
if ($Models)   { $PyArgs += '--models' }
if ($Graph)    { $PyArgs += '--graph'  }
if ($Quiet)    { $PyArgs += '--quiet'  }
# -Agent nhan ten bat ky trong registry, nen them agent thu 4 KHONG phai sua
# script nay (dung tinh than quy tac IF-09). -r / -v chi la loi tat hay dung.
if ($Research) { $Agent = 'research_agent' }
if ($Vision)   { $Agent = 'vision_agent' }
if ($Agent)    { $PyArgs += @('--agent', $Agent) }

if ($CauHoi) { $PyArgs += ($CauHoi -join ' ') }

if (-not ($Config -or $Models -or $Graph) -and -not $CauHoi) {
    Write-Host "Thieu cau hoi. Vi du:" -ForegroundColor Yellow
    Write-Host '    .\chay.ps1 -r "rotary positional encoding"'
    Write-Host '    .\chay.ps1 -Config     # xem cau hinh, khong ton luot nao'
    exit 1
}

& $PyExe @PyArgs
exit $LASTEXITCODE
