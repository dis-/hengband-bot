"""Extract the Lv7 zombie warrior town boundary that stopped before quest 1 (D20)."""
import gzip
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import load_monrace_knowledge, find_monrace_definitions
from hengbot.quest_knowledge import load_quest_knowledge, find_quest_definitions
from tests.extract_me_q1_torch import boundary as _boundary
import tests.extract_me_q1_torch as me


ROOT = Path(r"C:\hengband-backups\viewing-captures-1030\n1b-253-q1-block\incident-captures")


def main():
    # 08:12:45: the first of three stops; the shop census refused the
    # potion stock demanded by the warrior's (default) Q1 force gate.
    me.ROOT = ROOT
    capture, source, rows, raw, modes, decision = _boundary("20261030-081245-no-key-exhausted")
    races = load_monrace_knowledge(find_monrace_definitions(Path.cwd(), None))
    q1 = load_quest_knowledge(find_quest_definitions(Path.cwd()))[1]
    ids = {race for race, _ in q1.threat_roster}
    ids.update(row["race_id"] for field in ("visible_monsters", "detected_monsters")
               for row in raw.get(field, []))
    general = next(row for row in rows if row["type"] == "store" and row["store"]["store_type"] == 0)
    case = dict(
        snapshot=raw,
        sources={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in (source, capture / "policy-state.json")},
        recorded_readiness=decision["fixedquest_readiness"],
        recorded_key=decision["key"], recorded_reason=decision["reason"],
        # The Outpost general store page of the same capture (turn 75108).
        general_page=general["store"],
        knowledge=[row for row in rows if row["type"] == "knowledge"],
        monraces={key: asdict(races[key]) for key in ids},
        state={"modes_and_latches": {key: modes[key] for key in
               ("_town_supplier_stock", "_town_supplier_stock_observations")}},
    )
    target = Path(__file__).with_name("fixtures") / "warrior-q1-lower-20261030.json.gz"
    with gzip.open(target, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    print(target, raw["turn"], target.stat().st_size)


if __name__ == "__main__":
    main()
