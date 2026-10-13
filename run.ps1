<#
  Cahier - inicia o servidor local e abre o navegador em http://localhost:8000
  Uso: powershell -ExecutionPolicy Bypass -File run.ps1 [-NoBrowser] [-Port 8000]
#>
param([switch]$NoBrowser, [int]$Port = 0)
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot
$venvPy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Write-Host "O Cahier ainda não foi instalado. Rode setup.ps1 primeiro." -ForegroundColor Red
    exit 1
}
$launchArgs = @("launch.py")
if ($NoBrowser) { $launchArgs += "--no-browser" }
if ($Port -gt 0) { $launchArgs += @("--port", "$Port") }
& $venvPy @launchArgs
