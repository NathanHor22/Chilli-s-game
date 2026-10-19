[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython)) { throw "Run setup.ps1 first." }
if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot "models\pose_landmarker_lite.task"))) {
    throw "The pose model is missing. Run setup.ps1 first."
}
& $venvPython -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw "Build dependency installation failed." }
& $venvPython -m PyInstaller --noconfirm ChilliShimmy.spec
if ($LASTEXITCODE -ne 0) { throw "Executable build failed." }
$bundleDirectory = Join-Path $PSScriptRoot "dist\ChilliShimmy"
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "config.json") -Destination $bundleDirectory
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "README.md") -Destination $bundleDirectory
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "THIRD_PARTY.md") -Destination $bundleDirectory
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "Run Game.cmd") -Destination $bundleDirectory
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "Run Demo.cmd") -Destination $bundleDirectory
Write-Host "Built dist\ChilliShimmy\ChilliShimmy.exe. Copy the ENTIRE ChilliShimmy folder to the installation PC."
