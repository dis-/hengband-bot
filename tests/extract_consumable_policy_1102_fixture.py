"""Freeze the boards of the consumable-table test (consumable-policy-1102).

Sources (copied read-only from the viewing bots, C:/hengband-backups/pdca/captures):

  dungeon  n1-c life-103 (Magic-Eater), state line 0 (turn 1807627) of
           hourly-0700-1102/n1-c-life-103-20261102-064131-equipment-
           transaction-home-route-repeat-terminal: Angband 8F, no visible
           monster, waiting for its Recall; slot b 赤外線視力の薬 (75/24) and
           slot i 魔法の地図の巻物 x2 (70/25), both 「捨てる」 in the table.
  home     n1-a life-464 (warrior), state lines 56 (the Home page), 57 (the
           ``~9`` Home list the bot requested at turn 2869814,
           ``equipment-transaction:catalogue-request-knowledge``) and 58 (the
           Home page after it) of hourly-0600-1102/n1-a-life-464-20261102-
           054907-town-blocked-departure-unsatisfiable: slot e 啓蒙の薬 (75/56),
           i テレポート・レベルの巻物 (70/10), k 解呪の巻物 (70/14), all
           「拾って自宅に片付ける」, and b ヒーローの薬 (75/32, 「拾って持ち歩く」);
           no cursed item worn.
  alchemist n1-a life-435, state line 0 (turn 523013) of
           recall-yeek-1030/n1-a/life-435/captures/20261030-185622-stuck-
           prompt-town-recall-to-yeek-cave: the Alchemist page whose ware p is
           財宝感知の巻物 (70/26, no 「購入する」); the recorded bot was mining
           (decision ``fundraising.mode`` "mine") and bought it (``pp5\\r\\r``
           shop:in-store-buy).

The fixture is a JSON-lines gzip, one {"id", "line"} record per board.  Only
this extraction tool reads the captures.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

CAPTURES = Path("C:/hengband-backups/pdca/captures")
SOURCES = {
    "dungeon": ("hourly-0700-1102/n1-c-life-103-20261102-064131-equipment-"
                "transaction-home-route-repeat-terminal/state.jsonl.gz", (0,)),
    "home": ("hourly-0600-1102/n1-a-life-464-20261102-054907-town-blocked-"
             "departure-unsatisfiable/state.jsonl.gz", (56, 57, 58)),
    "alchemist": ("recall-yeek-1030/n1-a/life-435/captures/20261030-185622-"
                  "stuck-prompt-town-recall-to-yeek-cave/state.jsonl.gz", (0,)),
}
OUTPUT = Path(__file__).with_name("fixtures") / "consumable-policy-20261102.jsonl.gz"


def main() -> None:
    records = []
    for name, (path, indexes) in SOURCES.items():
        with gzip.open(CAPTURES / path, "rt", encoding="utf-8") as stream:
            lines = stream.read().split("\n")
        records.extend({"id": f"{name}/{index}", "line": lines[index]}
                       for index in indexes)
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
