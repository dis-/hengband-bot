#!/usr/bin/env python3
"""Progress invariants for the supervision fronts: bot, measurement, review.

Reads only artifacts the bot and git already produce - no front may depend on
an agent self-reporting, because self-reporting makes the operator the
detector.  Writes nothing under the bot's runtime directory; its own verdict
files live in ``%LOCALAPPDATA%\\hengbot-supervisor``.  Run from inside the
packaged Claude app, Windows redirects that write to
``%LOCALAPPDATA%\\Packages\\<family>\\LocalCache\\Local\\hengbot-supervisor``;
supervisor_notify.ps1 looks there too.

Exit code 1 when any front is stalled, so a scheduled task can act on it.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from supervise import identified_alive  # noqa: E402  (scripts/ is not a package)

FRONTS = ("bot", "measurement", "review")
DEFAULT_BOT_IDENTITY = "hengbot"
# The decision log advances every few seconds; ownership metrics emit a
# decision-progress row a minute.  The unpushed-commit window is the review
# round's own budget.
BOT_IDLE_SECONDS = 120
MEASUREMENT_IDLE_SECONDS = 180
REVIEW_UNPUSHED_SECONDS = 60 * 60
TAIL_BYTES = 512 * 1024
# Windows PowerShell's `-Encoding utf8` prepends this to every artifact it
# writes; it is a mark, never content, and a cp932 console cannot encode it.
BOM = "﻿"


def strip_bom(text: str) -> str:
    return text.lstrip(BOM)


def read_artifact(path: Path) -> str | None:
    """A text artifact's content, or None when it cannot be read.

    Never raises on the encoding of what it reads: an artifact written by
    PowerShell carries a BOM, and one written by a Japanese-speaking operator
    carries text no console codec here is guaranteed to represent.
    """
    try:
        return strip_bom(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return None


def configure_stdout(stream=None) -> None:
    """Make stdout survive text the console codec cannot represent.

    The checker prints what it reads, so a cp932 console would otherwise let a
    Japanese hold reason - or a single BOM - kill the very process that exists
    to notice a stall.
    """
    stream = sys.stdout if stream is None else stream
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None:
        return
    try:
        reconfigure(encoding="utf-8", errors="replace")
    except (OSError, ValueError, LookupError):
        try:
            reconfigure(errors="replace")
        except (OSError, ValueError, LookupError):
            pass


def emit(line: str, stream=None) -> None:
    """Print a line even when the stream's codec cannot encode it."""
    stream = sys.stdout if stream is None else stream
    try:
        print(line, file=stream)
        return
    except UnicodeEncodeError:
        pass
    encoding = getattr(stream, "encoding", None) or "ascii"
    try:
        safe = line.encode(encoding, errors="replace").decode(encoding, errors="replace")
    except (LookupError, UnicodeError):
        safe = line.encode("ascii", errors="replace").decode("ascii")
    print(safe, file=stream)


def state_dir(explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit)
    configured = os.environ.get("HENGBOT_SUPERVISOR_STATE_DIR", "").strip()
    if configured:
        return Path(configured)
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("TMPDIR") or "."
    return Path(base) / "hengbot-supervisor"


def parse_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def tail_rows(path: Path, rows: int, tail_bytes: int = TAIL_BYTES) -> list[dict]:
    """The last parseable JSON objects of a JSONL file, oldest first."""
    try:
        with path.open("rb") as stream:
            stream.seek(0, os.SEEK_END)
            start = max(0, stream.tell() - tail_bytes)
            stream.seek(start)
            blob = stream.read()
    except OSError:
        return []
    lines = blob.decode("utf-8", errors="replace").splitlines()
    if start and lines:
        lines = lines[1:]  # the first line was cut in half by the seek
    parsed: list[dict] = []
    for line in lines[-max(rows * 4, rows):]:
        # A byte-order mark survives the seek when a PowerShell-written file is
        # read from its start, and would otherwise hide the row behind a
        # decode error.
        line = strip_bom(line.strip())
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            parsed.append(row)
    return parsed[-rows:]


def read_pid(path: Path) -> int | None:
    text = read_artifact(path)
    if text is None:
        return None
    try:
        return int(text.strip())
    except ValueError:
        return None


def format_age(seconds: float) -> str:
    seconds = int(max(0, seconds))
    if seconds < 90:
        return f"{seconds}s"
    minutes, rest = divmod(seconds, 60)
    if minutes < 90:
        return f"{minutes}m{rest:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m"


def git_output(root: Path, *arguments: str) -> str | None:
    try:
        run = subprocess.run(["git", "-C", str(root), *arguments],
                             capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return run.stdout.strip() if run.returncode == 0 else None


def bot_front(root: Path, now: datetime, alive: bool,
              identity_evidence: str) -> tuple[bool, str]:
    runtime = root / "jsonlog"
    hold = runtime / "maintenance.hold"
    decisions = tail_rows(runtime / "bot-decisions.jsonl", 1)
    last = decisions[-1] if decisions else {}
    last_time = parse_time(last.get("time"))
    sequence = last.get("decision_sequence")
    age = (now - last_time).total_seconds() if last_time else None
    decision_note = (f"last decision #{sequence} {format_age(age)} ago"
                     if age is not None else "no decision row on disk")
    if alive:
        if age is None or age > BOT_IDLE_SECONDS:
            return False, f"{identity_evidence} but {decision_note} (> {BOT_IDLE_SECONDS}s)"
        return True, f"{identity_evidence}, {decision_note}"
    if hold.exists():
        text = read_artifact(hold)
        reason = text.strip().splitlines() if text else []
        if reason:
            return True, f"bot stopped under maintenance.hold ({reason[0]}), {decision_note}"
        # An empty hold file would silence this front for as long as it exists,
        # which is the stall it is meant to explain.  The hold has to carry a
        # reason to count as deliberate.
        return False, (f"{identity_evidence}, {decision_note}, "
                       f"maintenance.hold carries no reason")
    return False, f"{identity_evidence}, {decision_note}, no maintenance.hold"


def measurement_front(root: Path, now: datetime, bot_alive: bool) -> tuple[bool, str]:
    """The decision COUNT must advance, not merely a row must exist.

    Row presence alone repeats the bot front; the count delta is the only
    measurement-specific fact.
    """
    path = root / "jsonlog" / "ownership-metrics.jsonl"
    rows = tail_rows(path, 200)
    if not bot_alive:
        return True, "no live bot session to measure"
    session = None
    for row in reversed(rows):
        if row.get("kind") == "session-start":
            session = row.get("session")
            break
    ended = any(row.get("kind") == "session-end" and row.get("session") == session
                for row in rows)
    if session is None:
        return False, f"no session-start row in {path.name}"
    if ended:
        return False, f"session {session} ended while the bot process still runs"
    progress = [row for row in rows
                if row.get("kind") == "decision-progress" and row.get("session") == session]
    if not progress:
        return False, f"no decision-progress row for session {session}"
    latest = progress[-1]
    latest_time = parse_time(latest.get("time"))
    age = (now - latest_time).total_seconds() if latest_time else None
    if age is None or age > MEASUREMENT_IDLE_SECONDS:
        shown = format_age(age) if age is not None else "unknown"
        return False, (f"latest decision-progress for {session} is {shown} old "
                       f"(> {MEASUREMENT_IDLE_SECONDS}s)")
    count = latest.get("decisions")
    if len(progress) < 2:
        return True, f"first decision-progress for {session}: decisions={count}"
    previous = progress[-2]
    delta = (count or 0) - (previous.get("decisions") or 0)
    if delta <= 0:
        return False, (f"decision count stuck at {count} between "
                       f"{previous.get('time')} and {latest.get('time')}")
    return True, (f"decisions {previous.get('decisions')} -> {count} (+{delta}) "
                  f"in the last {format_age(age)}")


def review_front(root: Path, now: datetime) -> tuple[bool, str]:
    count_text = git_output(root, "rev-list", "--count", "origin/main..main")
    if count_text is None:
        return True, "no git repository or no origin/main to compare"
    try:
        count = int(count_text)
    except ValueError:
        return True, f"unreadable rev-list output {count_text!r}"
    if count == 0:
        return True, "no unpushed commits on main"
    log = git_output(root, "log", "--reverse", "--format=%cI %h %s", "origin/main..main")
    oldest = (log or "").splitlines()[0] if log else ""
    stamp, _, rest = oldest.partition(" ")
    committed = parse_time(stamp)
    if committed is None:
        return False, f"{count} unpushed commits on main, oldest age unknown"
    age = (now - committed).total_seconds()
    summary = f"{count} unpushed commits on main, oldest {format_age(age)} old ({rest})"
    if age > REVIEW_UNPUSHED_SECONDS:
        return False, summary
    return True, summary


def check(root: Path, now: datetime, identity: str) -> dict:
    alive, identity_evidence = identified_alive(read_pid(root / "jsonlog" / "bot.pid"), identity)
    bot_ok, bot_evidence = bot_front(root, now, alive, identity_evidence)
    measurement_ok, measurement_evidence = measurement_front(root, now, alive)
    review_ok, review_evidence = review_front(root, now)
    fronts = {
        "bot": {"ok": bot_ok, "evidence": bot_evidence},
        "measurement": {"ok": measurement_ok, "evidence": measurement_evidence},
        "review": {"ok": review_ok, "evidence": review_evidence},
    }
    return {
        "time": now.isoformat(),
        "root": str(root),
        "fronts": fronts,
        "stalled": [name for name in FRONTS if not fronts[name]["ok"]],
    }


def write_verdict(directory: Path, source: str, verdict: dict) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"verdict-{source}.json"
    temporary = directory / f"verdict-{source}.{os.getpid()}.tmp"
    temporary.write_text(json.dumps(verdict, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, path)
    return path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(_SCRIPTS.parent),
                        help="repository root holding jsonlog/ (default: this checkout)")
    parser.add_argument("--state-dir", default=None,
                        help="where the verdict file is written (default: %%LOCALAPPDATA%%)")
    parser.add_argument("--source", default="session", choices=("session", "task"),
                        help="who is running the check; names the verdict file")
    parser.add_argument("--bot-identity", default=DEFAULT_BOT_IDENTITY,
                        help="substring the bot's command line must contain")
    parser.add_argument("--now", default=None, help="ISO timestamp to evaluate at (testing)")
    parser.add_argument("--quiet", action="store_true", help="print the JSON verdict only")
    arguments = parser.parse_args(argv)
    configure_stdout()
    now = parse_time(arguments.now) or datetime.now(timezone.utc).astimezone()
    verdict = check(Path(arguments.root), now, arguments.bot_identity)
    verdict["verdict_file"] = str(write_verdict(state_dir(arguments.state_dir),
                                                arguments.source, verdict))
    if not arguments.quiet:
        for name in FRONTS:
            front = verdict["fronts"][name]
            emit(f"{name} {'ok' if front['ok'] else 'stalled'}: {front['evidence']}")
    emit(json.dumps(verdict, ensure_ascii=False))
    return 1 if verdict["stalled"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
