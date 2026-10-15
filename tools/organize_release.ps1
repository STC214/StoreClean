# Archive non-APK deliverables without deletion; -Apply confirms the displayed move plan.
param([switch]$Apply)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$release = Join-Path $root 'release'
$archive = Join-Path $root 'analysis\release_artifacts'
[xml]$manifest = Get-Content -LiteralPath (Join-Path $root 'module\AndroidManifest.xml') -Raw -Encoding UTF8
$version = $manifest.DocumentElement.GetAttribute('versionName', 'http://schemas.android.com/apk/res/android')
if ($version -notmatch '^\d+\.\d+\.\d+$') { throw 'Invalid module version' }
$keep = Join-Path $release ('storeclean-' + $version + '.apk')
$keepHash = (Get-FileHash -LiteralPath $keep -Algorithm SHA256).Hash
foreach ($directory in @($release, (Join-Path $root 'analysis'), $archive)) {
    if (Test-Path -LiteralPath $directory) {
        if ((Get-Item -LiteralPath $directory -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw "Reparse point directory: $directory"
        }
    }
}
$plan = @()
foreach ($item in Get-ChildItem -LiteralPath $release -File) {
    if ($item.FullName -eq $keep) { continue }
    if ($item.Name -notmatch '^storeclean-\d+\.\d+\.\d+(\.patch|-source\.zip|-verification\.json|\.apk\.idsig)$') {
        throw "Unexpected file; not moved: $($item.FullName)"
    }
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Reparse point file' }
    $source = [IO.Path]::GetFullPath($item.FullName)
    $destination = [IO.Path]::GetFullPath((Join-Path $archive $item.Name))
    if (-not $source.StartsWith($release + '\', [StringComparison]::OrdinalIgnoreCase) -or
        -not $destination.StartsWith($archive + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Move target exceeds intended directories'
    }
    if (Test-Path -LiteralPath $destination) { throw "Destination exists: $destination" }
    $hash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
    $plan += [pscustomobject]@{ Source = $source; Destination = $destination; Hash = $hash }
    Write-Output "Move: $source -> $destination"
}
if (-not $Apply) {
    Write-Output 'DRY RUN: no file moved'
    exit 0
}
New-Item -ItemType Directory -Path $archive -Force | Out-Null
foreach ($entry in $plan) {
    Move-Item -LiteralPath $entry.Source -Destination $entry.Destination
    if ((Get-FileHash -LiteralPath $entry.Destination -Algorithm SHA256).Hash -ne $entry.Hash) {
        throw "Archived hash mismatch: $($entry.Destination)"
    }
}
if ((Get-FileHash -LiteralPath $keep -Algorithm SHA256).Hash -ne $keepHash) { throw 'Latest APK changed' }
$remaining = @(Get-ChildItem -LiteralPath $release -Force)
if ($remaining.Count -ne 1 -or $remaining[0].FullName -ne $keep) { throw 'Unexpected release contents remain' }
Write-Output "PASS: archived $($plan.Count) files; release contains only latest APK; hashes unchanged"
