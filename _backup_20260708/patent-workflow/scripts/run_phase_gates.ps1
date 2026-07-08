Param(
  [Parameter(Mandatory=$true)]
  [ValidateSet('2','4','7','10','11','all')]
  [string]$Phase,

  [string]$Workspace = '.',

  [string]$Manifest = 'artifacts/run_manifest.md',

  # Phase 11 only
  [string]$DeliverDir,
  [string]$PatentTitle,

  [string]$Out
)

$py = 'python'
$script = Join-Path $Workspace 'skills/patent-workflow/scripts/run_phase_gates.py'

if (-not (Test-Path $script)) {
  throw "run_phase_gates.py not found: $script"
}

$cmd = @($py, $script, '--phase', $Phase, '--workspace', $Workspace)

if ($Manifest) {
  $cmd += @('--manifest', $Manifest)
}

if ($Out) {
  $cmd += @('--out', $Out)
}

if ($Phase -eq '11') {
  if (-not $DeliverDir -or -not $PatentTitle) {
    throw "Phase 11 requires -DeliverDir and -PatentTitle"
  }
  $cmd += @('--deliver-dir', $DeliverDir, '--patent-title', $PatentTitle)
}

Write-Host "Running: $($cmd -join ' ')"
& $cmd[0] $cmd[1..($cmd.Length-1)]

exit $LASTEXITCODE
