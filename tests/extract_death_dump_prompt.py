"""Extract the death-chain "Dump the screen?" stops of 2026-10-30 (D32).

Sources: the viewing captures copied to
C:/hengband-backups/pdca/captures/unfixed-24h-1031.  Every case is a
character that died (HP <= 0 on the recorded state) and stopped as a
``stuck-prompt`` whose stderr line reads ``ctx=confirm
ctx_prompt="画面を保存しますか？[y/n]" reason=unowned confirm``.  Each case keeps
the recorded screen at the stop (control-at-stop.json.gz), the last recorded
player-turn board before it (state.jsonl.gz), the last recorded decision row
(bot-decisions.jsonl.gz), the stderr stop line, and the race facts of the
monsters on the board.
"""
import gzip
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge

ROOT = Path(r"C:\hengband-backups\pdca\captures\unfixed-24h-1031")
CASES = {
    "n1-c/life-008": "20261030-080422-stuck-prompt-melee",
    "n1-c/life-009": "20261030-081045-stuck-prompt-emergency-cornered-attack",
    "n1-c/life-011": "20261030-083320-stuck-prompt-emergency-cornered-attack",
    "n1-c/life-016": "20261030-130108-stuck-prompt-emergency-cornered-attack",
    "n1-a/life-424": "20261030-080257-stuck-prompt-explore",
    "n1-a/life-433": "20261030-165748-stuck-prompt-ranged-fire-target",
    "n1-b/life-268": "20261030-205054-stuck-prompt-emergency-seek-upstairs",
}
DECISION_FIELDS = ("decision_sequence", "turn", "reason", "key")


def rows(path):
    out = []
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass  # A bounded tail may start inside a record.
    return out


def main():
    races = load_monrace_knowledge(find_monrace_definitions(Path.cwd(), None))
    cases, sources, ids = {}, {}, set()
    for name, stamp in CASES.items():
        capture = ROOT / name / "captures" / stamp
        files = [capture / leaf for leaf in (
            "control-at-stop.json.gz", "state.jsonl.gz", "bot-decisions.jsonl.gz",
            "bot-stderr.log")]
        sources[name] = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                         for path in files}
        with gzip.open(files[0], "rt", encoding="utf-8") as stream:
            stop = json.load(stream)
        board = [row for row in rows(files[1]) if row.get("type") == "player_turn"][-1]
        decision = rows(files[2])[-1]
        stop_line = next(line for line in reversed(
            files[3].read_text(encoding="utf-8").splitlines())
            if line.startswith("<stuck-prompt>"))
        ids.update(row["race_id"] for row in board["visible_monsters"])
        cases[name] = {
            "screen": stop["screen"],
            "dead_hp": stop["state"]["player"]["hp"],
            "board": board,
            "decision": {field: decision.get(field) for field in DECISION_FIELDS},
            "stop_line": stop_line,
        }
    case = {"sources": sources, "cases": cases,
            "monraces": {key: asdict(races[key]) for key in sorted(ids)}}
    target = Path(__file__).with_name("fixtures") / "death-dump-prompt-20261030.json.gz"
    with gzip.open(target, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    print(target, target.stat().st_size)


if __name__ == "__main__":
    main()
