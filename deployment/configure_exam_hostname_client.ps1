param(
    [Parameter(Mandatory = $true)]
    [string]$ServerIp
)

$ErrorActionPreference = 'Stop'
$hostname = 'exam.ite'
$hostsPath = Join-Path $env:WINDIR 'System32\drivers\etc\hosts'
$backupPath = "$hostsPath.before-lan-exam"

$parsedIp = $null
if (-not [Net.IPAddress]::TryParse($ServerIp, [ref]$parsedIp) -or $parsedIp.AddressFamily -ne 'InterNetwork') {
    throw "ServerIp must be a valid IPv4 address; received '$ServerIp'."
}

$resolvedHostsPath = (Resolve-Path -LiteralPath $hostsPath).Path
if ($resolvedHostsPath -ne $hostsPath) {
    throw "Unexpected Windows hosts-file path: $resolvedHostsPath"
}

if (-not (Test-Path -LiteralPath $backupPath)) {
    Copy-Item -LiteralPath $hostsPath -Destination $backupPath
}

$lines = Get-Content -LiteralPath $hostsPath
$keptLines = @($lines | Where-Object {
    $_ -notmatch '(?i)^\s*[^#]*\bexam\.ite\b'
})
$keptLines += "$ServerIp`t$hostname"
[IO.File]::WriteAllLines($hostsPath, $keptLines, [Text.Encoding]::ASCII)

Clear-DnsClientCache
$mappedAddress = [Net.Dns]::GetHostAddresses($hostname) |
    Where-Object AddressFamily -eq 'InterNetwork' |
    Select-Object -First 1
if (-not $mappedAddress -or $mappedAddress.IPAddressToString -ne $ServerIp) {
    throw "$hostname did not resolve to $ServerIp after updating the hosts file."
}

Write-Host "$hostname now points to $ServerIp on this computer." -ForegroundColor Green
