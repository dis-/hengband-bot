"""Operator-side auto-recovery loop (user decision 2026-10-01, plan item 3).

Watches the live bot process.  When the bot exits while the game is alive and no
maintenance hold is set, it preserves the evidence, closes any open game UI
with ESC, and resumes the bot through the hengband-bot-play skill.  It never
touches policy code.

It stops for real (exit code 3, touches jsonlog/maintenance.hold) when:
  * the same stop reason occurs 3 times within 30 minutes,
  * the game process is gone, or the stop output mentions death,
  * a resume itself fails.
Every event is appended to jsonlog/autorecover.jsonl for the 10-restart review
(revert criteria in the memory file run-continuously-plan-decision-20261001).
"""

from __future__ import annotations

import datetime as dt
import gzip
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(r"C:\hengband\bot-client")
J = ROOT / "jsonlog"
HOLD = J / "maintenance.hold"
EVENTS = J / "autorecover.jsonl"
SKILL = Path(os.environ["USERPROFILE"]) / ".claude" / "skills" / "hengband-bot-play" / "scripts"
WINDOW_S = 30 * 60
SAME_REASON_LIMIT = 3
POLL_S = 10


def now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def log(event: dict) -> None:
    event = {"time": now(), **event}
    with EVENTS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")
    print(json.dumps(event, ensure_ascii=False), flush=True)


def bot_pids() -> list[int]:
    """Live bot processes found by command line, not by bot.pid.

    The skill's Set-Content of bot.pid can fail with a sharing violation while
    the new bot starts (2026-10-02 06:00), leaving a stale pid; trusting it made
    the supervisor declare a running bot dead.  Also rewrites bot.pid so the
    skill's status/stop see the real process.
    """
    script = ("Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and "
              "$_.CommandLine -match '-m hengbot' -and $_.CommandLine -match 'bot-state-fixed' } | "
              "ForEach-Object { $_.ProcessId }")
    out = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                         capture_output=True, text=True, timeout=60)
    pids = [int(x) for x in out.stdout.split() if x.isdigit()]
    if len(pids) == 1:
        try:
            if (J / "bot.pid").read_text().strip() != str(pids[0]):
                (J / "bot.pid").write_text(str(pids[0]))
        except OSError:
            pass
    elif not pids:
        # A stale bot.pid whose number Windows reused for another process makes
        # the skill refuse to resume ("already running", 2026-10-02 09:00).
        try:
            (J / "bot.pid").unlink()
        except OSError:
            pass
    return pids


def pid_alive(path: Path) -> bool:
    try:
        pid = int(path.read_text().strip())
    except (OSError, ValueError):
        return False
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True)
    return str(pid) in out.stdout


def died_prompt() -> bool:
    """The game's death prompt 「画面を保存しますか？」 (player-damage.cpp) as
    the bot's stuck-prompt line reports it.  The stderr log carries the game
    text in cp932 (2026-10-03 05:33: a death was treated as a stuck prompt,
    resumed, and escalated only as resume-failed)."""
    try:
        err = (J / "bot-stderr.log").read_bytes()[-8000:]
    except OSError:
        return False
    text = "画面を保存しますか"
    return text.encode("cp932") in err or text.encode("utf-8") in err


def stop_reason() -> str:
    """Normalised reason from the last marker the bot printed."""
    try:
        tail = (J / "bot-stdout.log").read_text(encoding="utf-8", errors="replace")[-4000:]
    except OSError:
        tail = ""
    try:
        err = (J / "bot-stderr.log").read_text(encoding="utf-8", errors="replace")[-4000:]
    except OSError:
        err = ""
    if "Traceback" in err:
        last = [l for l in err.splitlines() if l.strip()][-1:]
        return "crash:" + (last[0][:120] if last else "unknown")
    markers = re.findall(r"<([a-z][a-z0-9:_\-]*)[^>]*>", tail)
    markers = [m for m in markers if m not in {"identify:staged-tail-released", "floor-transition:esc"}]
    if not markers:
        # A stuck prompt is reported on stderr only (2026-10-02 18:28-18:33,
        # three "exit:no-marker" stops that were one named prompt stop).
        stuck = re.findall(r"<stuck-prompt> owner=(\S+)", err)
        if stuck:
            return "stuck-prompt:" + stuck[-1]
        return "exit:no-marker"
    # Collapse variable parts (request ids, counts) so repeats match.
    return re.sub(r"\d+", "#", markers[-1])


def preserve(tag: str) -> str:
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    base = J / f"autorecover-{stamp}-{re.sub(r'[^a-z0-9]+', '-', tag.lower())[:60]}"
    for name, n in (("bot-decisions.jsonl", 3_000_000), ("bot-posted-characters.jsonl", 1_000_000),
                    ("bot-state-fixed.jsonl", 3_000_000)):
        src = J / name
        if not src.exists():
            continue
        with src.open("rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - n))
            data = fh.read()
        if size > n:
            data = data[data.find(b"\n") + 1:]
        with gzip.open(f"{base}.{name}.gz", "wb") as gz:
            gz.write(data)
    for name in ("bot-stdout.log", "bot-stderr.log"):
        if (J / name).exists():
            shutil.copy(J / name, f"{base}.{name}")
    return base.name


def esc_game() -> None:
    gp = (J / "hengband.pid").read_text().strip()
    for _ in range(3):
        subprocess.run([sys.executable, str(SKILL / "send-hengband-key.py"), "--pid", gp, "--codepoint", "27"],
                       capture_output=True)
        time.sleep(0.6)


def resume() -> bool:
    ps = SKILL / "hengband-bot-play.ps1"
    # The skill starts the bot as a long-lived child that inherits handles, so
    # never capture or wait on its output; detach and watch bot.pid instead.
    # DETACHED_PROCESS leaves PowerShell without a console and the skill does
    # nothing; CREATE_NO_WINDOW works (verified with -Action status).
    flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    with (J / "autorecover-resume.log").open("a", encoding="utf-8") as out:
        subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps),
                          "-Action", "resume", "-EnforceCrossareaFundraising"],
                         stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
                         creationflags=flags, close_fds=True)
    deadline = time.time() + 120
    while time.time() < deadline:
        time.sleep(5)
        if bot_pids():
            return True
    return False


def town_cycle() -> str | None:
    """Same narrow-cycle rule as the operator watcher: the last 200 decisions,
    all in town, use at most 3 distinct non-periodic reasons."""
    try:
        with (J / "bot-decisions.jsonl").open("rb") as fh:
            fh.seek(0, 2)
            fh.seek(max(0, fh.tell() - 4_000_000))
            lines = fh.read().decode("utf-8", "replace").splitlines()[-200:]
    except OSError:
        return None
    reasons, levels = [], set()
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if "decision_sequence" not in row:
            return None  # a session boundary inside the window: too early to judge
        reason = row.get("reason") or ""
        if reason.startswith("periodic:"):
            continue
        reasons.append(reason)
        levels.add((row.get("floor") or {}).get("level"))
    if len(reasons) >= 150 and len(set(reasons)) <= 3 and levels == {0}:
        return "cycle:" + "|".join(sorted(set(reasons)))[:150]
    return None


def stop_bot() -> None:
    for pid in bot_pids():
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
    time.sleep(3)


def main() -> int:
    history: list[tuple[float, str]] = []
    log({"event": "start"})
    while True:
        time.sleep(POLL_S)
        if HOLD.exists():
            continue
        cycle = None
        if bot_pids():
            cycle = town_cycle()
            if cycle is None:
                continue
            stop_bot()
        reason = cycle or stop_reason()
        if not pid_alive(J / "hengband.pid"):
            log({"event": "escalate", "why": "game-dead", "reason": reason})
            return 3
        tail = (J / "bot-stdout.log").read_text(encoding="utf-8", errors="replace")[-2000:]
        if "player-death" in tail or "死んだ" in tail or died_prompt():
            HOLD.touch()
            log({"event": "escalate", "why": "death", "reason": reason})
            return 3
        captured = preserve(reason)
        t = time.time()
        history = [(ts, r) for ts, r in history if t - ts < WINDOW_S] + [(t, reason)]
        repeats = sum(1 for _, r in history if r == reason)
        if repeats >= SAME_REASON_LIMIT:
            HOLD.touch()
            log({"event": "escalate", "why": f"same-reason-x{repeats}-in-30min", "reason": reason,
                 "captured": captured})
            return 3
        if bot_pids():
            log({"event": "skip", "why": "bot-still-running-after-stop", "reason": reason})
            continue
        esc_game()
        ok = resume()
        log({"event": "restart", "reason": reason, "captured": captured, "repeats_in_window": repeats,
             "resumed": ok})
        if not ok:
            HOLD.touch()
            log({"event": "escalate", "why": "resume-failed", "reason": reason})
            return 3


if __name__ == "__main__":
    raise SystemExit(main())
