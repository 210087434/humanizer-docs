$ErrorActionPreference = "Stop"
$RootDir = Split-Path $PSScriptRoot -Parent
$BuildDir = Join-Path $PSScriptRoot "build"
$StageDir = Join-Path $BuildDir "payload"
$DistDir = Join-Path $BuildDir "dist"
$PayloadZip = Join-Path $BuildDir "payload.zip"
$InstallerPath = Join-Path $PSScriptRoot "HumanizeHelperSetup.exe"
$PyInstallerWorkDir = Join-Path $env:TEMP "HumanizeHelper-PyInstaller-work"
$Python = (Get-Command python -ErrorAction Stop).Source
$Csc = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"

if (!(Test-Path $Csc)) {
    throw "The .NET Framework C# compiler was not found at $Csc."
}

& $Python -m pip install -r (Join-Path $PSScriptRoot "requirements-build.txt")
if ($LASTEXITCODE -ne 0) {
    throw "Could not install the installer build dependency."
}

$PyInstallerArgs = @(
    "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
    "--name", "HumanizeHelper",
    "--paths", $RootDir,
    "--add-binary", "$RootDir\desktop_app\word_com_helper.exe;.",
    "--distpath", $DistDir,
    "--workpath", $PyInstallerWorkDir,
    "--specpath", $BuildDir,
    (Join-Path $RootDir "desktop_app\app.py")
)
& $Python @PyInstallerArgs
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller could not build HumanizeHelper.exe."
}

if (Test-Path $StageDir) {
    Remove-Item -LiteralPath $StageDir -Recurse -Force
}
New-Item -ItemType Directory -Path $StageDir | Out-Null
Copy-Item -LiteralPath (Join-Path $DistDir "HumanizeHelper.exe") -Destination $StageDir
Copy-Item -LiteralPath (Join-Path $RootDir "desktop_app\word_com_helper.exe") -Destination $StageDir

$ExtensionStage = Join-Path $StageDir "browser_extension"
New-Item -ItemType Directory -Path $ExtensionStage | Out-Null
Get-ChildItem -LiteralPath (Join-Path $RootDir "browser_extension") -File |
    Where-Object { $_.Name -notin @("config.js", "config.example.js", "page_guard.js") } |
    Copy-Item -Destination $ExtensionStage

if (Test-Path $PayloadZip) {
    Remove-Item -LiteralPath $PayloadZip -Force
}
& $Python (Join-Path $PSScriptRoot "package_payload.py") $StageDir $PayloadZip
if ($LASTEXITCODE -ne 0) {
    throw "Could not create the installer payload archive."
}

& $Csc /nologo /target:winexe /platform:anycpu `
    "/out:$InstallerPath" `
    /reference:System.Windows.Forms.dll `
    /reference:System.Drawing.dll `
    /reference:System.Management.dll `
    /reference:System.IO.Compression.dll `
    /reference:System.IO.Compression.FileSystem.dll `
    "/resource:$PayloadZip,payload.zip" `
    (Join-Path $PSScriptRoot "SetupWizard.cs")
if ($LASTEXITCODE -ne 0) {
    throw "Could not compile the setup wizard."
}

Write-Host "Built installer: $InstallerPath"
