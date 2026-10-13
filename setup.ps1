<#
  Cahier - instalação no Windows.
  Uso: clique com o botão direito > "Executar com o PowerShell"
       ou: powershell -ExecutionPolicy Bypass -File setup.ps1 [-RunTests]
#>
param([switch]$RunTests)
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

function Find-Python {
    # Devolve o comando (exe + argumentos) de um Python 3.10+.
    foreach ($candidate in @("py -3", "python", "python3")) {
        $parts = $candidate.Split(" ")
        $exe = $parts[0]
        $extra = @()
        if ($parts.Length -gt 1) { $extra = $parts[1..($parts.Length - 1)] }
        if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
        try {
            $ver = & $exe @extra -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        } catch { continue }
        if ($LASTEXITCODE -eq 0 -and $ver) {
            $v = "$ver".Trim().Split(".")
            if ([int]$v[0] -eq 3 -and [int]$v[1] -ge 10) {
                return [pscustomobject]@{ Exe = $exe; Args = $extra }
            }
        }
    }
    return $null
}

Write-Host "== Cahier: instalação ==" -ForegroundColor Cyan
$py = Find-Python
if (-not $py) {
    Write-Host "Python 3.10 ou mais recente não foi encontrado." -ForegroundColor Red
    Write-Host "Instale em https://www.python.org/downloads/ (marque 'Add python.exe to PATH') e rode este script de novo."
    exit 1
}
$pyExe = $py.Exe; $pyArgs = $py.Args
Write-Host ("Usando Python: " + (& $pyExe @pyArgs --version))

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Criando ambiente virtual (.venv)..."
    & $pyExe @pyArgs -m venv .venv
}
$venvPy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

Write-Host "Instalando dependências..."
& $venvPy -m pip install --upgrade pip --quiet --disable-pip-version-check
& $venvPy -m pip install -r requirements.txt --quiet --disable-pip-version-check
if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar as dependências." }

if (-not (Test-Path ".env")) {
    Write-Host "Criando .env com uma chave secreta nova..."
    $key = & $venvPy -c "import secrets; print(secrets.token_urlsafe(50))"
    (Get-Content ".env.example" -Encoding UTF8) -replace "^CAHIER_SECRET_KEY=.*", "CAHIER_SECRET_KEY=$key" |
        Set-Content ".env" -Encoding UTF8
}

Write-Host "Preparando o banco de dados..."
& $venvPy manage.py migrate --noinput
if ($LASTEXITCODE -ne 0) { throw "Falha nas migrations." }
& $venvPy manage.py seed_content
if ($LASTEXITCODE -ne 0) { throw "Falha ao carregar o conteúdo inicial." }
& $venvPy manage.py validate_content | Select-Object -Last 1

if ($RunTests) {
    Write-Host "Rodando os testes automatizados..."
    & $venvPy manage.py test tests
    if ($LASTEXITCODE -ne 0) { throw "Alguns testes falharam." }
}

Write-Host ""
Write-Host "Instalação concluída!" -ForegroundColor Green
Write-Host "Para começar a estudar, rode run.ps1 (ou dê dois cliques em Iniciar.bat)."
