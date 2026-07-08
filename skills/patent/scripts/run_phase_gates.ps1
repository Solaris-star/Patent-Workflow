param(
  [Parameter(Mandatory = $true)]
  [ValidateSet('research', 'prior-art', 'draft', 'review', 'deliver', 'all')]
  [string]$Gate,
  [string]$Workspace = '.',
  [string]$Manifest = 'artifacts/run_manifest.md',
  [string]$DeliverDir,
  [string]$PatentTitle
)

$ErrorActionPreference = 'Stop'
$runner = Join-Path $PSScriptRoot 'run_phase_gates.py'

$argsList = @('--gate', $Gate, '--workspace', $Workspace)
if ($Manifest) { $argsList += @('--manifest', $Manifest) }
if ($DeliverDir) { $argsList += @('--deliver-dir', $DeliverDir) }
if ($PatentTitle) { $argsList += @('--patent-title', $PatentTitle) }

python $runner @argsList
exit $LASTEXITCODE
