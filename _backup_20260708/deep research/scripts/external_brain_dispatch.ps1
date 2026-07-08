param(
  [string]$Query,
  [string]$QueryFile,
  [ValidateSet('parallel','fallback','single')][string]$Mode = 'parallel',
  [string[]]$PreferredOrder = @('grok', 'deepseek'),
  [int]$MinSuccessCount = 2,
  [int]$MaxTokens = 512,
  [int]$ProviderTimeoutSec = 180,
  [int]$JobTimeoutSec = 240,
  [switch]$IncludeResponses
)

$ErrorActionPreference = 'Stop'
$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $utf8NoBom
[Console]::OutputEncoding = $utf8NoBom
$OutputEncoding = $utf8NoBom

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$providerScripts = @{
  grok = Join-Path $scriptRoot 'grok_chat.ps1'
  deepseek = Join-Path $scriptRoot 'deepseek_chat.ps1'
}

function New-TempArtifactPath {
  param([string]$Extension = 'tmp')
  return (Join-Path ([System.IO.Path]::GetTempPath()) ("deep-research-" + [guid]::NewGuid().ToString('N') + ".$Extension"))
}

function Write-Utf8TextFile {
  param(
    [string]$Path,
    [string]$Content
  )
  [System.IO.File]::WriteAllText($Path, $Content, $utf8NoBom)
}

function Read-Utf8TextFile {
  param([string]$Path)
  if (-not (Test-Path $Path)) {
    return $null
  }
  return [System.IO.File]::ReadAllText($Path, $utf8NoBom)
}

function ConvertTo-AsciiSafeJson {
  param([string]$JsonText)
  $builder = New-Object System.Text.StringBuilder
  foreach ($char in $JsonText.ToCharArray()) {
    $code = [int][char]$char
    if ($code -gt 127) {
      [void]$builder.AppendFormat('\u{0:x4}', $code)
    } else {
      [void]$builder.Append($char)
    }
  }
  return $builder.ToString()
}

function New-ProviderFailureResult {
  param(
    [string]$Provider,
    [string]$AttemptMode,
    [int]$ExitCode,
    [string]$ErrorMessage,
    [object]$RawResponse = $null
  )

  return [pscustomobject]@{
    provider = $Provider
    status = 'failed'
    attempt_mode = $AttemptMode
    selected = $false
    exit_code = $ExitCode
    response_model = $null
    content = $null
    reasoning_content = $null
    error = $ErrorMessage
    raw_response = $RawResponse
  }
}

function Remove-ChannelFailuresForProvider {
  param(
    [object[]]$Failures,
    [string]$Provider
  )

  return @(
    $Failures | Where-Object { $_.provider -ne $Provider }
  )
}

function Add-OrReplaceChannelFailure {
  param(
    [object[]]$Failures,
    [string]$Provider,
    [int]$ExitCode,
    [string]$ErrorMessage,
    [string]$AttemptMode
  )

  $remaining = @(Remove-ChannelFailuresForProvider -Failures $Failures -Provider $Provider)
  $updated = @($remaining)
  $updated += [pscustomobject]@{
    provider = $Provider
    exit_code = $ExitCode
    error = $ErrorMessage
    attempt_mode = $AttemptMode
  }
  return $updated
}

function Get-InitialProviderState {
  param([string[]]$Providers)
  $items = @()
  foreach ($provider in $Providers) {
    $items += [pscustomobject]@{
      provider = $provider
      status = 'pending'
      attempt_mode = $null
      selected = $false
      exit_code = $null
      response_model = $null
      content = $null
      reasoning_content = $null
      error = $null
      raw_response = $null
    }
  }
  return $items
}

if ([string]::IsNullOrWhiteSpace($Query) -and -not [string]::IsNullOrWhiteSpace($QueryFile)) {
  if (-not (Test-Path $QueryFile)) {
    Write-Error "QueryFile does not exist: $QueryFile"
    exit 2
  }
  $Query = Read-Utf8TextFile -Path $QueryFile
}

if ([string]::IsNullOrWhiteSpace($Query)) {
  Write-Error 'Either Query or QueryFile must be provided.'
  exit 2
}

if ($ProviderTimeoutSec -le 0) {
  $ProviderTimeoutSec = 45
}

if ($JobTimeoutSec -le 0) {
  $JobTimeoutSec = $ProviderTimeoutSec + 25
}

function Invoke-ProviderOnce {
  param(
    [string]$Provider,
    [string]$ProviderScript,
    [string]$ProviderQuery,
    [int]$ProviderMaxTokens,
    [int]$ProviderTimeoutSec,
    [string]$AttemptMode,
    [bool]$KeepResponse
  )

  if (-not (Test-Path $ProviderScript)) {
    return New-ProviderFailureResult -Provider $Provider -AttemptMode $AttemptMode -ExitCode 404 -ErrorMessage "Missing provider script: $ProviderScript"
  }

  $raw = $null
  $exitCode = $null
  $stderrText = $null
  $queryFile = New-TempArtifactPath -Extension 'txt'
  $outFile = New-TempArtifactPath -Extension 'json'

  try {
    Write-Utf8TextFile -Path $queryFile -Content $ProviderQuery
    $output = & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $ProviderScript -QueryFile $queryFile -MaxTokens $ProviderMaxTokens -TimeoutSec $ProviderTimeoutSec -OutFile $outFile 2>&1
    $exitCode = $LASTEXITCODE
    $stderrText = ($output | Out-String).Trim()
    $raw = Read-Utf8TextFile -Path $outFile
  } catch {
    $stderrText = $_ | Out-String
    $exitCode = if ($LASTEXITCODE -ne $null) { $LASTEXITCODE } else { 1 }
  } finally {
    Remove-Item -LiteralPath $queryFile -ErrorAction SilentlyContinue
    if ($exitCode -eq 0) {
      Remove-Item -LiteralPath $outFile -ErrorAction SilentlyContinue
    }
  }

  if ($exitCode -ne 0 -or [string]::IsNullOrWhiteSpace($raw)) {
    $errorMessage = if (-not [string]::IsNullOrWhiteSpace($stderrText)) { $stderrText.Trim() } elseif ([string]::IsNullOrWhiteSpace($raw)) { 'Empty response' } else { $raw.Trim() }
    $rawResponse = if ($KeepResponse -and -not [string]::IsNullOrWhiteSpace($raw)) { $raw } else { $null }
    return New-ProviderFailureResult -Provider $Provider -AttemptMode $AttemptMode -ExitCode $exitCode -ErrorMessage $errorMessage -RawResponse $rawResponse
  }

  try {
    $parsed = $raw | ConvertFrom-Json
    $choice = $parsed.choices[0]
    $message = $choice.message
    return [pscustomobject]@{
      provider = $Provider
      status = 'success'
      attempt_mode = $AttemptMode
      selected = $false
      exit_code = $exitCode
      response_model = $parsed.model
      content = $message.content
      reasoning_content = $message.reasoning_content
      error = $null
      raw_response = if ($KeepResponse) { $parsed } else { $null }
    }
  } catch {
    Remove-Item -LiteralPath $outFile -ErrorAction SilentlyContinue
    $rawResponse = if ($KeepResponse) { $raw } else { $null }
    return New-ProviderFailureResult -Provider $Provider -AttemptMode $AttemptMode -ExitCode $exitCode -ErrorMessage "Invalid JSON response: $($_.Exception.Message)" -RawResponse $rawResponse
  }

  Remove-Item -LiteralPath $outFile -ErrorAction SilentlyContinue
}

function Invoke-ParallelProviders {
  param(
    [string[]]$Providers,
    [string]$ProviderQuery,
    [int]$ProviderMaxTokens,
    [int]$ProviderTimeoutSec,
    [int]$ParallelJobTimeoutSec,
    [bool]$KeepResponse
  )

  $jobs = @()
  foreach ($provider in $Providers) {
    $scriptPath = $providerScripts[$provider]
    $jobs += Start-Job -Name $provider -ScriptBlock {
      param($Name, $Path, $QueryText, $Tokens, $TimeoutSec, $IncludeRaw)

      $IncludeRaw = [System.Convert]::ToBoolean($IncludeRaw)
      $utf8NoBom = [System.Text.UTF8Encoding]::new($false)
      [Console]::InputEncoding = $utf8NoBom
      [Console]::OutputEncoding = $utf8NoBom
      $OutputEncoding = $utf8NoBom

      if (-not (Test-Path $Path)) {
        return [pscustomobject]@{
          provider = $Name
          status = 'failed'
          attempt_mode = 'parallel'
          selected = $false
          exit_code = 404
          response_model = $null
          content = $null
          reasoning_content = $null
          error = "Missing provider script: $Path"
          raw_response = $null
        }
      }

      $raw = $null
      $exitCode = $null
      $stderrText = $null
      $queryFile = Join-Path ([System.IO.Path]::GetTempPath()) ("deep-research-" + [guid]::NewGuid().ToString('N') + ".txt")
      $outFile = Join-Path ([System.IO.Path]::GetTempPath()) ("deep-research-" + [guid]::NewGuid().ToString('N') + ".json")

      try {
        [System.IO.File]::WriteAllText($queryFile, $QueryText, $utf8NoBom)
        $output = & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $Path -QueryFile $queryFile -MaxTokens $Tokens -TimeoutSec $TimeoutSec -OutFile $outFile 2>&1
        $exitCode = $LASTEXITCODE
        $stderrText = ($output | Out-String).Trim()
        if (Test-Path $outFile) {
          $raw = [System.IO.File]::ReadAllText($outFile, $utf8NoBom)
        }
      } catch {
        $stderrText = $_ | Out-String
        $exitCode = if ($LASTEXITCODE -ne $null) { $LASTEXITCODE } else { 1 }
      } finally {
        Remove-Item -LiteralPath $queryFile -ErrorAction SilentlyContinue
        if ($exitCode -eq 0) {
          Remove-Item -LiteralPath $outFile -ErrorAction SilentlyContinue
        }
      }

      if ($exitCode -ne 0 -or [string]::IsNullOrWhiteSpace($raw)) {
        return [pscustomobject]@{
          provider = $Name
          status = 'failed'
          attempt_mode = 'parallel'
          selected = $false
          exit_code = $exitCode
          response_model = $null
          content = $null
          reasoning_content = $null
          error = if (-not [string]::IsNullOrWhiteSpace($stderrText)) { $stderrText.Trim() } elseif ([string]::IsNullOrWhiteSpace($raw)) { 'Empty response' } else { $raw.Trim() }
          raw_response = if ($IncludeRaw -and -not [string]::IsNullOrWhiteSpace($raw)) { $raw } else { $null }
        }
      }

      try {
        $parsed = $raw | ConvertFrom-Json
        $choice = $parsed.choices[0]
        $message = $choice.message
        return [pscustomobject]@{
          provider = $Name
          status = 'success'
          attempt_mode = 'parallel'
          selected = $false
          exit_code = $exitCode
          response_model = $parsed.model
          content = $message.content
          reasoning_content = $message.reasoning_content
          error = $null
          raw_response = if ($IncludeRaw) { $parsed } else { $null }
        }
      } catch {
        Remove-Item -LiteralPath $outFile -ErrorAction SilentlyContinue
        return [pscustomobject]@{
          provider = $Name
          status = 'failed'
          attempt_mode = 'parallel'
          selected = $false
          exit_code = $exitCode
          response_model = $null
          content = $null
          reasoning_content = $null
          error = "Invalid JSON response: $($_.Exception.Message)"
          raw_response = if ($IncludeRaw) { $raw } else { $null }
        }
      }

      Remove-Item -LiteralPath $outFile -ErrorAction SilentlyContinue
    } -ArgumentList $provider, $scriptPath, $ProviderQuery, $ProviderMaxTokens, $ProviderTimeoutSec, $(if ($KeepResponse) { 1 } else { 0 })
  }

  if ($jobs.Count -gt 0) {
    Wait-Job -Job $jobs -Timeout $ParallelJobTimeoutSec | Out-Null
  }

  $timedOutJobs = @(
    $jobs | Where-Object {
      $_.State -notin @('Completed', 'Failed', 'Stopped')
    }
  )

  $received = @()
  foreach ($job in $timedOutJobs) {
    Stop-Job -Job $job -ErrorAction SilentlyContinue | Out-Null
    $received += New-ProviderFailureResult -Provider $job.Name -AttemptMode 'parallel' -ExitCode 408 -ErrorMessage "Dispatcher timeout after $ParallelJobTimeoutSec seconds."
  }

  foreach ($job in $jobs) {
    if ($timedOutJobs.Id -contains $job.Id) {
      Remove-Job -Job $job -Force | Out-Null
      continue
    }

    try {
      $jobOutput = Receive-Job -Job $job -ErrorAction Stop
      if ($null -eq $jobOutput) {
        $received += New-ProviderFailureResult -Provider $job.Name -AttemptMode 'parallel' -ExitCode 500 -ErrorMessage 'Parallel provider job returned no structured result.'
      } else {
        $received += $jobOutput
      }
    } catch {
      $received += New-ProviderFailureResult -Provider $job.Name -AttemptMode 'parallel' -ExitCode 500 -ErrorMessage "Parallel provider job failed: $($_.Exception.Message)"
    }
    Remove-Job -Job $job -Force | Out-Null
  }

  return $received
}

$orderedProviders = @()
foreach ($provider in $PreferredOrder) {
  $candidateProviders = @($provider -split '[,;]') | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
  foreach ($candidateProvider in $candidateProviders) {
    $normalized = $candidateProvider.Trim().ToLowerInvariant()
    if ($providerScripts.ContainsKey($normalized) -and $orderedProviders -notcontains $normalized) {
      $orderedProviders += $normalized
    }
  }
}

if ($orderedProviders.Count -eq 0) {
  Write-Error 'No supported providers were requested.'
  exit 2
}

$providerResults = Get-InitialProviderState -Providers $orderedProviders
$channelFailures = @()
$fallbackActions = @()
$successProviders = @()
$attemptedProviders = @()
$fallbackTaken = $false

if ($Mode -eq 'parallel') {
  $results = Invoke-ParallelProviders -Providers $orderedProviders -ProviderQuery $Query -ProviderMaxTokens $MaxTokens -ProviderTimeoutSec $ProviderTimeoutSec -ParallelJobTimeoutSec $JobTimeoutSec -KeepResponse ([bool]$IncludeResponses)
  foreach ($result in $results) {
    $attemptedProviders += $result.provider
    $match = $providerResults | Where-Object { $_.provider -eq $result.provider } | Select-Object -First 1
    $match.status = $result.status
    $match.attempt_mode = $result.attempt_mode
    $match.exit_code = $result.exit_code
    $match.response_model = $result.response_model
    $match.content = $result.content
    $match.reasoning_content = $result.reasoning_content
    $match.error = $result.error
    $match.raw_response = $result.raw_response

    if ($result.status -eq 'success') {
      $successProviders += $result.provider
      $channelFailures = Remove-ChannelFailuresForProvider -Failures $channelFailures -Provider $result.provider
    } else {
      $channelFailures = Add-OrReplaceChannelFailure -Failures $channelFailures -Provider $result.provider -ExitCode $result.exit_code -ErrorMessage $result.error -AttemptMode $result.attempt_mode
    }
  }

  if ($successProviders.Count -gt 0 -and $successProviders.Count -lt $orderedProviders.Count) {
    $fallbackTaken = $true
    $fallbackActions += "Parallel attempt partially failed; continue with success providers: $($successProviders -join ', ')"
  }

  if ($successProviders.Count -lt $MinSuccessCount) {
    $retryProviders = @(
      $orderedProviders | Where-Object { $successProviders -notcontains $_ }
    )

    if ($retryProviders.Count -gt 0) {
      $fallbackTaken = $true
      $fallbackActions += "Parallel attempt reached $($successProviders.Count) success(es), below min_success_count=$MinSuccessCount; retry remaining providers sequentially."
    }

    foreach ($provider in $retryProviders) {
      $attemptedProviders += $provider
      $result = Invoke-ProviderOnce -Provider $provider -ProviderScript $providerScripts[$provider] -ProviderQuery $Query -ProviderMaxTokens $MaxTokens -ProviderTimeoutSec $ProviderTimeoutSec -AttemptMode 'fallback_after_parallel' -KeepResponse ([bool]$IncludeResponses)
      $match = $providerResults | Where-Object { $_.provider -eq $provider } | Select-Object -First 1
      $match.status = $result.status
      $match.attempt_mode = $result.attempt_mode
      $match.exit_code = $result.exit_code
      $match.response_model = $result.response_model
      $match.content = $result.content
      $match.reasoning_content = $result.reasoning_content
      $match.error = $result.error
      $match.raw_response = $result.raw_response

      if ($result.status -eq 'success') {
        if ($successProviders -notcontains $provider) {
          $successProviders += $provider
        }
        $channelFailures = Remove-ChannelFailuresForProvider -Failures $channelFailures -Provider $provider
        $fallbackActions += "Sequential retry recovered provider $provider after parallel failure."
      } else {
        $channelFailures = Add-OrReplaceChannelFailure -Failures $channelFailures -Provider $result.provider -ExitCode $result.exit_code -ErrorMessage $result.error -AttemptMode $result.attempt_mode
      }

      if ($successProviders.Count -ge $MinSuccessCount) {
        break
      }
    }
  }
} elseif ($Mode -eq 'fallback') {
  foreach ($provider in $orderedProviders) {
    $attemptedProviders += $provider
    $result = Invoke-ProviderOnce -Provider $provider -ProviderScript $providerScripts[$provider] -ProviderQuery $Query -ProviderMaxTokens $MaxTokens -ProviderTimeoutSec $ProviderTimeoutSec -AttemptMode 'fallback' -KeepResponse ([bool]$IncludeResponses)
    $match = $providerResults | Where-Object { $_.provider -eq $provider } | Select-Object -First 1
    $match.status = $result.status
    $match.attempt_mode = $result.attempt_mode
    $match.exit_code = $result.exit_code
    $match.response_model = $result.response_model
    $match.content = $result.content
    $match.reasoning_content = $result.reasoning_content
    $match.error = $result.error
    $match.raw_response = $result.raw_response

    if ($result.status -eq 'success') {
      $successProviders += $provider
      $channelFailures = Remove-ChannelFailuresForProvider -Failures $channelFailures -Provider $provider
      if ($successProviders.Count -ge $MinSuccessCount) {
        break
      }
    } else {
      $fallbackTaken = $true
      $channelFailures = Add-OrReplaceChannelFailure -Failures $channelFailures -Provider $result.provider -ExitCode $result.exit_code -ErrorMessage $result.error -AttemptMode $result.attempt_mode
      $fallbackActions += "Provider $provider failed; fallback to next provider in order."
    }
  }

  foreach ($provider in $orderedProviders) {
    if ($attemptedProviders -notcontains $provider) {
      $match = $providerResults | Where-Object { $_.provider -eq $provider } | Select-Object -First 1
      $match.status = 'skipped'
      $match.attempt_mode = 'fallback'
    }
  }
} else {
  $provider = $orderedProviders[0]
  $attemptedProviders += $provider
  $result = Invoke-ProviderOnce -Provider $provider -ProviderScript $providerScripts[$provider] -ProviderQuery $Query -ProviderMaxTokens $MaxTokens -ProviderTimeoutSec $ProviderTimeoutSec -AttemptMode 'single' -KeepResponse ([bool]$IncludeResponses)
  $match = $providerResults | Where-Object { $_.provider -eq $provider } | Select-Object -First 1
  $match.status = $result.status
  $match.attempt_mode = $result.attempt_mode
  $match.exit_code = $result.exit_code
  $match.response_model = $result.response_model
  $match.content = $result.content
  $match.reasoning_content = $result.reasoning_content
  $match.error = $result.error
  $match.raw_response = $result.raw_response

  if ($result.status -eq 'success') {
    $successProviders += $provider
    $channelFailures = Remove-ChannelFailuresForProvider -Failures $channelFailures -Provider $provider
  } else {
    $channelFailures = Add-OrReplaceChannelFailure -Failures $channelFailures -Provider $result.provider -ExitCode $result.exit_code -ErrorMessage $result.error -AttemptMode $result.attempt_mode
  }

  foreach ($other in $orderedProviders | Select-Object -Skip 1) {
    $matchOther = $providerResults | Where-Object { $_.provider -eq $other } | Select-Object -First 1
    $matchOther.status = 'skipped'
    $matchOther.attempt_mode = 'single'
  }
}

foreach ($provider in $successProviders) {
  $match = $providerResults | Where-Object { $_.provider -eq $provider } | Select-Object -First 1
  $match.selected = $true
}

if (-not [bool]$IncludeResponses) {
  foreach ($item in $providerResults) {
    $item.raw_response = $null
  }
}

$brainChainStatus = switch ($successProviders.Count) {
  0 { 'all_unavailable' }
  1 { 'single_available' }
  default { 'dual_available' }
}

$degradedRun = $brainChainStatus -ne 'dual_available'

if ($brainChainStatus -eq 'all_unavailable' -and $fallbackActions.Count -eq 0) {
  $fallbackActions += 'All external-brain chains unavailable; continue only if discovery and validation channels remain sufficient.'
}

$summary = [pscustomobject]@{
  requested_mode = $Mode
  preferred_order = $orderedProviders
  min_success_count = $MinSuccessCount
  provider_timeout_sec = $ProviderTimeoutSec
  job_timeout_sec = $JobTimeoutSec
  attempted_providers = @($attemptedProviders | Select-Object -Unique)
  selected_providers = @($successProviders | Select-Object -Unique)
  success_count = $successProviders.Count
  brain_chain_status = $brainChainStatus
  degraded_run = $degradedRun
  fallback_taken = $fallbackTaken
  channel_failures = $channelFailures
  fallback_actions = $fallbackActions
  provider_results = $providerResults
  completed_at = (Get-Date).ToString('s')
}

$summaryJson = $summary | ConvertTo-Json -Depth 20
[Console]::Out.Write((ConvertTo-AsciiSafeJson -JsonText $summaryJson))

if ($successProviders.Count -ge $MinSuccessCount) {
  exit 0
}

exit 1
