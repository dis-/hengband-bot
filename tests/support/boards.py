"""Board builders shared by several test modules.

Moved verbatim out of the test modules that hosted them (maintainability
review 1109, 段3); those modules re-export them under their old names.

- Goldburn CONSTRUCTED seams (was tests/test_goldburn_shopping_constructed.py,
  see its module note for what is retained and what is constructed):
  ``goldburn_decision``, ``goldburn_board`` and ``goldburn_shopping_policy``.
- The recorded n1-a town board row 1 (was ``_board`` in both
  tests/test_town_terminal_commit_pins.py and
  tests/test_town_terminal_need_evidence.py): ``n1a_townalt_board``.

The Quest 25 『幽霊屋敷』 board and its policy helpers live in
tests/support/q25_house.py.
"""

import tests  # noqa: F401 -- isolate live runtime files
import gzip
import hashlib
import json
from pathlib import Path

from policy_fixtures import grid, player, item
from hengbot.model import Position, Snapshot, TVAL_DIGGING, SV_DIGGING_SHOVEL, parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import CrossTownShoppingExpedition

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

# ---------------------------------------------------------------------------
# Goldburn CONSTRUCTED seams (was tests/test_goldburn_shopping_constructed.py)
# ---------------------------------------------------------------------------

GOLDBURN_FIXTURE = FIXTURES / "goldburn-20261003.decisions.json"
GOLDBURN_SHA256 = "6f3f9fe6b9d9e6c5e9323795e03a96cd545af59c6516582925f4a5faba439c37"


def goldburn_decision(index):
    assert hashlib.sha256(GOLDBURN_FIXTURE.read_bytes().replace(b"\r\n", b"\n")).hexdigest() == GOLDBURN_SHA256
    return json.loads(GOLDBURN_FIXTURE.read_text(encoding="utf-8"))["rows"][index]["decision"]


def goldburn_board(index=0):
    row = goldburn_decision(index)
    y, x = row["position"]["y"], row["position"]["x"]
    return Snapshot(
        player(y, x, gold=row["player"]["gold"], level=row["player"]["level"],
               hp=row["player"]["hp"], max_hp=row["player"]["max_hp"],
               mp=row["player"]["mp"], max_mp=row["player"]["max_mp"],
               food=9000, class_id=0),
        {Position(yy, xx): grid(yy, xx, building_type=4 if (yy, xx) == (28, 56) else -1)
         for yy in range(y - 2, y + 3) for xx in range(x - 2, x + 3)},
        [], floor_key=(0, 0, 0), town_flag=True, town_id=1 if index == 0 else 0,
        inventory=[] if index == 0 else [item("a", TVAL_DIGGING, SV_DIGGING_SHOVEL, is_equipment=True)],
        visited_town_ids=(0, 1), turn=row["turn"],
    )


def goldburn_shopping_policy():
    policy = HengbotPolicy()
    row = goldburn_decision(0)
    policy._cross_town_shopping = CrossTownShoppingExpedition(**{
        **row["cross_town_shopping"],
        "blocking_categories": tuple(row["cross_town_shopping"]["blocking_categories"]),
        "candidate_order": tuple(row["cross_town_shopping"]["candidate_order"]),
    })
    policy._identification_need = "full"
    return policy


# ---------------------------------------------------------------------------
# Recorded n1-a town board (was _board in tests/test_town_terminal_*.py)
# ---------------------------------------------------------------------------

N1A_TOWNALT_FIXTURE = FIXTURES / "n1a-townalt-20261023.jsonl.gz"


def n1a_townalt_board():
    with gzip.open(N1A_TOWNALT_FIXTURE, "rt", encoding="utf-8") as stream:
        return [parse_snapshot(json.loads(line), {}) for line in stream][1]
