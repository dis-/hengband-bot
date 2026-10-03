<#
.SYNOPSIS
  Rebuild the decision-ladder page and publish it to GitHub Pages.

.DESCRIPTION
  Regenerates docs/data/ladder.json from the ladder and the decision logs,
  then copies what Pages serves (index.html, data/, .nojekyll) into the
  gh-pages worktree and pushes it.  main keeps the sources; gh-pages holds
  only the served files, so publishing the page never pushes unrelated work.

  The worktree lives outside the repository and outside bot-client, at a
  short path: checking the full tree out under a long path fails on Windows.

.PARAMETER Worktree
  Where the gh-pages worktree lives (created on first run).

.PARAMETER SkipBuild
  Publish docs/ as it stands, without regenerating ladder.json.
#>
[CmdletBinding()]
param(
    [string] $Worktree = 'C:\hb-ghpages',
    [switch] $SkipBuild
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$docs = Join-Path $repo 'docs'

if (-not $SkipBuild) {
    Write-Host '==> building docs/data/ladder.json'
    python (Join-Path $PSScriptRoot 'build_ladder_page.py')
    if ($LASTEXITCODE -ne 0) { throw "build_ladder_page.py failed ($LASTEXITCODE)" }
}

if (-not (Test-Path (Join-Path $Worktree '.git'))) {
    Write-Host "==> adding the gh-pages worktree at $Worktree"
    git -C $repo fetch origin gh-pages
    git -C $repo worktree add $Worktree gh-pages
    if ($LASTEXITCODE -ne 0) { throw 'could not add the gh-pages worktree' }
} else {
    git -C $Worktree fetch origin gh-pages
    git -C $Worktree reset --hard origin/gh-pages
}

Write-Host '==> copying the served files'
Copy-Item (Join-Path $docs 'index.html') $Worktree -Force
Copy-Item (Join-Path $docs '.nojekyll') $Worktree -Force
New-Item -ItemType Directory -Force (Join-Path $Worktree 'data') | Out-Null
Copy-Item (Join-Path $docs 'data\ladder.json') (Join-Path $Worktree 'data') -Force

git -C $Worktree add -A
if (@(git -C $Worktree status --porcelain).Count -eq 0) {
    Write-Host '==> nothing changed; not publishing'
    exit 0
}

$stamp = Get-Date -Format 'yyyy-MM-dd HH:mm'
git -C $Worktree commit -q -m "Refresh the decision-ladder page ($stamp)"
if ($LASTEXITCODE -ne 0) { throw 'commit failed' }
git -C $Worktree push -q origin gh-pages
if ($LASTEXITCODE -ne 0) { throw 'push failed' }
Write-Host '==> published: https://dis-.github.io/hengband-bot/'
