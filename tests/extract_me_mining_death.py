"""Extract the n1-c Magic-Eater Yeek cave 1F death boards (D21).

Sources: the 2026-10-30 viewing captures of n1-c (zombie Magic-Eater, Lv8)
lives 8, 9 and 11 (stuck-prompt stops at their deaths) and life 16 (stop at
13:01).  Each case keeps recorded player-turn boards, the recorded decision
rows of those boards, the remembered terrain and the return/fundraising modes
of the policy checkpoint written at the stop, and the race facts of every
monster on the boards.
"""
import gzip
import hashlib
import json
import zlib
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge

ROOT = Path(r"C:\hengband-backups\viewing-captures-1030")
CASES = {
    "life-008": (ROOT / "n1c-lives-8-13" / "life-008" / "incident-captures"
                 / "20261030-080419-stuck-prompt", (805338, 805349)),
    "life-009": (ROOT / "n1c-lives-8-13" / "life-009" / "incident-captures"
                 / "20261030-081043-stuck-prompt", (219660, 219724)),
    "life-011": (ROOT / "n1c-lives-8-13" / "life-011" / "incident-captures"
                 / "20261030-083317-stuck-prompt", (186766, 187358)),
    "life-016": (ROOT / "n1c-life016" / "x" / "incident-captures"
                 / "20261030-130103-stuck-prompt", (94171, 94285)),
}
# life-016's own decision tail ends before 12:59; the bounded 4000-row log of
# the same process (l16.jsonl, copied with the capture) holds those rows.
DECISION_LOGS = {"life-016": ROOT / "n1c-life016" / "x" / "l16.jsonl"}
MODE_FIELDS = ("_fundraising_mode", "_returning_to_town", "_emergency_return_active",
               "_crossarea_fundraising_enforced", "_last_return_trigger",
               "_fundraising_runs_started")
DECISION_FIELDS = ("decision_sequence", "turn", "reason", "key", "position", "player",
                   "messages", "threat_prediction")


def snapshot_rows(path):
    # The live generation is copied as a tail: start at its first gzip member.
    data = path.read_bytes()
    position = data.find(b"\x1f\x8b\x08")
    text = b""
    while position < len(data):
        stream = zlib.decompressobj(31)
        text += stream.decompress(data[position:])
        if not stream.unused_data:
            break
        position = len(data) - len(stream.unused_data)
    return [json.loads(line) for line in text.split(b"\n") if line.strip()]


def decision_rows(path):
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass  # The bounded tail starts in the middle of a JSON record.
    return rows


def main():
    races = load_monrace_knowledge(find_monrace_definitions(Path.cwd(), None))
    cases, sources, ids = {}, {}, set()
    for name, (capture, turns) in CASES.items():
        snapshots = capture / "snapshots" / "snapshots-current.jsonl.gz"
        boards = {row["turn"]: row for row in snapshot_rows(snapshots)
                  if row.get("type") == "player_turn"}
        log = DECISION_LOGS.get(name, capture / "decision-tail.jsonl")
        decisions = {row["turn"]: row for row in decision_rows(log) if "turn" in row}
        checkpoint = json.loads((capture / "policy-state.json").read_text(encoding="utf-8"))
        sources[name] = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                         for path in (snapshots, log, capture / "policy-state.json")}
        for turn in turns:
            ids.update(row["race_id"] for row in boards[turn]["visible_monsters"])
        cases[name] = {
            "boards": {str(turn): boards[turn] for turn in turns},
            "decisions": {str(turn): {field: decisions[turn].get(field)
                                      for field in DECISION_FIELDS} for turn in turns},
            "terrain": checkpoint["terrain"],
            "checkpoint_created_at": checkpoint["created_at"],
            "modes": {field: checkpoint["modes_and_latches"][field] for field in MODE_FIELDS},
        }
    case = {"sources": sources, "cases": cases,
            "monraces": {key: asdict(races[key]) for key in sorted(ids)}}
    target = Path(__file__).with_name("fixtures") / "me-mining-death-20261030.json.gz"
    with gzip.open(target, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    print(target, target.stat().st_size)


if __name__ == "__main__":
    main()
