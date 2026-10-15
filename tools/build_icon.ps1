# Deterministic local crop/resizing only; no network or image-generation service.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$root = Split-Path -Parent $PSScriptRoot
$sourcePath = Join-Path $root 'icon.png'
$originalHash = (Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash
$source = [System.Drawing.Image]::FromFile($sourcePath)
$portrait = $null
try {
    # Use a centered square inside the upper half, ending above the chest.
    $side = [int][Math]::Min($source.Width, [Math]::Floor($source.Height / 2))
    $x = [int][Math]::Floor(($source.Width - $side) / 2)
    $portrait = New-Object System.Drawing.Bitmap $side, $side
    $graphics = [System.Drawing.Graphics]::FromImage($portrait)
    try {
        $graphics.DrawImage($source, (New-Object System.Drawing.Rectangle 0, 0, $side, $side),
            (New-Object System.Drawing.Rectangle $x, 0, $side, $side), [System.Drawing.GraphicsUnit]::Pixel)
    } finally { $graphics.Dispose() }
    $masterDirectory = Join-Path $root 'module\res\drawable-nodpi'
    [IO.Directory]::CreateDirectory($masterDirectory) | Out-Null
    $portrait.Save((Join-Path $masterDirectory 'icon_portrait.png'), [System.Drawing.Imaging.ImageFormat]::Png)
    $sizes = [ordered]@{mdpi = 48; hdpi = 72; xhdpi = 96; xxhdpi = 144; xxxhdpi = 192}
    foreach ($density in $sizes.Keys) {
        $size = [int]$sizes[$density]
        $directory = Join-Path $root ('module\res\mipmap-' + $density)
        [IO.Directory]::CreateDirectory($directory) | Out-Null
        $bitmap = New-Object System.Drawing.Bitmap $size, $size
        $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
        try {
            $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
            $graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
            $graphics.DrawImage($portrait, 0, 0, $size, $size)
            $path = Join-Path $directory 'ic_launcher.png'
            $bitmap.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
        } finally {
            $graphics.Dispose()
            $bitmap.Dispose()
        }
        $check = [System.Drawing.Image]::FromFile($path)
        try {
            if ($check.Width -ne $size -or $check.Height -ne $size) { throw "Invalid icon size: $path" }
        } finally { $check.Dispose() }
        Write-Output "PASS $density ${size}x${size}: $path"
    }
    Write-Output "Crop: x=$x y=0 width=$side height=$side; source=$($source.Width)x$($source.Height)"
} finally {
    if ($portrait) { $portrait.Dispose() }
    $source.Dispose()
}
if ((Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash -ne $originalHash) {
    throw 'Original icon.png changed'
}
Write-Output "PASS original SHA256 unchanged: $originalHash"
