param([switch]$SkipInstaller)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
$version = (Select-String -LiteralPath 'island/__init__.py' -Pattern '^__version__ = "([0-9.]+)"').Matches[0].Groups[1].Value
if ($version -notmatch '^\d+\.\d+\.\d+$') { throw 'Invalid version' }
if ($env:GITHUB_REF_TYPE -eq 'tag' -and $env:GITHUB_REF_NAME -ne "v$version") { throw 'Tag and application version do not match' }
New-Item -ItemType Directory -Force -Path 'build','dist/release' | Out-Null
$parts = ($version.Split('.') + '0') -join ', '
@"
VSVersionInfo(ffi=FixedFileInfo(filevers=($parts), prodvers=($parts), mask=0x3f, flags=0, OS=0x40004, fileType=1, subtype=0, date=(0,0)),
 kids=[StringFileInfo([StringTable('040904B0', [StringStruct('CompanyName','BochkaPiva'),
 StringStruct('ProductName','Cloud Island'), StringStruct('FileDescription','Cloud Island for Windows'),
 StringStruct('FileVersion','$version'), StringStruct('ProductVersion','$version'),
 StringStruct('OriginalFilename','CloudIsland.exe')])]), VarFileInfo([VarStruct('Translation',[1033,1200])])])
"@ | Set-Content -LiteralPath 'build/version_info.txt' -Encoding utf8
python tools/collect_licenses.py
if ($LASTEXITCODE -ne 0) { throw 'Notice collection failed' }
python -m PyInstaller --noconfirm --distpath dist --workpath build/pyinstaller packaging/cloud-island.spec
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }
$test = Start-Process -FilePath (Join-Path $root 'dist/CloudIsland.exe') -ArgumentList @('--self-test', ('"'+(Join-Path $root 'build/packaged-check.json')+'"')) -WindowStyle Hidden -PassThru
if (-not $test.WaitForExit(30000)) { throw 'Packaged self-test timeout' }
if ($test.ExitCode -ne 0) { throw 'Packaged self-test failed' }
Copy-Item -LiteralPath 'dist/CloudIsland.exe' -Destination 'dist/release/CloudIsland.exe' -Force
$stage = Join-Path $root 'build/portable'
New-Item -ItemType Directory -Force -Path $stage | Out-Null
Copy-Item -LiteralPath 'dist/CloudIsland.exe','LICENSE','THIRD_PARTY.md' -Destination $stage -Force
Copy-Item -LiteralPath 'build/licenses' -Destination $stage -Recurse -Force
Compress-Archive -Path "$stage/*" -DestinationPath "dist/release/CloudIsland-$version-win-x64.zip" -Force
git archive --format=zip --prefix=CloudIsland-Source/ -o "dist/release/CloudIsland-$version-source.zip" HEAD
if ($LASTEXITCODE -ne 0) { throw 'Source archive failed' }
if (-not $SkipInstaller) {
    $iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (-not $iscc) { throw 'Inno Setup 6 not installed. Install JRSoftware.InnoSetup or use -SkipInstaller.' }
    & $iscc "/DAppVersion=$version" 'packaging/installer.iss'
    if ($LASTEXITCODE -ne 0) { throw 'Installer build failed' }
    Copy-Item -LiteralPath "packaging/Output/CloudIsland-Setup-$version-win-x64.exe" -Destination 'dist/release' -Force
}
$checksums = Get-ChildItem -LiteralPath 'dist/release' -File | Where-Object Name -ne 'SHA256SUMS.txt' | Sort-Object Name | ForEach-Object {
    $hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    "$hash  $($_.Name)"
}
$checksums | Set-Content -LiteralPath 'dist/release/SHA256SUMS.txt' -Encoding ascii
Write-Host "Cloud Island $version: dist/release"
