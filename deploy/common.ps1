# Shared by the Windows deploy scripts (common.sh's twin): paths and deploy\.env. Dot-sourced, not run.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Turbo = Join-Path $Root 'vendor\turbo-cloud'
$Nitro = Join-Path $Root 'vendor\nitro-next'
$Plugin = Join-Path $Root 'turbo-plugin'

# deploy\.env is read as data, one KEY=value per line, never run as code. Only WB_* keys are taken;
# surrounding spaces and one pair of quotes are dropped. A value already in the environment wins.
function Import-WbEnv([string] $File) {
    if (-not (Test-Path -LiteralPath $File -PathType Leaf)) { return }

    foreach ($raw in Get-Content -LiteralPath $File) {
        $line = $raw.TrimEnd("`r")
        if ($line -eq '' -or $line.StartsWith('#')) { continue }

        $eq = $line.IndexOf('=')
        $key = if ($eq -ge 0) { $line.Substring(0, $eq) -replace '\s', '' } else { '' }

        if ($eq -lt 0 -or $key -cnotmatch '^WB_[A-Z0-9_]+$') {
            Write-Warning "deploy/.env: skipped a line that is not WB_NAME=value: $line"
            continue
        }

        $value = $line.Substring($eq + 1).Trim()
        if ($value.Length -ge 2 -and (($value[0] -eq '"' -and $value[-1] -eq '"') -or ($value[0] -eq "'" -and $value[-1] -eq "'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }

        if (-not [Environment]::GetEnvironmentVariable($key)) {
            [Environment]::SetEnvironmentVariable($key, $value)
        }
    }
}

Import-WbEnv (Join-Path $Root 'deploy\.env')

function Assert-Command([string] $Name, [string] $Hint) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) { throw "Needs ${Name}: $Hint" }
}

# A path setting that is set must name something that exists, or the script stops here: Turbo
# would otherwise start on a wrong path (a new 400 MB asset download into it, for one).
function Assert-PathSetting([string] $Name, [ValidateSet('file', 'dir')] [string] $Kind) {
    $value = [Environment]::GetEnvironmentVariable($Name)
    if (-not $value) { return }

    $type = if ($Kind -eq 'file') { 'Leaf' } else { 'Container' }
    if (-not (Test-Path -LiteralPath $value -PathType $type)) {
        throw "$Name is not an existing ${Kind}: '$value' (check deploy/.env)"
    }
}

# Runs a program and stops the script when it fails, as `set -e` does for the bash scripts. A plain
# function, so arguments such as -C reach the program instead of being read as this function's.
function Invoke-Checked {
    $file, $rest = $args
    & $file @rest
    if ($LASTEXITCODE -ne 0) { throw "$file $($rest -join ' ') failed with exit code $LASTEXITCODE" }
}
