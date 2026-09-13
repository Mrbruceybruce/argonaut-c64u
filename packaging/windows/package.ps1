$ErrorActionPreference = 'Stop'
function Run-Checked($File, $Arguments) {
  $p = Start-Process -FilePath $File -ArgumentList $Arguments -PassThru -Wait
  if ($p.ExitCode -ne 0) { throw "$File exited with $($p.ExitCode)" }
}
$bundle = Join-Path $env:GITHUB_WORKSPACE 'dist\Argonaut'
$assets = Join-Path $env:GITHUB_WORKSPACE 'release-assets'
New-Item -ItemType Directory -Force $assets | Out-Null
$iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $iscc)) { throw 'Inno Setup compiler is unavailable' }
& $iscc packaging/windows/installer.iss
if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed' }
$setup = Join-Path $assets 'Argonaut-0.1.4-Windows-x64-Setup.exe'
$installed = Join-Path $env:RUNNER_TEMP 'Argonaut Install Test'
Run-Checked $setup @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',"/DIR=`"$installed`"")
if (Test-Path "$installed\portable.flag") { throw 'Installer incorrectly enabled portable mode' }
$report = Join-Path $env:RUNNER_TEMP 'installed-self-test.json'
Run-Checked "$installed\Argonaut.exe" @('--self-test',"`"$report`"")
if (-not (Test-Path $report)) { throw 'Installed executable self-test failed' }
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
if (-not (Test-Path $report)) { throw 'Portable executable self-test failed' }
if (-not (Test-Path "$bundle\Data\argonaut\config.json")) { throw 'Portable preferences missing' }
Remove-Item "$bundle\Data" -Recurse -Force
Compress-Archive -Path "$bundle\*" -DestinationPath "$assets\Argonaut-0.1.4-Windows-x64-Portable.zip"
git archive --format=zip --prefix=argonaut-0.1.4/ -o "$assets\argonaut-0.1.4-source.zip" HEAD
if ($LASTEXITCODE -ne 0) { throw 'Source archive failed' }
Get-ChildItem $assets -File | Sort-Object Name | ForEach-Object {
  $digest = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
  "$digest  $($_.Name)"
} | Set-Content -Encoding ascii "$assets\SHA256SUMS"
