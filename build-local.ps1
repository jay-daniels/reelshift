# ReelShift - local Windows build (no GitHub Actions needed).
# Run with .\build-local.cmd or powershell -ExecutionPolicy Bypass -File .\build-local.ps1
[CmdletBinding()]
param(
    [switch]$SkipTests,
    [switch]$OpenOutput
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
Set-Location -LiteralPath $root
$venvPython = Join-Path $root '.venv\Scripts\python.exe'
$exe = Join-Path $root 'dist\ReelShift.exe'

function Run-Python([string[]]$Arguments) {
    & $venvPython @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Python-Befehl fehlgeschlagen (Exitcode $LASTEXITCODE): python $($Arguments -join ' ')"
    }
}

try {
    Write-Host ''
    Write-Host '=== ReelShift: Lokaler Windows-Build ===' -ForegroundColor Cyan
    Write-Host 'Keine GitHub Actions. Build findet ausschliesslich auf diesem PC statt.'

    if (-not (Test-Path -LiteralPath $venvPython)) {
        $created = $false
        $launcher = Get-Command py -ErrorAction SilentlyContinue
        if ($launcher) {
            foreach ($version in @('-3.10', '-3.12', '-3.11', '-3.13', '-3.14', '-3')) {
                try {
                    & py $version -c 'import sys' 2>$null
                    if ($LASTEXITCODE -ne 0) { continue }
                }
                catch { continue }
                Write-Host "Python Launcher ${version}: erstelle .venv ..."
                & py $version -m venv (Join-Path $root '.venv')
                if ($LASTEXITCODE -ne 0) { throw 'Python konnte keine virtuelle Umgebung anlegen.' }
                $created = $true
                break
            }
        }
        if (-not $created) {
            $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
            if (-not $pythonCmd) {
                throw 'Python fehlt. Installiere Python 3.10+ von python.org und starte erneut.'
            }
            Write-Host 'Erstelle .venv mit python ...'
            & python -m venv (Join-Path $root '.venv')
            if ($LASTEXITCODE -ne 0) { throw 'Python konnte keine virtuelle Umgebung anlegen.' }
        }
    }
    if (-not (Test-Path -LiteralPath $venvPython)) {
        throw 'Die virtuelle Python-Umgebung wurde nicht angelegt.'
    }

    Write-Host '[1/4] Python-Version pruefen ...' -ForegroundColor Cyan
    Run-Python @('-c', 'import sys; assert sys.version_info >= (3,10), "Python 3.10 oder neuer ist erforderlich"; print(sys.version)')

    Write-Host '[2/4] Projekt und PyInstaller installieren/aktualisieren ...' -ForegroundColor Cyan
    Run-Python @('-m', 'pip', 'install', '--disable-pip-version-check', '-e', '.', 'pyinstaller>=6,<7', 'pillow>=11,<13')

    if (-not $SkipTests) {
        Write-Host '[3/4] Unit-Tests ...' -ForegroundColor Cyan
        Run-Python @('-m', 'unittest', 'discover', '-s', 'tests', '-v')
    } else {
        Write-Host '[3/4] Tests uebersprungen (-SkipTests)' -ForegroundColor Yellow
    }

    Write-Host '[4/4] Icon erzeugen und ReelShift.exe bauen ...' -ForegroundColor Cyan
    Run-Python @((Join-Path $root 'tools\make_icon.py'))
    $iconPath = Join-Path $root 'assets\reelshift.ico'
    if (-not (Test-Path -LiteralPath $iconPath)) { throw 'App-Icon konnte nicht erstellt werden.' }
    $iconBundle = "$($iconPath);assets"
    $pyInstallerArgs = @('-m', 'PyInstaller', '--noconfirm', '--onefile', '--windowed',
              '--name', 'ReelShift',
              '--icon', $iconPath,
              '--add-data', $iconBundle,
              '--distpath', (Join-Path $root 'dist'),
              '--workpath', (Join-Path $root 'build\pyinstaller'),
              '--specpath', (Join-Path $root 'build'),
              (Join-Path $root 'run.py'))
    Run-Python $pyInstallerArgs

    if (-not (Test-Path -LiteralPath $exe)) { throw 'Build meldete Erfolg, aber die EXE fehlt.' }
    $mb = [math]::Round((Get-Item -LiteralPath $exe).Length / 1MB, 1)
    Write-Host ''
    Write-Host "ERFOLG: $exe ($mb MB)" -ForegroundColor Green
    Write-Host 'FFmpeg/FFprobe werden weiterhin separat benoetigt (PATH oder Auswahl in der GUI).'
    if ($OpenOutput) { Start-Process explorer.exe -ArgumentList ('"' + (Join-Path $root 'dist') + '"') }
    exit 0
}
catch {
    Write-Host ''
    Write-Host "BUILD FEHLGESCHLAGEN: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host 'Pruefe die Ausgabe oben. Bei Pip-Fehlern: Python/PATH/Internet pruefen.'
    exit 1
}
