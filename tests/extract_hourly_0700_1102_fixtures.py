"""Freeze the 2026-11-02 06:10-06:49 viewing-bot stops (hourly-0700-1102).

Sources, copied under C:/hengband-backups/pdca/captures/hourly-0700-1102/:

  rollover    n1-a life-464 06:10:25 no-key-exhausted (bot-10ac9173a).
              Decision 10034 posted ``~9<ESC>`` at turn 3003443; the
              emitter's 256 MiB rollover truncated state.jsonl right after
              the Home list it wrote (the stop's state.jsonl begins at turn
              3003443 and the ring holds no home knowledge row after 3003423),
              so the await at 10037 posted nothing.  Frozen: the ring rows of
              turn 3003433 (the last board group before the rollover), the
              whole post-rollover state.jsonl, the Home list and skill rows the
              process consumed before (turns 3003423, 3002977), and decision
              10034/10037 facts.
  home-route  n1-c life-103 06:41:31 equipment-transaction:home-route-repeat-
              terminal (bot-2726a3bf5).  After the identification-catalog
              withdrawal (1880) the equipment deposit (1885, turn 1809910)
              found no Home route.  Frozen: that board, the last Home list
              (taken before the withdrawal), the last skill row, decision 1885
              facts and the policy-state ``_town_errand_plan``.
  esp-recall  n1-c life-103 06:49:23 stuck-prompt esp-threat:leave-recall
              (bot-2726a3bf5).  Decision 3738 read Word of Recall (``rh``) on
              depth 15; recall_player asked the depth question.  Frozen: the
              board (turn 1853588), decision facts and the <stuck-prompt> line.

Only this extraction tool reads the captures; the committed test reads the
frozen fixture alone.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

from tests.extract_recall_dungeon_prompt_fixture import ring_rows


ROOT = Path("C:/hengband-backups/pdca/captures/hourly-0700-1102")
ROLLOVER = ROOT / "n1-a-life-464-20261102-061025-no-key-exhausted"
HOME_ROUTE = ROOT / "n1-c-life-103-20261102-064131-equipment-transaction-home-route-repeat-terminal"
ESP_RECALL = ROOT / "n1-c-life-103-20261102-064923-stuck-prompt-esp-threat-leave-recall"
OUTPUT = Path(__file__).with_name("fixtures") / "hourly-0700-1102.json.gz"
DECISION_FACTS = ("decision_sequence", "turn", "reason", "key", "position")


def _jsonl_gz(path: Path) -> list[dict]:
    rows = []
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass  # a torn tail of the previous session
    return rows


def _ring(capture: Path) -> list[dict]:
    return ring_rows((capture / "incident-captures" / "snapshots"
                      / "snapshots-current.jsonl.gz").read_bytes())


def _decision(capture: Path, sequence: int, *extra: str) -> dict:
    row = next(row for row in _jsonl_gz(capture / "bot-decisions.jsonl.gz")
               if row.get("decision_sequence") == sequence
               and row.get("reason") != "loop-detected")
    return {key: row[key] for key in (*DECISION_FACTS, *extra)}


def _last_knowledge(rows: list[dict], category: str, before: int) -> dict:
    return [row for row in rows if row["type"] == "knowledge"
            and row["knowledge"]["category"] == category and row["turn"] <= before][-1]


def _sources(capture: Path, *names: str) -> dict:
    return {name: hashlib.sha256((capture / name).read_bytes()).hexdigest() for name in names}


def rollover_case() -> dict:
    ring = _ring(ROLLOVER)
    after = _jsonl_gz(ROLLOVER / "state.jsonl.gz")
    assert after[0]["turn"] == 3003443, after[0]["turn"]
    home = _last_knowledge(ring, "home", 3003443)
    assert home["turn"] == 3003423, home["turn"]
    assert not [row for row in ring if row["type"] == "knowledge"
                and row["knowledge"]["category"] == "home" and row["turn"] > 3003423]
    stdout = (ROLLOVER / "bot-stdout.log").read_text(encoding="utf-8").splitlines()
    return dict(
        sources=_sources(ROLLOVER, "state.jsonl.gz", "bot-decisions.jsonl.gz",
                         "incident-captures/snapshots/snapshots-current.jsonl.gz"),
        before=[row for row in ring if row["turn"] == 3003433],
        after=after,
        home=home,
        skill=_last_knowledge(ring, "skill_exp", 3003443),
        decisions=[_decision(ROLLOVER, 10034, "home_scan"),
                   _decision(ROLLOVER, 10037, "home_scan")],
        stdout_tail=stdout[-2:],
    )


def home_route_case() -> dict:
    ring = _ring(HOME_ROUTE)
    board = [row for row in ring if row["type"] == "player_turn" and row["turn"] == 1809910][-1]
    state = json.loads((HOME_ROUTE / "incident-captures" / "policy-state.json")
                       .read_text(encoding="utf-8"))
    decision = _decision(HOME_ROUTE, 1885, "equipment_optimization")
    optimization = decision.pop("equipment_optimization")
    decision["transaction_next"] = optimization["transaction_next"]
    decision["home_route_projection"] = optimization["home_route_projection"]
    return dict(
        sources=_sources(HOME_ROUTE, "bot-decisions.jsonl.gz", "incident-captures/policy-state.json",
                         "incident-captures/snapshots/snapshots-current.jsonl.gz"),
        board=board,
        home=_last_knowledge(ring, "home", 1809910),
        skill=_last_knowledge(ring, "skill_exp", 1809910),
        decision=decision,
        withdrawal=_decision(HOME_ROUTE, 1880),
        town_errand_plan=state["state"]["_town_errand_plan"],
    )


def esp_recall_case() -> dict:
    board = [row for row in _jsonl_gz(ESP_RECALL / "state.jsonl.gz")
             if row["type"] == "player_turn"][-1]
    assert board["turn"] == 1853588, board["turn"]
    stderr = (ESP_RECALL / "bot-stderr.log").read_text(encoding="utf-8").splitlines()
    return dict(
        sources=_sources(ESP_RECALL, "state.jsonl.gz", "bot-decisions.jsonl.gz", "bot-stderr.log"),
        board=board,
        decision=_decision(ESP_RECALL, 3738),
        stuck_prompt=next(line for line in reversed(stderr) if line.startswith("<stuck-prompt>")),
    )


def main() -> None:
    case = {"rollover": rollover_case(), "home-route": home_route_case(),
            "esp-recall": esp_recall_case()}
    OUTPUT.write_bytes(gzip.compress(
        json.dumps(case, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), mtime=0))
    print(OUTPUT, OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
