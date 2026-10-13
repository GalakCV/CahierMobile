<#
  Cahier - cria um backup datado do banco em data\backups\
  Uso: powershell -ExecutionPolicy Bypass -File backup.ps1 [-Label "antes-da-viagem"]
  Pode rodar com o servidor aberto (a cópia é consistente).
#>
param([string]$Label = "manual")
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot
$venvPy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Write-Host "O Cahier ainda não foi instalado. Rode setup.ps1 primeiro." -ForegroundColor Red
    exit 1
}
& $venvPy manage.py backup_db --label $Label
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Backups disponíveis:"
Get-ChildItem "data\backups\cahier-*.sqlite3" | Sort-Object Name -Descending | Select-Object -First 5 Name, Length
