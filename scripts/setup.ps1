param([string]$PythonPath)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
if (-not $PythonPath) {
    $bundled=Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
    $PythonPath=if(Test-Path -LiteralPath $bundled){$bundled}else{'python'}
}
if (-not(Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    & $PythonPath -m venv .venv
    if($LASTEXITCODE -ne 0){throw 'Python虚拟环境创建失败。'}
}
& '.\.venv\Scripts\python.exe' -m pip install -r requirements.lock
if($LASTEXITCODE -ne 0){throw '依赖安装失败。'}
Write-Output '安装完成。运行 scripts/run.ps1 collect，然后 scripts/run.ps1 serve。'
