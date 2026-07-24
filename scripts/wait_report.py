from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _fmt(seconds: float) -> str:
    minutes, remainder = divmod(max(0.0, seconds), 60.0)
    hours, minutes = divmod(int(minutes), 60)
    if hours:
        return f"{hours}h {minutes:02d}m {remainder:04.1f}s"
    if minutes:
        return f"{minutes}m {remainder:04.1f}s"
    return f"{remainder:.3f}s"


def build_report(current: dict, previous: dict, now: float) -> tuple[str, dict]:
    categories = current.get("categories", {})
    old_categories = previous.get("categories", {})
    rows = []
    for name, values in categories.items():
        old = old_categories.get(name, {})
        total_seconds = float(values.get("seconds", 0.0))
        total_calls = int(values.get("calls", 0))
        delta_seconds = max(0.0, total_seconds - float(old.get("seconds", 0.0)))
        delta_calls = max(0, total_calls - int(old.get("calls", 0)))
        if delta_calls or delta_seconds:
            rows.append((delta_seconds, name, delta_calls, total_seconds, total_calls))
    rows.sort(reverse=True)
    elapsed = max(0.0, now - float(previous.get("reported_at_epoch", current.get("started_at_epoch", now))))
    interval_total = sum(row[0] for row in rows)
    lines = [
        f"wait report: interval={_fmt(elapsed)} intentional_wait={_fmt(interval_total)}",
        f"cumulative={_fmt(float(current.get('total_seconds', 0.0)))} calls={int(current.get('total_calls', 0))}",
    ]
    if rows:
        for delta_seconds, name, delta_calls, total_seconds, total_calls in rows:
            interval_average = delta_seconds / delta_calls if delta_calls else 0.0
            lines.append(
                f"- {name}: +{_fmt(delta_seconds)} / {delta_calls} calls "
                f"(avg {_fmt(interval_average)}; total {_fmt(total_seconds)} / {total_calls})"
            )
    else:
        lines.append("- no recorded waits in this interval")
    checkpoint = {
        "reported_at_epoch": now,
        "reported_at": datetime.fromtimestamp(now).astimezone().isoformat(timespec="seconds"),
        "categories": categories,
    }
    return "\n".join(lines), checkpoint


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    args = parser.parse_args()
    current = _read(args.log)
    previous = _read(args.state)
    now = time.time()
    report, checkpoint = build_report(current, previous, now)
    print(report)
    _write(args.state, checkpoint)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
