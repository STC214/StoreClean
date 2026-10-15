# Show exact production-APK targets first; -Apply confirms their removal.
param([switch]$Apply)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$release = Join-Path $root 'release'
if ((Get-Item -LiteralPath $release -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
    throw 'Release directory is a reparse point'
}
$apks = @(Get-ChildItem -LiteralPath $release -File | Where-Object {
    $_.Name -match '^storeclean-\d+\.\d+\.\d+\.apk$'
} | Sort-Object { [version]($_.BaseName.Substring('storeclean-'.Length)) } -Descending)
if ($apks.Count -eq 0) { throw 'No production APK found' }
$latest = $apks[0]
$version = $latest.BaseName.Substring('storeclean-'.Length)
$recordPath = Join-Path $root ('analysis\release_artifacts\storeclean-' + $version + '-verification.json')
if (-not (Test-Path -LiteralPath $recordPath)) {
    $recordPath = Join-Path $release ('storeclean-' + $version + '-verification.json')
}
$record = Get-Content -LiteralPath $recordPath -Raw -Encoding UTF8 | ConvertFrom-Json
$hash = (Get-FileHash -LiteralPath $latest.FullName -Algorithm SHA256).Hash
if ($record.version -ne $version -or $record.apk_sha256 -ne $hash) {
    throw 'Latest APK lacks matching verification record'
}
$targets = @()
foreach ($apk in $apks | Select-Object -Skip 1) {
    foreach ($candidate in @($apk.FullName, ($apk.FullName + '.idsig'))) {
        $path = [IO.Path]::GetFullPath($candidate)
        if (-not $path.StartsWith($release + '\', [StringComparison]::OrdinalIgnoreCase)) {
            throw "Target exceeds release directory: $path"
        }
        if (Test-Path -LiteralPath $path) {
            if ((Get-Item -LiteralPath $path -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "Target is a reparse point: $path"
            }
            $targets += $path
            Write-Output "Target: $path"
        }
    }
}
Write-Output "Keep: $($latest.FullName)"
if (-not $Apply) {
    Write-Output 'DRY RUN: no file removed'
    exit 0
}
foreach ($path in $targets) {
    Remove-Item -LiteralPath $path -Force
    if (Test-Path -LiteralPath $path) { throw "Target remains: $path" }
    Write-Output "Removed: $path"
}
if ((Get-FileHash -LiteralPath $latest.FullName -Algorithm SHA256).Hash -ne $hash) {
    throw 'Latest APK changed'
}
$remaining = @(Get-ChildItem -LiteralPath $release -File -Filter 'storeclean-*.apk')
if ($remaining.Count -ne 1 -or $remaining[0].Name -ne $latest.Name) {
    throw 'Unexpected production APKs remain'
}
Write-Output "PASS: only $($latest.Name) remains; latest hash unchanged"
