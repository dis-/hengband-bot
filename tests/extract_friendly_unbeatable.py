"""Extract the town boards where the hunt attacked an unbeatable friendly (D32).

Sources (incident captures of 2026-10-30, copied under
C:/hengband-backups/pdca/captures): n1-b life 268 (warrior Lv7, Farmer
Maggot, death), n1-c life 34 (Magic-Eater Lv8, Farmer Maggot, death) and
n1-c life 10 (Magic-Eater Lv8, the pigeon Poppo, HP 14 and the D22 stop).
Each case keeps the recorded player-turn boards, the decision rows of those
boards, the skill/home knowledge rows last received before the first board,
the supplier shelves and fundraising facts of the policy checkpoint written
at the stop, and the race facts of every monster on the boards.
"""
import gzip
import hashlib
import json
import zlib
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge

ROOT = Path(r"C:\hengband-backups\pdca\captures")
CASES = {
    "n1-b/life-268": (ROOT / "unfixed-24h-1031" / "n1-b" / "life-268" / "incident-captures"
                      / "20261030-205050-stuck-prompt", (75224, 75256)),
    "n1-c/life-034": (ROOT / "n1c-1030-2100" / "life-034" / "incident-captures"
                      / "20261030-204206-stuck-prompt", (151878, 151886, 152427, 152545)),
    "n1-c/life-010": (ROOT / "unfixed-24h-1031" / "n1-c" / "life-010" / "incident-captures"
                      / "20261030-082816-stuck-prompt", (478794,)),
}
DECISION_FIELDS = ("decision_sequence", "turn", "reason", "key", "player")
MODE_FIELDS = ("_fundraising_mode", "_supply_stockout_gold_target",
               "_town_supplier_stock", "_town_supplier_stock_observations")


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
    cases, sources, ids = {}, {}, {1320}  # 1320: the constructed beatable friendly
    for name, (capture, turns) in CASES.items():
        snapshots = capture / "snapshots" / "snapshots-current.jsonl.gz"
        log = capture / "decision-tail.jsonl"
        checkpoint_path = capture / "policy-state.json"
        sources[name] = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                         for path in (snapshots, log, checkpoint_path)}
        boards, knowledge = {}, {}
        for row in snapshot_rows(snapshots):
            if row.get("turn", 0) <= turns[0] and row.get("type") == "knowledge":
                knowledge[row["knowledge"]["category"]] = row
            if row.get("type") == "player_turn" and row["turn"] in turns:
                boards.setdefault(row["turn"], row)
        decisions = {}
        for row in decision_rows(log):
            if row.get("turn") in turns:
                decisions.setdefault(row["turn"], row)
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        modes = checkpoint["modes_and_latches"]
        for turn in turns:
            ids.update(row["race_id"] for row in boards[turn]["visible_monsters"])
        cases[name] = {
            "boards": {str(turn): boards[turn] for turn in turns},
            "decisions": {str(turn): {field: decisions[turn].get(field)
                                      for field in DECISION_FIELDS} for turn in turns},
            "knowledge": [knowledge[key] for key in ("skill_exp", "home") if key in knowledge],
            "modes": {field: modes.get(field, checkpoint["state"].get(field))
                      for field in MODE_FIELDS},
        }
    case = {"sources": sources, "cases": cases,
            "monraces": {key: asdict(races[key]) for key in sorted(ids)}}
    target = Path(__file__).with_name("fixtures") / "friendly-unbeatable-20261030.json.gz"
    with gzip.open(target, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    print(target, target.stat().st_size)


if __name__ == "__main__":
    main()
