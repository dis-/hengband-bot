"""Freeze the 2026-11-01 n1-c stuck-prompt:me-powerful:identify stops (#47, D53).

Source: the viewing zombie Magic-Eater n1-c (build bot-577cd246b), copied to
C:/hengband-backups/pdca/captures/fix-me-powerful-stuck-1101/ (the diagnosis
LUNA-DIAG-fix-me-powerful-stuck-1101.txt):

  life-076 captures/20261101-030343-stuck-prompt-me-powerful-identify
           incident-captures/20261101-030340-stuck-prompt
  life-075 captures/20261101-020942-stuck-prompt-me-powerful-identify
           incident-captures/20261101-020938-stuck-prompt

Each case keeps: the stop board (the last player_turn row of the stop
capture's state log), the last skill-proficiency and Home knowledge rows of
the life's snapshot rings, the capture's ``_me_staff_sequence`` record, the
recorded decision (the last row of the stop process's decision log), the last
posted character, and the game's reply to that ``U`` (control-at-stop.json:
the racial power prompt with its published input_context).

Only this extraction tool reads the captures; the committed test reads the
frozen fixture alone.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge


ROOT = Path("C:/hengband-backups/pdca/captures/fix-me-powerful-stuck-1101")
CASES = (
    ("life-076", "20261101-030343-stuck-prompt-me-powerful-identify", "20261101-030340-stuck-prompt"),
    ("life-075", "20261101-020942-stuck-prompt-me-powerful-identify", "20261101-020938-stuck-prompt"),
)
OUTPUT = Path(__file__).with_name("fixtures") / "me-powerful-stuck-20261101.json.gz"
DECISION_FIELDS = ("decision_sequence", "turn", "reason", "key")
SCREEN_FIELDS = ("width", "height", "cursor", "lines", "input_context")


def gz_rows(path: Path) -> list[dict]:
    found = []
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as stream:
        try:
            for line in stream:
                try:
                    found.append(json.loads(line))
                except json.JSONDecodeError:
                    pass  # A ring generation may end in a partial line.
        except EOFError:
            pass  # The live ring generation is still open.
    return found


def last_knowledge(rings: list[Path], category: str) -> dict:
    found = None
    for ring in rings:
        for row in gz_rows(ring):
            if (row.get("knowledge") or {}).get("category") == category:
                found = row
    assert found is not None, category
    return found


def case(life: str, stop: str, incident: str, races) -> dict:
    capture = ROOT / life / "captures" / stop
    snapshots = ROOT / life / "incident-captures" / incident / "snapshots"
    rings = [*sorted(snapshots.glob("snapshots-2*.jsonl.gz")), snapshots / "snapshots-current.jsonl.gz"]
    states = gz_rows(capture / "state.jsonl.gz")
    board = [row for row in states if row["type"] == "player_turn"][-1]
    assert states[-1]["type"] == "power_list" and states[-1]["power_list"]["kind"] == "racial"
    decision = gz_rows(capture / "bot-decisions.jsonl.gz")[-1]
    assert decision["turn"] == board["turn"] and decision["reason"] == "me-powerful:identify"
    posted = gz_rows(capture / "bot-posted-characters.jsonl.gz")[-1]
    with gzip.open(capture / "control-at-stop.json.gz", "rt", encoding="utf-8") as stream:
        screen = json.load(stream)["screen"]
    policy_state = ROOT / life / "incident-captures" / incident / "policy-state.json"
    record = json.loads(policy_state.read_text(encoding="utf-8"))["state"]["_me_staff_sequence"]
    race_ids = {row["race_id"] for field in ("visible_monsters", "detected_monsters")
                for row in board.get(field, [])}
    return dict(
        id=f"{life}/{stop}",
        sources={str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in (capture / "state.jsonl.gz", capture / "bot-decisions.jsonl.gz",
                              capture / "control-at-stop.json.gz", policy_state)},
        board=board,
        skill=last_knowledge(rings, "skill_exp"),
        home=last_knowledge(rings, "home"),
        sequence={key: record[key] for key in ("absorbed", "stage", "powers_read")},
        decision={key: decision[key] for key in DECISION_FIELDS},
        posted=posted["character"],
        screen={key: screen[key] for key in SCREEN_FIELDS},
        monraces={str(race): asdict(races[race]) for race in sorted(race_ids) if race in races},
    )


def main():
    races = load_monrace_knowledge(find_monrace_definitions(Path.cwd(), None))
    cases = [case(*row, races) for row in CASES]
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(cases, stream, ensure_ascii=False, separators=(",", ":"), default=sorted)
    print(OUTPUT, OUTPUT.stat().st_size)
    for row in cases:
        print(row["id"], row["decision"], row["posted"], row["skill"]["turn"], row["home"]["turn"])


if __name__ == "__main__":
    main()
