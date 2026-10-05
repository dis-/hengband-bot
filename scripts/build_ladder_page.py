"""Generate the data file behind the decision-ladder page (docs/).

The page shows the rungs of ``CLAIM_LADDER`` in the order ``_decide``
consults them, each annotated with how often the live bot actually decided
there.  Everything is derived: the ladder from ``claim_ladder.py``, the
source anchors from the policy modules, the counts from the decision logs.

    python scripts/build_ladder_page.py [--log-glob GLOB ...] [--out PATH]
"""

from __future__ import annotations

import argparse
import ast
import glob
import gzip
import io
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
sys.path.insert(0, SRC)

from hengbot import claim_ladder as cl  # noqa: E402

DEFAULT_LOGS = (
    "jsonlog/bot-decisions.jsonl",
    "jsonlog/*.bot-decisions.jsonl",
    "jsonlog/*.bot-decisions.jsonl.gz",
)
BLOB_BASE = "https://github.com/dis-/hengband-bot/blob"
DEFAULT_WINDOWS = (48,)
SECTION_ORDER = ("rewrite", "decide", "town", "fallback")

# The page is read in Japanese; the ladder names itself in English.
SECTION_LABELS = {
    "rewrite": ("書き換え", "ラダーが答えを出した後に、その答えを差し替える段"),
    "decide": ("本体の優先順位", "_decide が上から順に相談していく段"),
    "town": ("町の用事", "_decide に呼び出し点がなく、町の調停役が選ぶ段"),
    "fallback": ("最後の受け皿", "どの段も答えなかったときに拾う段"),
}
FAMILY_LABELS = {
    "bookkeeping": "記録と保存",
    "combat": "戦闘",
    "cross-town": "町の間の移動",
    "curse-enchant": "呪いと強化",
    "departure": "出発と帰還",
    "detectors": "異常の検出",
    "equipment-opt": "装備の最適化",
    "equipment-txn": "装備の取引",
    "escape": "脱出",
    "esp-threat": "テレパシーの脅威",
    "explore": "探索",
    "floor-loot": "床の戦利品",
    "fundraising": "資金稼ぎ",
    "home-errand": "自宅の用事",
    "home-scan": "自宅の確認",
    "home-visit": "自宅の訪問",
    "hunt": "狩り",
    "identification": "鑑定",
    "idle": "手待ち",
    "misc": "その他",
    "positioning": "位置取り",
    "quest-request": "クエストの受注",
    "quest-sweep": "クエストの掃討",
    "rumor": "うわさ集め",
    "shop-buy": "店での購入",
    "shop-sell": "店での売却",
    "store-router": "店の出入り",
    "survival": "生存",
    "town-plan": "町の段取り",
    "unregistered": "未登録",
}


def leading_comment(lines, lineno):
    """The contiguous ``#`` block written just above ``def`` (1-based)."""
    collected = []
    index = lineno - 2
    while index >= 0:
        stripped = lines[index].strip()
        if not stripped.startswith("#"):
            break
        text = stripped.lstrip("#").strip()
        if text.startswith("--") or not text:
            break
        collected.append(text)
        index -= 1
    return " ".join(reversed(collected)).strip()


def source_index():
    """producer name -> (module path, line, one-paragraph description)."""
    found = {}
    for name in sorted(os.listdir(os.path.join(SRC, "hengbot"))):
        if not name.endswith(".py"):
            continue
        path = os.path.join(SRC, "hengbot", name)
        text = open(path, encoding="utf-8").read()
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        lines = text.splitlines()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name in found:
                continue
            doc = ast.get_docstring(node) or ""
            summary = doc.strip().split("\n\n")[0].replace("\n", " ").strip()
            if not summary:
                summary = leading_comment(lines, node.lineno)
            found[node.name] = (f"src/hengbot/{name}", node.lineno, summary)
    return found


def callsite_notes(producers):
    """producer -> the comment written above its ``_decide`` call site.

    Half the rungs have no docstring of their own; what explains their
    position is the comment ``_decide`` carries above the branch that calls
    them.  The first call site wins, matching the ladder's own order.
    """
    path = os.path.join(SRC, "hengbot", "policy.py")
    text = open(path, encoding="utf-8").read()
    lines = text.splitlines()
    tree = ast.parse(text)
    notes = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name != "_decide":
            continue
        for stmt in node.body:
            segment = "\n".join(lines[stmt.lineno - 1:stmt.end_lineno])
            note = leading_comment(lines, stmt.lineno)
            if not note:
                continue
            for producer in producers:
                if producer in notes or producer not in segment:
                    continue
                notes[producer] = note
    return notes


def ladder_groups():
    """rung producer -> the section heading comment it sits under."""
    path = os.path.join(SRC, "hengbot", "claim_ladder.py")
    text = open(path, encoding="utf-8").read()
    body = text.split("_RUNGS", 1)[-1]
    heading = ""
    groups = {}
    for line in body.splitlines():
        match = re.match(r"\s*#\s*--+\s*(.+?)\s*--+\s*$", line)
        if match:
            heading = match.group(1).strip()
            continue
        call = re.match(r'\s*_(rewrite|decide|town|fallback)\(\s*"([^"]+)"', line)
        if call:
            groups.setdefault(call.group(2), heading)
    return groups


def open_log(path):
    if path.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    return open(path, encoding="utf-8", errors="replace")


def parse_time(stamp):
    """A decision's ``time`` as an aware datetime, or None."""
    if not stamp:
        return None
    try:
        moment = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment


class Window:
    """One period the page can be read in: everything, or a recent span."""

    def __init__(self, key, label, hours, now):
        self.key = key
        self.label = label
        self.hours = hours
        self.since = None if hours is None else now - timedelta(hours=hours)
        self.hits = Counter()
        self.reasons = defaultdict(Counter)
        self.objectives = defaultdict(Counter)
        self.keys = defaultdict(Counter)
        self.files = set()
        self.rows = 0
        self.unrunged = 0
        self.first = None
        self.last = None

    def holds(self, moment):
        if self.since is None:
            return True
        return moment is not None and moment >= self.since

    def add(self, rung, row, stamp, path):
        self.rows += 1
        self.files.add(path)
        self.hits[rung] += 1
        self.reasons[rung][row.get("reason") or "(none)"] += 1
        self.objectives[rung][row.get("objective") or "(none)"] += 1
        key = row.get("key")
        if key is not None:
            self.keys[rung][str(key)] += 1
        if stamp:
            if self.first is None or stamp < self.first:
                self.first = stamp
            if self.last is None or stamp > self.last:
                self.last = stamp

    def meta(self):
        return {
            "key": self.key,
            "label": self.label,
            "hours": self.hours,
            "since": self.since.isoformat() if self.since else None,
            "files": len(self.files),
            "decisions": self.rows,
            "unrunged": self.unrunged,
            "first": self.first,
            "last": self.last,
        }


def collect_logs(patterns, windows):
    """Count decisions per rung, into every window that holds the row."""
    seen = set()
    for pattern in patterns:
        for path in sorted(glob.glob(os.path.join(ROOT, pattern))):
            real = os.path.realpath(path)
            if real in seen:
                continue
            seen.add(real)
            try:
                handle = open_log(path)
            except OSError:
                continue
            with handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except ValueError:
                        continue
                    stamp = row.get("time")
                    moment = parse_time(stamp)
                    live = [w for w in windows if w.holds(moment)]
                    if not live:
                        continue
                    claim = row.get("claim") or {}
                    rung = claim.get("rung")
                    if not rung:
                        for window in live:
                            window.unrunged += 1
                        continue
                    for window in live:
                        window.add(rung, row, stamp, real)
    return windows


def git(*args):
    try:
        out = subprocess.run(["git", "-C", ROOT, *args],
                             capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def git_sha():
    """The commit the source links point at -- one the remote can serve.

    A local HEAD that has not been pushed would give every link a 404, so
    fall back to the branch name: the lines may drift, the link survives.
    """
    head = git("rev-parse", "HEAD")
    if not head:
        return "main"
    pushed = git("merge-base", "--is-ancestor", head, "origin/main")
    return head if pushed is not None else "main"


def top(counter, limit=8):
    return [[name, count] for name, count in counter.most_common(limit)]


def build(patterns, spans):
    sources = source_index()
    groups = ladder_groups()
    notes = callsite_notes({r.producer for r in cl.CLAIM_LADDER})
    now = datetime.now(timezone.utc)
    windows = collect_logs(patterns, [Window(key, label, hours, now)
                                      for key, label, hours in spans])
    sha = git_sha()
    rungs = []
    for index, rung in enumerate(cl.CLAIM_LADDER):
        where = sources.get(rung.producer)
        rungs.append({
            "index": index,
            "name": rung.name,
            "producer": rung.producer,
            "family": rung.family,
            "section": rung.section,
            "rank": rung.rank,
            "reasons": list(rung.reasons),
            "ordinary": rung.ordinary,
            "town_rank": rung.shares_town_rank,
            "owns_transaction": rung.owns_transaction,
            "group": groups.get(rung.producer, ""),
            "family_ja": FAMILY_LABELS.get(rung.family, rung.family),
            "file": where[0] if where else None,
            "line": where[1] if where else None,
            "doc": (where[2] if where else "") or notes.get(rung.producer, ""),
            "doc_from": ("docstring" if where and where[2]
                         else ("call-site" if notes.get(rung.producer) else "")),
            "w": {w.key: {
                "hits": w.hits.get(rung.name, 0),
                "reasons": top(w.reasons[rung.name]),
                "objectives": top(w.objectives[rung.name], 6),
                "keys": top(w.keys[rung.name], 6),
            } for w in windows},
        })
    return {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commit": sha,
        "blob_base": BLOB_BASE + "/" + sha + "/",
        "sections": [{"name": s,
                      "label": SECTION_LABELS[s][0],
                      "note": SECTION_LABELS[s][1]}
                     for s in SECTION_ORDER
                     if any(r["section"] == s for r in rungs)],
        "families": [{"name": f, "label": FAMILY_LABELS.get(f, f),
                      "count": sum(1 for r in rungs if r["family"] == f),
                      "hits": {w.key: sum(r["w"][w.key]["hits"] for r in rungs
                                          if r["family"] == f)
                               for w in windows}}
                     for f in sorted({r["family"] for r in rungs})],
        "windows": [w.meta() for w in windows],
        "rungs": rungs,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log-glob", action="append", default=None,
                        help="decision-log glob, relative to bot-client "
                             "(repeatable; default: every bot-decisions log)")
    parser.add_argument("--out", default=os.path.join(ROOT, "docs", "data",
                                                      "ladder.json"))
    parser.add_argument("--window", action="append", default=None,
                        metavar="HOURS",
                        help="a recent period the page can switch to, in "
                             "hours (repeatable; default: 48)")
    args = parser.parse_args()
    spans = [("all", "全期間", None)]
    for hours in args.window or [str(h) for h in DEFAULT_WINDOWS]:
        hours = int(hours)
        label = ("直近%d時間" % hours if hours < 48 * 2
                 else "直近%d日" % round(hours / 24))
        spans.append(("h%d" % hours, label, hours))
    data = build(args.log_glob or list(DEFAULT_LOGS), spans)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=1, sort_keys=False)
        handle.write("\n")
    for window in data["windows"]:
        observed = sum(1 for r in data["rungs"] if r["w"][window["key"]]["hits"])
        print("%-10s %7d decisions / %3d logs / %2d rungs observed, %2d cold"
              % (window["label"], window["decisions"], window["files"],
                 observed, len(data["rungs"]) - observed))
    print("-> %s" % args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
