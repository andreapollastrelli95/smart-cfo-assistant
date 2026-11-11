# Installazione / riparazione di Smart CFO Assistant:
# crea il virtual environment, installa le dipendenze, genera l'icona e il collegamento sul Desktop.
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$venv = Join-Path $root ".venv"

# Python x64: le librerie cloud (cryptography, pydantic-core) non hanno wheel per Windows ARM64.
$python = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "Installo Python 3.12 (x64)..."
    winget install -e --id Python.Python.3.12 --scope user --architecture x64 --silent `
        --accept-package-agreements --accept-source-agreements
}

if (-not (Test-Path "$venv\Scripts\python.exe")) {
    Write-Host "Creo il virtual environment in $venv ..."
    & $python -m venv $venv
}
$vpy = "$venv\Scripts\python.exe"
& $vpy -m pip install --upgrade pip --quiet
& $vpy -m pip install -r (Join-Path $root "requirements.txt") --quiet
& $vpy (Join-Path $root "make_icon.py")

$desktop = [Environment]::GetFolderPath("Desktop")
$shell = New-Object -ComObject WScript.Shell
$lnk = $shell.CreateShortcut((Join-Path $desktop "Smart CFO Assistant.lnk"))
$lnk.TargetPath = "$venv\Scripts\pythonw.exe"
$lnk.Arguments = "`"$root\main.py`""
$lnk.WorkingDirectory = $root
$lnk.IconLocation = "$root\assets\smartcfo.ico,0"
$lnk.Description = "Smart CFO Assistant - Contabilita, Bilancio, Controllo di Gestione e Finanza"
$lnk.Save()
Write-Host "Collegamento creato sul Desktop. Installazione completata."
