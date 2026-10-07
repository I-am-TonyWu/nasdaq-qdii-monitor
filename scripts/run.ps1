param(
    [ValidateSet('serve','collect','funds','retry','forward','freeze','report','send','backup','status','weekly')]
    [string]$Command='serve',
    [switch]$Hidden
)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
$pythonPath=Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw '请先运行 scripts/setup.ps1 安装项目依赖。' }
Set-Location -LiteralPath $projectRoot
if ($Hidden) {
    $logRoot=Join-Path $projectRoot 'logs'
    New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
    $started=Start-Process -FilePath $pythonPath -ArgumentList @('-X','utf8','-m','app.cli',$Command) -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logRoot "$Command.stdout.log") -RedirectStandardError (Join-Path $logRoot "$Command.stderr.log")
    Write-Output "已启动 $Command，PID $($started.Id)。"
} else {
    & $pythonPath -X utf8 -m app.cli $Command
    if ($LASTEXITCODE -ne 0) { throw "项目命令失败：$Command" }
}
