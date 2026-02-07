param(
    [Parameter(Mandatory=$true)][string]$Server,
    [Parameter(Mandatory=$true)][string]$Token,
    [Parameter(Mandatory=$true)][string]$Path
)

$Headers = @{ Authorization = "Bearer $Token" }
$InfoUrl = "$Server/api/file/info?path=$Path"
$Info = Invoke-RestMethod -Method Get -Headers $Headers -Uri $InfoUrl

$TargetRoot = Join-Path $env:USERPROFILE "Documents\mbspp_cli"
$TargetPath = Join-Path $TargetRoot $Path
$TargetDir = Split-Path $TargetPath -Parent
if (!(Test-Path $TargetDir)) {
    New-Item -ItemType Directory -Path $TargetDir -Force | Out-Null
}

$NeedsDownload = $true
if (Test-Path $TargetPath) {
    $LocalTime = (Get-Item $TargetPath).LastWriteTimeUtc
    $RemoteTime = [DateTime]::Parse($Info.mtime).ToUniversalTime()
    if ($LocalTime -ge $RemoteTime) {
        $NeedsDownload = $false
    }
}

if ($NeedsDownload) {
    if ($Info.size -gt 4294967296) {
        throw "File too large for open mode (>4GB)."
    }
    $DownloadUrl = "$Server/api/download/$Path"
    Invoke-WebRequest -Uri $DownloadUrl -Headers $Headers -OutFile $TargetPath
    $RemoteTime = [DateTime]::Parse($Info.mtime).ToUniversalTime()
    (Get-Item $TargetPath).LastWriteTimeUtc = $RemoteTime
}

Start-Process -FilePath $TargetPath
