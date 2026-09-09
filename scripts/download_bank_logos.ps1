param(
    [string]$OutputDirectory = (Join-Path $PSScriptRoot "..\frontend\assets\bank-logos"),
    [string]$ZipPath = (Join-Path $PSScriptRoot "..\frontend\assets\bank-logos.zip"),
    [int]$Size = 256
)

$ErrorActionPreference = "Stop"
$apiUrl = "https://api.vietqr.io/v2/banks"
$resolvedOutput = [System.IO.Path]::GetFullPath($OutputDirectory)
$resolvedZip = [System.IO.Path]::GetFullPath($ZipPath)
$temporary = Join-Path ([System.IO.Path]::GetTempPath()) ("smartfinance-bank-logos-" + [guid]::NewGuid())

Add-Type -AssemblyName System.Drawing

function Convert-ToSquarePng {
    param([byte[]]$Bytes, [string]$Destination, [int]$CanvasSize)

    $stream = [System.IO.MemoryStream]::new($Bytes)
    $source = $null
    $bitmap = $null
    $graphics = $null
    try {
        $source = [System.Drawing.Image]::FromStream($stream)
        $bitmap = [System.Drawing.Bitmap]::new($CanvasSize, $CanvasSize, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
        $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
        $graphics.Clear([System.Drawing.Color]::Transparent)
        $graphics.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
        $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
        $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
        $scale = [Math]::Min(($CanvasSize * 0.86) / $source.Width, ($CanvasSize * 0.86) / $source.Height)
        $width = [Math]::Max(1, [int][Math]::Round($source.Width * $scale))
        $height = [Math]::Max(1, [int][Math]::Round($source.Height * $scale))
        $x = [int](($CanvasSize - $width) / 2)
        $y = [int](($CanvasSize - $height) / 2)
        $graphics.DrawImage($source, $x, $y, $width, $height)
        $bitmap.Save($Destination, [System.Drawing.Imaging.ImageFormat]::Png)
    }
    finally {
        if ($graphics) { $graphics.Dispose() }
        if ($bitmap) { $bitmap.Dispose() }
        if ($source) { $source.Dispose() }
        $stream.Dispose()
    }
}

try {
    New-Item -ItemType Directory -Path $temporary | Out-Null
    $response = Invoke-RestMethod -Uri $apiUrl -Headers @{ Accept = "application/json" }
    if ($response.code -ne "00" -or -not $response.data) {
        throw "VietQR returned an invalid bank list."
    }

    $manifest = [ordered]@{}
    foreach ($bank in $response.data) {
        $code = ([string]$bank.code).Trim().ToUpperInvariant() -replace '[^A-Z0-9_-]', ''
        if (-not $code -or -not $bank.logo) { continue }
        try {
            $download = Invoke-WebRequest -Uri $bank.logo -Headers @{ Accept = "image/*" } -UseBasicParsing
            $fileName = "$code.png"
            Convert-ToSquarePng -Bytes $download.Content -Destination (Join-Path $temporary $fileName) -CanvasSize $Size
            $manifest[$code] = [ordered]@{
                name = [string]$bank.name
                shortName = [string]$bank.shortName
                bin = [string]$bank.bin
                file = $fileName
                source = [string]$bank.logo
            }
            Write-Host "Downloaded $code"
        }
        catch {
            Write-Warning "Skipped $code`: $($_.Exception.Message)"
        }
    }

    if ($manifest.Count -eq 0) { throw "No bank logo could be downloaded." }
    $metadata = [ordered]@{
        generatedAt = (Get-Date).ToUniversalTime().ToString("o")
        sourceApi = $apiUrl
        size = "${Size}x${Size}"
        count = $manifest.Count
        banks = $manifest
    }
    $metadata | ConvertTo-Json -Depth 6 | Set-Content -Path (Join-Path $temporary "manifest.json") -Encoding UTF8

    New-Item -ItemType Directory -Force -Path (Split-Path $resolvedOutput) | Out-Null
    if (Test-Path -LiteralPath $resolvedOutput) { Remove-Item -LiteralPath $resolvedOutput -Recurse -Force }
    Move-Item -LiteralPath $temporary -Destination $resolvedOutput
    New-Item -ItemType Directory -Force -Path (Split-Path $resolvedZip) | Out-Null
    if (Test-Path -LiteralPath $resolvedZip) { Remove-Item -LiteralPath $resolvedZip -Force }
    Compress-Archive -Path (Join-Path $resolvedOutput "*") -DestinationPath $resolvedZip -CompressionLevel Optimal
    Write-Host "Saved $($manifest.Count) logos to $resolvedOutput"
    Write-Host "Created $resolvedZip"
}
finally {
    if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Recurse -Force }
}
