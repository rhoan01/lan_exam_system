$ErrorActionPreference = 'Stop'

$configPath = 'C:\ProgramData\MySQL\MySQL Server 26.7\my.ini'
$backupPath = 'C:\ProgramData\MySQL\MySQL Server 26.7\my.ini.before-lan-exam'
$resultDirectory = Join-Path $PSScriptRoot 'runtime'
$resultPath = Join-Path $resultDirectory 'mysql-localhost-result.txt'
$localConfigPath = Join-Path $PSScriptRoot 'mysql.local.bat'

New-Item -ItemType Directory -Path $resultDirectory -Force | Out-Null
$mysqlSecured = $false

try {
    $windowsUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    @(
        (Join-Path $PSScriptRoot 'mysql.local.bat'),
        (Join-Path $PSScriptRoot 'mysql.root.local.txt')
    ) | ForEach-Object {
        if (Test-Path -LiteralPath $_) {
            & takeown.exe /F $_ | Out-Null
            & icacls.exe $_ `
                /inheritance:r `
                /grant:r `
                ($windowsUser + ':(R,W)') `
                'NT AUTHORITY\SYSTEM:(F)' `
                'BUILTIN\Administrators:(F)' | Out-Null
            if ($LASTEXITCODE -ne 0) {
                throw "Could not secure local credential file $_."
            }
        }
    }

    $resolvedPath = (Resolve-Path -LiteralPath $configPath).Path
    if ($resolvedPath -ne $configPath) {
        throw "Unexpected MySQL configuration path: $resolvedPath"
    }

    Copy-Item -LiteralPath $configPath -Destination $backupPath -Force
    $configText = [IO.File]::ReadAllText($configPath)

    if ($configText -match '(?m)^\s*bind-address\s*=') {
        $updatedText = [regex]::Replace(
            $configText,
            '(?m)^\s*bind-address\s*=.*$',
            'bind-address=127.0.0.1'
        )
    } else {
        $updatedText = [regex]::Replace(
            $configText,
            '(?m)^\[mysqld\]\s*$',
            '$0' + [Environment]::NewLine + 'bind-address=127.0.0.1',
            1
        )
    }

    if ($updatedText -match '(?m)^\s*mysqlx\s*=') {
        $updatedText = [regex]::Replace(
            $updatedText,
            '(?m)^\s*mysqlx\s*=.*$',
            'mysqlx=0'
        )
    } else {
        $updatedText = [regex]::Replace(
            $updatedText,
            '(?m)^\[mysqld\]\s*$',
            '$0' + [Environment]::NewLine + 'mysqlx=0',
            1
        )
    }

    if (
        $updatedText -notmatch '(?m)^bind-address=127\.0\.0\.1$' -or
        $updatedText -notmatch '(?m)^mysqlx=0$'
    ) {
        throw 'Could not secure the MySQL network settings.'
    }

    [IO.File]::WriteAllText(
        $configPath,
        $updatedText,
        (New-Object Text.UTF8Encoding($false))
    )
    Restart-Service -Name MySQL267 -Force

    $service = Get-Service -Name MySQL267
    $service.WaitForStatus('Running', [TimeSpan]::FromSeconds(30))
    $mysqlSecured = $true

    $lanIpLine = Get-Content -LiteralPath $localConfigPath | Where-Object {
        $_ -match '^set "LAN_SERVER_IP=(.+)"$'
    } | Select-Object -First 1
    if (-not $lanIpLine) {
        throw 'LAN_SERVER_IP is missing from deployment\mysql.local.bat.'
    }
    $lanIp = [regex]::Match($lanIpLine, '^set "LAN_SERVER_IP=(.+)"$').Groups[1].Value
    $adapter = Get-NetIPAddress -AddressFamily IPv4 | Where-Object {
        $_.IPAddress -eq $lanIp
    } | Select-Object -First 1
    if (-not $adapter) {
        throw "No network adapter owns LAN_SERVER_IP $lanIp."
    }
    $profile = Get-NetConnectionProfile -InterfaceIndex $adapter.InterfaceIndex
    if ($profile.NetworkCategory -eq 'Public') {
        Set-NetConnectionProfile -InterfaceIndex $adapter.InterfaceIndex -NetworkCategory Private
    }

    @('Port 3306', 'Port 33060', 'mysqld', 'python.exe') | ForEach-Object {
        Get-NetFirewallRule -DisplayName $_ -ErrorAction SilentlyContinue |
            Remove-NetFirewallRule
    }
    $webRuleName = 'LAN Exam System (TCP 8000)'
    Get-NetFirewallRule -DisplayName $webRuleName -ErrorAction SilentlyContinue |
        Remove-NetFirewallRule
    New-NetFirewallRule `
        -DisplayName $webRuleName `
        -Direction Inbound `
        -Action Allow `
        -Protocol TCP `
        -LocalPort 8000 `
        -RemoteAddress LocalSubnet `
        -Profile Private,Domain | Out-Null

    'OK' | Set-Content -LiteralPath $resultPath -Encoding ASCII
} catch {
    if (-not $mysqlSecured -and (Test-Path -LiteralPath $backupPath)) {
        Copy-Item -LiteralPath $backupPath -Destination $configPath -Force
        Start-Service -Name MySQL267 -ErrorAction SilentlyContinue
    }
    ('ERROR: ' + $_.Exception.Message) | Set-Content -LiteralPath $resultPath -Encoding UTF8
    exit 1
}
