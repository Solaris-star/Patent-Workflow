# 部署 patent skill 家族到 Claude Code 用户级 skills + agents 目录。
# 用法：pwsh -File deploy.ps1 [-DryRun]
# 其他 agent 宿主（Codex / Hermes 等）：skill 内容宿主中立，把 skills/ 下各目录
# 复制到对应宿主的技能目录即可（详见 README.md「多宿主部署」）。

param([switch]$DryRun)

$ErrorActionPreference = 'Stop'
$repoSkills = Join-Path $PSScriptRoot 'skills'
$repoAgents = Join-Path $PSScriptRoot 'agents'
$targetRoot = Join-Path $HOME '.claude\skills'
$agentRoot = Join-Path $HOME '.claude\agents'

$family = @(
  'patent', 'patent-research', 'patent-research-cli', 'patent-prior-art',
  'patent-style', 'patent-draft', 'patent-review', 'patent-deslop'
)

foreach ($s in $family) {
  $src = Join-Path $repoSkills $s
  $dst = Join-Path $targetRoot $s
  if (-not (Test-Path (Join-Path $src 'SKILL.md'))) { throw "missing SKILL.md in $src" }
  if ($DryRun) {
    Write-Host "[dry-run] $src -> $dst"
    continue
  }
  # /MIR 镜像同步：仓库是唯一真源，目标目录多余文件会被清除
  robocopy $src $dst /MIR /XD __pycache__ /NFL /NDL /NJH /NJS | Out-Null
  if ($LASTEXITCODE -ge 8) { throw "robocopy failed for $s (exit $LASTEXITCODE)" }
  Write-Host "deployed: $s"
}

# 预定义子代理（调研 scout ×4 + 审查视角 ×4）→ 用户级 agents 目录
$agentCount = 0
if (Test-Path $repoAgents) {
  if (-not $DryRun) { New-Item -ItemType Directory -Force $agentRoot | Out-Null }
  foreach ($f in Get-ChildItem $repoAgents -Filter 'patent-*.md') {
    if ($DryRun) { Write-Host "[dry-run] $($f.FullName) -> $agentRoot"; continue }
    Copy-Item $f.FullName $agentRoot -Force
    $agentCount++
    Write-Host "agent deployed: $($f.BaseName)"
  }
}

if (-not $DryRun) {
  Write-Host "`nDone. Deployed $($family.Count) skills to $targetRoot, $agentCount agents to $agentRoot"
}
exit 0
