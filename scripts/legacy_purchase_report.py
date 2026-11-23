"""Count which selector chose the shop purchases: the rungs table or the legacy order.

Review 2026-11-23 (b)-6, owner 「数を見てから一本化する」: the bots write one row per composed
shop purchase to ``purchase-source.jsonl`` beside their decision log
(``hengbot.purchase_source_journal``).  This script reads those files (and their rotated
generations ``purchase-source.jsonl.1`` ...) under the given paths and prints, per bot:

- the purchases by source (``rungs`` / ``legacy`` / the errands / ``survival``);
- the legacy order's purchases by the rung of the table the ware closes (its category and tier),
  and how often the table alone would have bought the same ware on that page;
- the wares only the legacy order buys (no rung of the table matches them, before or after
  the absorbed-power filter, and the table alone buys something else), by name;
- the wares where the table would have bought something else, by (legacy ware -> table ware).

A composed buy that was not posted (an outside composition chose otherwise) is composed again
on a later decision at the same gold: rows with the same bot, town visit, store, ware and gold
are counted once.

Usage::

    python scripts/legacy_purchase_report.py <dir-or-file> [...] [--json] [--top N]

A directory is searched recursively.  The bot of a file is the nearest ancestor directory named
like ``n1-a`` (else the file's directory name).
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

FILE_NAME = "purchase-source.jsonl"
BOT_DIRECTORY = re.compile(r"^n\d+-[a-z]$")
_GENERATION = re.compile(re.escape(FILE_NAME) + r"(\.\d+)?(\.gz)?$")


def journal_files(paths) -> list[Path]:
    found = []
    for path in paths:
        path = Path(path)
        if path.is_file():
            found.append(path)
        elif path.is_dir():
            found.extend(candidate for candidate in sorted(path.rglob(FILE_NAME + "*"))
                         if candidate.is_file() and _GENERATION.fullmatch(candidate.name))
    return found


def bot_of(path: Path) -> str:
    for parent in path.parents:
        if BOT_DIRECTORY.match(parent.name):
            return parent.name
    return path.parent.name or "?"


def rows_of(path: Path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict) and row.get("source"):
                yield row


def _ware_name(ware) -> str:
    if not isinstance(ware, dict):
        return "-"
    return f"{ware.get('name')} ({ware.get('tval')}:{ware.get('sval')})"


def summarize(paths) -> dict:
    seen = set()
    bots: dict[str, dict] = {}
    for path in journal_files(paths):
        bot = bot_of(path)
        for row in rows_of(path):
            ware = row.get("ware") or {}
            identity = (bot, row.get("epoch"), row.get("store"), ware.get("name"),
                        ware.get("tval"), ware.get("sval"), row.get("gold"))
            if identity in seen:
                continue
            seen.add(identity)
            summary = bots.setdefault(bot, {
                "purchases": 0, "by_source": Counter(),
                "legacy_by_rung": defaultdict(lambda: {"count": 0, "table_agrees": 0}),
                "legacy_only": Counter(), "table_differs": Counter(),
            })
            summary["purchases"] += 1
            source = row["source"]
            summary["by_source"][source] += 1
            if source == "rungs":
                continue
            key = (f"{row.get('category')}/{row.get('rung')}/{row.get('tier')}"
                   if row.get("rung") else "(no rung)")
            entry = summary["legacy_by_rung"][f"{source}:{key}"]
            entry["count"] += 1
            entry["table_agrees"] += bool(row.get("table_agrees"))
            if not row.get("rungs") and not row.get("rungs_unfiltered") and not row.get("table_agrees"):
                summary["legacy_only"][_ware_name(ware)] += 1
            if not row.get("table_agrees"):
                table = row.get("table")
                summary["table_differs"][
                    f"{_ware_name(ware)} -> "
                    + (_ware_name(table) + f" [{table.get('rung')}]" if table else "nothing")] += 1
    return {
        bot: {
            "purchases": summary["purchases"],
            "by_source": dict(summary["by_source"].most_common()),
            "legacy_by_rung": dict(sorted(summary["legacy_by_rung"].items(),
                                          key=lambda item: -item[1]["count"])),
            "legacy_only": dict(summary["legacy_only"].most_common()),
            "table_differs": dict(summary["table_differs"].most_common()),
        }
        for bot, summary in sorted(bots.items())
    }


def _total(report: dict) -> dict:
    total = {"purchases": 0, "by_source": Counter(), "legacy_only": Counter()}
    for summary in report.values():
        total["purchases"] += summary["purchases"]
        total["by_source"].update(summary["by_source"])
        total["legacy_only"].update(summary["legacy_only"])
    return total


def print_report(report: dict, top: int, stream=sys.stdout) -> None:
    if not report:
        print("no purchase-source rows found", file=stream)
        return
    for bot, summary in report.items():
        print(f"== {bot}: {summary['purchases']} purchases", file=stream)
        print("  by source: " + ", ".join(f"{name} {count}" for name, count
                                          in summary["by_source"].items()), file=stream)
        print("  not by the rungs table, by the rung the ware closes"
              " (count / the table alone buys the same ware):", file=stream)
        for name, entry in list(summary["legacy_by_rung"].items())[:top]:
            print(f"    {name}: {entry['count']} / {entry['table_agrees']}", file=stream)
        if summary["legacy_only"]:
            print("  wares no rung of the table wants (only the legacy order buys them):",
                  file=stream)
            for name, count in list(summary["legacy_only"].items())[:top]:
                print(f"    {name}: {count}", file=stream)
        if summary["table_differs"]:
            print("  the table alone would buy something else (legacy ware -> table's):",
                  file=stream)
            for name, count in list(summary["table_differs"].items())[:top]:
                print(f"    {name}: {count}", file=stream)
    total = _total(report)
    print(f"== all bots: {total['purchases']} purchases; by source: "
          + ", ".join(f"{name} {count}" for name, count in total["by_source"].most_common()),
          file=stream)
    print(f"   legacy-only purchases: {sum(total['legacy_only'].values())}", file=stream)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="+", type=Path,
                        help="directories (searched recursively) or purchase-source jsonl files")
    parser.add_argument("--json", action="store_true", help="print the summary as JSON")
    parser.add_argument("--top", type=int, default=20, help="rows per list (default 20)")
    args = parser.parse_args(argv)
    report = summarize(args.paths)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_report(report, args.top)
    return 0


if __name__ == "__main__":
    sys.exit(main())
