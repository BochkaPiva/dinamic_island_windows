param([switch]$SkipInstaller, [switch]$ForSale)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Split-Path -Parent $PSScriptRoot)).Path
Set-Location -LiteralPath $root
python tools/release_readiness.py $(if ($ForSale) { '--sales' } else { '--candidate' })
if ($LASTEXITCODE -ne 0) { throw 'Release readiness check failed' }
$version = (Select-String -LiteralPath 'island/__init__.py' -Pattern '^__version__ = "([0-9.]+)"').Matches[0].Groups[1].Value
if ($version -notmatch '^\d+\.\d+\.\d+$') { throw 'Invalid version' }
# Never mix a candidate with previous assets or accidentally publish a source ZIP.
$release = [IO.Path]::GetFullPath((Join-Path $root 'dist/release'))
if ((Split-Path -Parent (Split-Path -Parent $release)) -ne $root -or (Split-Path -Leaf $release) -ne 'release') { throw 'Unsafe release path' }
if (Test-Path -LiteralPath $release) { Remove-Item -LiteralPath $release -Recurse -Force }
New-Item -ItemType Directory -Force -Path 'build',$release | Out-Null
$parts = ($version.Split('.') + '0') -join ', '
@"
VSVersionInfo(ffi=FixedFileInfo(filevers=($parts), prodvers=($parts), mask=0x3f, flags=0, OS=0x40004, fileType=1, subtype=0, date=(0,0)),
 kids=[StringFileInfo([StringTable('040904B0', [StringStruct('CompanyName','BochkaPiva'),
 StringStruct('ProductName','Nelviro'), StringStruct('FileDescription','Nelviro'),
 StringStruct('FileVersion','$version'), StringStruct('ProductVersion','$version'),
 StringStruct('OriginalFilename','CloudIsland.exe')])]), VarFileInfo([VarStruct('Translation',[1033,1200])])])
"@ | Set-Content -LiteralPath 'build/version_info.txt' -Encoding utf8
python tools/collect_licenses.py
if ($LASTEXITCODE -ne 0) { throw 'Notice collection failed' }
python -m PyInstaller --noconfirm --clean --distpath dist --workpath build/pyinstaller packaging/cloud-island.spec
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }
$test = Start-Process -FilePath (Join-Path $root 'dist/CloudIsland/CloudIsland.exe') -ArgumentList @('--self-test', ('"'+(Join-Path $root 'build/packaged-check.json')+'"')) -WindowStyle Hidden -PassThru
if (-not $test.WaitForExit(30000)) { throw 'Packaged self-test timeout' }
if ($test.ExitCode -ne 0) { throw 'Packaged self-test failed' }
Copy-Item -LiteralPath 'LICENSE','THIRD_PARTY.md' -Destination 'dist/CloudIsland' -Force
Copy-Item -LiteralPath 'build/licenses' -Destination 'dist/CloudIsland' -Recurse -Force
python tools/audit_bundle.py dist/CloudIsland
if ($LASTEXITCODE -ne 0) { throw 'Bundle audit failed' }
Compress-Archive -Path 'dist/CloudIsland/*' -DestinationPath "dist/release/Nelviro-Portable-$version-win-x64.zip" -Force
if (-not $SkipInstaller) {
    $iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (-not $iscc) { throw 'Inno Setup 6 not installed' }
    & $iscc "/DAppVersion=$version" 'packaging/installer.iss'
    if ($LASTEXITCODE -ne 0) { throw 'Installer build failed' }
    Copy-Item -LiteralPath "packaging/Output/Nelviro-Setup-$version-win-x64.exe" -Destination $release -Force
    # Existing updaters accept this exact filename. Keep byte-identical compatibility
    # bytes; public primary downloads and the current updater use the Nelviro name.
    Copy-Item -LiteralPath "packaging/Output/Nelviro-Setup-$version-win-x64.exe" -Destination (Join-Path $release "CloudIsland-Setup-$version-win-x64.exe") -Force
}
$checksums = Get-ChildItem -LiteralPath $release -File | Sort-Object Name | ForEach-Object {
    $hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    "$hash  $($_.Name)"
}
$checksums | Set-Content -LiteralPath 'dist/release/SHA256SUMS.txt' -Encoding ascii
Write-Host "Nelviro ${version}: private candidate in dist/release; no automatic publication"
