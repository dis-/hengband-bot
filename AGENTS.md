# AGENTS.md — Hengband bot (hengbot)

External Python bot that plays Hengband through the game's `--bot-json-output`
JSONL mode (see `README.md`). Developed alongside the C++ emitter on branch
`codex/bot-json-output` (PR #5488) of `dis-/hengband`.

Tests: `PYTHONPATH=src <python> -m unittest discover -s tests`
(use the codex runtime python, not the WindowsApps `python` stub).

---

## Getting a Claude Code review (Codex → Claude Code)

Claude Code can review changes headlessly — the mirror image of
`codex exec review --uncommitted`. Codex triggers it by running the `claude`
CLI as a shell command:

```
claude -p "/code-review" --output-format json
```

- `/code-review` reviews the current git diff of the working directory.
  For a GitHub PR: `claude -p "/review <pr-url>"`.
  Free-form: `claude -p "Review the uncommitted diff for correctness bugs; report file:line."`
- Run it inside the repo to review, or add `--add-dir <repo>`.

### What is required (4 things)

1. **The `claude` CLI must be runnable.** On this machine it is
   `C:\Users\user\node-portable\node-v24.17.0-win-x64\claude` (on PATH; needs
   Node). Codex's sandbox must allow executing it.

2. **Headless mode:** always pass `-p` / `--print` (one shot, prints to stdout,
   no TTY). Add `--output-format json` for a parseable result.

3. **Authentication — the real gotcha.** This machine's Claude Code is signed in
   via a session token at `C:\Users\user\.claude\.credentials.json`; there is NO
   `ANTHROPIC_API_KEY`. Codex runs as a *different* Windows user
   (`CodexSandboxOffline`) and cannot read that file, so `claude` would run
   unauthenticated. Bridge it with EITHER:
   - `ANTHROPIC_API_KEY=<key>` in Codex's environment (simplest, cross-user), OR
   - `CLAUDE_CONFIG_DIR=C:\Users\user\.claude` plus read access to that file.

4. **Non-interactive permissions.** Headless Claude still gates its tools and
   will stall on an approval prompt. Use ONE of:
   - `--permission-mode plan` — read-only, ideal for a review (no edits), OR
   - `--allowedTools "Read Grep Glob Bash"` — pre-approve the read/search tools, OR
   - `--dangerously-skip-permissions` — bypass all checks (fine inside Codex's
     own sandbox).

### Copy-paste

```bash
# bash, with an API key (recommended — works across users)
ANTHROPIC_API_KEY=sk-... claude -p "/code-review" \
  --add-dir C:\hengband\bot-client --permission-mode plan --output-format json
```

```powershell
# PowerShell equivalent
$env:ANTHROPIC_API_KEY = "sk-..."
claude -p "/code-review" --add-dir C:\hengband\bot-client --permission-mode plan --output-format json
```

```bash
# inside Codex's sandbox, bypassing prompts (no API key needed if config is shared)
claude -p "Review the uncommitted git diff for correctness bugs; list file:line findings." `
  --dangerously-skip-permissions
```

`claude -p` prints the review to stdout; Codex captures and acts on it. To wire
it into a workflow, put the `claude -p ...` call in Codex's pre-commit step or
`notify` hook.

### Notes
- For the C++ emitter, run the same command in
  `C:\hengband\.worktrees\bot-json-output` (or `--add-dir` it).
- To make this available in every Codex session (both repos), copy this section
  to a global `C:\Users\user\.codex\AGENTS.md`.
- Symmetry: the reverse (Claude → Codex) is
  `codex exec --ignore-user-config -m gpt-5.5 -s read-only review --uncommitted`
  (the `--ignore-user-config` sidesteps the config.toml `service_tier` mismatch).
