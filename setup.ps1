[CmdletBinding()]
param([string]$Python = "")

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

function Test-SupportedPython {
    param([string]$Executable, [string[]]$PrefixArguments = @())
    try {
        & $Executable @PrefixArguments -c "import sys,struct; assert sys.version_info[:2] == (3,11) and struct.calcsize('P') == 8" *> $null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    if ($Python) {
        if (-not (Test-SupportedPython -Executable $Python)) {
            throw "The supplied -Python must run Python 3.11 64-bit: $Python"
        }
        & $Python -m venv .venv
    } else {
        $launcherCommand = Get-Command py -ErrorAction SilentlyContinue
        $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
        if ($launcherCommand -and (Test-SupportedPython -Executable $launcherCommand.Source -PrefixArguments @("-3.11"))) {
            & $launcherCommand.Source -3.11 -m venv .venv
        } elseif ($pythonCommand -and (Test-SupportedPython -Executable $pythonCommand.Source)) {
            & $pythonCommand.Source -m venv .venv
        } else {
            throw "Install Python 3.11 64-bit, or supply -Python with its full path. Neither py -3.11 nor python found a supported interpreter."
        }
    }
    if ($LASTEXITCODE -ne 0) { throw "Could not create .venv." }
}

& $venvPython -c "import sys,struct; assert sys.version_info[:2] == (3,11) and struct.calcsize('P') == 8, 'The existing .venv must use Python 3.11 64-bit'"
if ($LASTEXITCODE -ne 0) { throw "Use a Python 3.11 64-bit virtual environment." }
& $venvPython -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed. Check internet access and rerun setup.ps1." }
& $venvPython tools\download_model.py
if ($LASTEXITCODE -ne 0) { throw "Model download failed. Rerun setup.ps1 when internet access is available." }
Write-Host "Setup complete. Double-click 'Run Demo.cmd' or 'Run Game.cmd'."
