param(
    [string]$Version,
    [string]$OutputDir = "release",
    [string]$NamePrefix = "RewrZ"
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$pythonExe = Join-Path $repoRoot ".venv\\Scripts\\python.exe"

if (-not (Test-Path $pythonExe)) {
    $pythonExe = "python"
}

$scriptPath = Join-Path $PSScriptRoot "build_release_package.py"
$arguments = @($scriptPath, "--output-dir", $OutputDir, "--name-prefix", $NamePrefix)

if ($Version) {
    $arguments += @("--version", $Version)
}

& $pythonExe @arguments

if ($LASTEXITCODE -ne 0) {
    throw "发布包生成失败，请先检查上面的错误输出。"
}
