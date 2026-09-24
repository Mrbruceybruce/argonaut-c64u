$ErrorActionPreference = 'Stop'
if (-not $env:ARGONAUT_VERSION) { throw 'ARGONAUT_VERSION is required' }
if (-not $env:ARGONAUT_WINDOWS_VERSION) { throw 'ARGONAUT_WINDOWS_VERSION is required' }
if (-not $env:ARGONAUT_SOURCE_COMMIT) { throw 'ARGONAUT_SOURCE_COMMIT is required' }
$version = $env:ARGONAUT_VERSION
function Run-Checked($File, $Arguments) {
  $p = Start-Process -FilePath $File -ArgumentList $Arguments -PassThru -Wait
  if ($p.ExitCode -ne 0) { throw "$File exited with $($p.ExitCode)" }
}
function Confirm-SelfTest($Report) {
  if (-not (Test-Path $Report)) { throw 'Executable self-test report is missing' }
  $result = Get-Content $Report | ConvertFrom-Json
  if ($result.result -ne 'passed' -or $result.suite -ne 'package') {
    throw 'Executable self-test did not pass'
  }
  if ($env:ARGONAUT_SOURCE_COMMIT -and $result.build -ne $env:ARGONAUT_SOURCE_COMMIT) {
    throw 'Executable build does not match the requested source commit'
  }
}
$bundle = Join-Path $env:GITHUB_WORKSPACE 'dist\Argonaut'
$assets = Join-Path $env:GITHUB_WORKSPACE 'release-assets'
New-Item -ItemType Directory -Force $assets | Out-Null
$releaseNotes = Join-Path $env:GITHUB_WORKSPACE "packaging\RELEASE-$version.md"
if (Test-Path $releaseNotes) { Copy-Item $releaseNotes "$bundle\RELEASE-NOTES.md" }
$iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $iscc)) { throw 'Inno Setup compiler is unavailable' }
$evidence = Join-Path $bundle 'BUILD-EVIDENCE.txt'
Add-Content $evidence "Inno Setup: $((Get-Item $iscc).VersionInfo.FileVersion)"
Add-Content $evidence "PowerShell: $($PSVersionTable.PSVersion)"
Add-Content $evidence "Windows: $([Environment]::OSVersion.VersionString)"
& $iscc "/DAppVersion=$version" "/DAppNumericVersion=$env:ARGONAUT_WINDOWS_VERSION" packaging/windows/installer.iss
if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed' }
$setup = Join-Path $assets "Argonaut-$version-Windows-x64-Setup.exe"
$setupVersion = (Get-Item $setup).VersionInfo
if ($setupVersion.FileVersion -ne $env:ARGONAUT_WINDOWS_VERSION) {
  throw 'Setup executable version resource is incorrect'
}
$sourceExe = Join-Path $bundle 'Argonaut.exe'
$versionInfo = (Get-Item $sourceExe).VersionInfo
if ($versionInfo.FileVersion -ne $env:ARGONAUT_WINDOWS_VERSION -or
    $versionInfo.ProductVersion -ne $version -or
    $versionInfo.ProductName -ne 'Argonaut' -or
    $versionInfo.CompanyName -ne 'Bruce Marcus') {
  throw "Argonaut.exe PE version resource is incorrect: $($versionInfo | Format-List | Out-String)"
}
$installed = Join-Path $env:RUNNER_TEMP 'Argonaut Install Test'
Run-Checked $setup @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',"/DIR=`"$installed`"")
if (Test-Path "$installed\portable.flag") { throw 'Installer incorrectly enabled portable mode' }
$report = Join-Path $env:RUNNER_TEMP 'installed-self-test.json'
Run-Checked "$installed\Argonaut.exe" @('--self-test',"`"$report`"")
Confirm-SelfTest $report
$shortcut = Join-Path ([Environment]::GetFolderPath('Programs')) 'Argonaut\Argonaut.lnk'
if (-not (Test-Path $shortcut)) { throw 'Start-menu shortcut missing' }
# A user-created file must not be swept away by the uninstaller.
Set-Content "$installed\user-data-test.txt" 'preserve me'
Run-Checked "$installed\unins000.exe" @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART')
if (Test-Path "$installed\Argonaut.exe") { throw 'Executable remains after uninstall' }
if (Test-Path $shortcut) { throw 'Shortcut remains after uninstall' }
if (-not (Test-Path "$installed\user-data-test.txt")) { throw 'Uninstaller removed user-created data' }
New-Item -ItemType File "$bundle\portable.flag" | Out-Null
$report = Join-Path $env:RUNNER_TEMP 'portable-self-test.json'
Run-Checked "$bundle\Argonaut.exe" @('--self-test',"`"$report`"")
Confirm-SelfTest $report
if (-not (Test-Path "$bundle\Data\argonaut\config.json")) { throw 'Portable preferences missing' }
Remove-Item "$bundle\Data" -Recurse -Force
$portable = Join-Path $assets "Argonaut-$version-Windows-x64-Portable.zip"
Compress-Archive -Path "$bundle\*" -DestinationPath $portable
$extracted = Join-Path $env:RUNNER_TEMP 'Argonaut Portable Final Test'
Expand-Archive -Path $portable -DestinationPath $extracted
if (Test-Path "$extracted\Data") { throw 'Distributed Portable ZIP contains test-generated Data' }
$report = Join-Path $env:RUNNER_TEMP 'portable-final-self-test.json'
Run-Checked "$extracted\Argonaut.exe" @('--self-test',"`"$report`"")
Confirm-SelfTest $report
$finalVersion = (Get-Item "$extracted\Argonaut.exe").VersionInfo
if ($finalVersion.FileVersion -ne $env:ARGONAUT_WINDOWS_VERSION -or
    $finalVersion.ProductVersion -ne $version) {
  throw 'Portable ZIP executable version resource is incorrect'
}
