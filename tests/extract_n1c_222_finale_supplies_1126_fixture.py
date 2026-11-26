"""Extract tests/fixtures/n1c-222-finale-supplies-1126.json.gz for test_finale_supplies_1126_recorded.

Source: n1-c life-222's incident capture ``incident-captures/20261126-090930-loop-detected/``
(Zombie Magic-Eater Lv50, build bot-5175c3635, the town visit of 2026-11-26 09:07:55):

* ``census``: the Home's ``~9`` list delivered to decision 2939 (journal row 118, its first
  input line), the last census before the supplies step stopped: 46 Restore Mana at Home;
* ``board``: decision 2940's board (journal row 119, its decision line), where the step stopped
  as ``supplies:not-at-home:75-40`` with the pack's Healing, *Healing* and Resistance taken;
* ``deferred``: ``_deferred_home_items`` of the capture's ``policy-state.json`` (the *Healing*
  and the Restore Mana, deferred from decision 2936/2937 on, ``deferred_home_item_signatures``);
* ``restore_mana_carry``: the carry the board's readiness row required (``angband_finale``'s
  report, ``carried.restore_mana.required``).

    python tests/extract_n1c_222_finale_supplies_1126_fixture.py <capture>
"""
import gzip
import json
import sys
from pathlib import Path

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-222-finale-supplies-1126.json.gz"
CENSUS_ROW, BOARD_ROW, STOP_SEQUENCE = 118, 119, 2940


def main() -> None:
    capture = Path(sys.argv[1])
    with gzip.open(capture / "town-arrival" / "journal.jsonl.gz", "rt", encoding="utf-8") as stream:
        journal = [json.loads(line) for line in stream if line.strip()]
    census = json.loads(journal[CENSUS_ROW]["inputs"][0])
    board = json.loads(journal[BOARD_ROW]["line"])
    assert census["type"] == "knowledge" and journal[BOARD_ROW]["decision_sequence"] == STOP_SEQUENCE
    state = json.loads((capture / "policy-state.json").read_text(encoding="utf-8"))["state"]
    with open(capture / "decision-tail.jsonl", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get("decision_sequence") == STOP_SEQUENCE:
                report = row["angband_finale"]["finale"]["report"]
    record = {"census": census, "board": board, "deferred": state["_deferred_home_items"],
              "restore_mana_carry": report["carried"]["restore_mana"]["required"],
              "stopped": "supplies:not-at-home:75-40"}
    FIXTURE.write_bytes(gzip.compress(json.dumps(record, ensure_ascii=False).encode("utf-8"), mtime=0))


if __name__ == "__main__":
    main()
