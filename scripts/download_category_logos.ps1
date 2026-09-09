param(
    [string]$OutputDirectory = (Join-Path $PSScriptRoot "..\frontend\assets\category-logos"),
    [string]$ZipPath = (Join-Path $PSScriptRoot "..\frontend\assets\category-logos.zip"),
    [int]$Size = 128
)

# Downloads one icon per built-in budget category (the leaves seeded by
# scripts/seed.py, rendered on the Budgets page and the dashboard budget list).
# Icons come from the Iconify API (Material Design Icons set, no API key). Each
# is fetched as a coloured SVG and written next to a manifest.json shaped like
# frontend/assets/bank-logos/manifest.json so the frontend can look a logo up by
# the category name stored in the database.

$ErrorActionPreference = "Stop"
$iconApi = "https://api.iconify.design"

# Category name (exactly as seeded, matches Category.name) -> icon + accent colour.
# Colours track the .cat-icon palette in frontend/styles.css.
$catalogue = @(
    [ordered]@{ name = "Thu nhập";      en = "Income";        icon = "mdi:cash-plus";               color = "#188469" }
    [ordered]@{ name = "Nhà ở";         en = "Housing";       icon = "mdi:home-city";               color = "#406eaf" }
    [ordered]@{ name = "Học phí";       en = "Tuition";       icon = "mdi:school";                  color = "#5b7fc4" }
    [ordered]@{ name = "Điện nước";     en = "Utilities";     icon = "mdi:flash";                   color = "#d9a441" }
    [ordered]@{ name = "Viễn thông";    en = "Telecom";       icon = "mdi:wifi";                    color = "#4a90b8" }
    [ordered]@{ name = "Y tế";          en = "Healthcare";    icon = "mdi:medical-bag";             color = "#cf5b58" }
    [ordered]@{ name = "Ăn uống";       en = "Dining";        icon = "mdi:silverware-fork-knife";   color = "#d37e20" }
    [ordered]@{ name = "Mua sắm";       en = "Shopping";      icon = "mdi:shopping";                color = "#955ca9" }
    [ordered]@{ name = "Di chuyển";     en = "Transport";     icon = "mdi:bus";                     color = "#188469" }
    [ordered]@{ name = "Nhiên liệu";    en = "Fuel";          icon = "mdi:gas-station";             color = "#b8763a" }
    [ordered]@{ name = "Học tập";       en = "Education";      icon = "mdi:book-open-page-variant";  color = "#6a7fb0" }
    [ordered]@{ name = "Khác";          en = "Other";         icon = "mdi:dots-horizontal-circle";  color = "#7a8a84" }
    [ordered]@{ name = "Chuyển khoản";  en = "Transfer";      icon = "mdi:bank-transfer";           color = "#406eaf" }
    [ordered]@{ name = "Uncategorised"; en = "Uncategorised"; icon = "mdi:help-circle";             color = "#9aa7a1" }
)

$resolvedOutput = [System.IO.Path]::GetFullPath($OutputDirectory)
$resolvedZip = [System.IO.Path]::GetFullPath($ZipPath)
$temporary = Join-Path ([System.IO.Path]::GetTempPath()) ("smartfinance-category-logos-" + [guid]::NewGuid())

function Get-Slug {
    param([string]$Value)
    $normalized = $Value.Normalize([Text.NormalizationForm]::FormD)
    $builder = [Text.StringBuilder]::new()
    foreach ($char in $normalized.ToCharArray()) {
        if ([Globalization.CharUnicodeInfo]::GetUnicodeCategory($char) -ne [Globalization.UnicodeCategory]::NonSpacingMark) {
            [void]$builder.Append($char)
        }
    }
    $ascii = $builder.ToString().Normalize([Text.NormalizationForm]::FormC)
    $ascii = $ascii -replace 'đ', 'd' -replace 'Đ', 'D'
    ($ascii.ToLowerInvariant() -replace '[^a-z0-9]+', '-').Trim('-')
}

try {
    New-Item -ItemType Directory -Path $temporary | Out-Null

    $manifest = [ordered]@{}
    foreach ($entry in $catalogue) {
        $slug = Get-Slug $entry.name
        $prefix, $iconName = $entry.icon.Split(":", 2)
        $uri = "$iconApi/$prefix/$iconName.svg?height=$Size&color=" + [uri]::EscapeDataString($entry.color)
        try {
            $download = Invoke-WebRequest -Uri $uri -Headers @{ Accept = "image/svg+xml" } -UseBasicParsing
            $body = if ($download.Content -is [byte[]]) { [Text.Encoding]::UTF8.GetString($download.Content) } else { [string]$download.Content }
            if ($body -notmatch '<svg') { throw "Iconify did not return an SVG for $($entry.icon)." }
            $fileName = "$slug.svg"
            Set-Content -Path (Join-Path $temporary $fileName) -Value $body -Encoding UTF8 -NoNewline
            $manifest[$slug] = [ordered]@{
                name   = $entry.name
                en     = $entry.en
                icon   = $entry.icon
                color  = $entry.color
                file   = $fileName
                source = $uri
            }
            Write-Host "Downloaded $slug ($($entry.icon))"
        }
        catch {
            Write-Warning "Skipped $slug`: $($_.Exception.Message)"
        }
    }

    if ($manifest.Count -eq 0) { throw "No category logo could be downloaded." }

    $metadata = [ordered]@{
        generatedAt = (Get-Date).ToUniversalTime().ToString("o")
        source      = "$iconApi (Material Design Icons)"
        size        = "${Size}x${Size}"
        count       = $manifest.Count
        categories  = $manifest
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
