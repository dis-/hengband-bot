"""n1-b life-322 (2026-11-06 02:37): the Q14 reward Light Crossbow was sold.

The reward, an unidentified ライト・クロスボウ (x3), was picked up at 02:37:07
and sold to the Weapon Smith six seconds later for $57 (decisions 13949
shop:in-store-inscribe {o@0, 13950 shop:in-store-sell d0y).  The optimizer
cannot judge an unidentified launcher, so spare_gear released it as spare,
and the town organization sold every Home candidate that had a buyer: the
owner's ranking (item_fate: the top 10 of a slot are kept, an unranked piece
is kept) was never asked.  Identified, it was (1.20turn) (+1,+2): 12.5 per
turn with plain bolts against the worn Sling's 7.5, and the owner's launcher
rule (2026-10-02) puts a Light Crossbow above an ordinary Sling.  Wearing it
needs bolts the optimizer can see: the Smith page this town already saw, a
look at the Smith, and a Smith stop reopened when the new launcher is worn
with none (launcher_upgrade).

Recorded: the 02:37:31 arrival checkpoint of the same life (the sale visit's
own checkpoint was pruned), its calibration, and the recorded boards of the
sale and of the same stay after identification
(tests/extract_launcher_sale_1106_fixture.py).  Changes to boards and
policy state are marked DECLARED.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.model import (
    STORE_HOME, STORE_MAGIC, STORE_TEMPLE, STORE_WEAPON, TVAL_BOW, TVAL_DIGGING, parse_snapshot,
)
from hengbot.policy import staged_prompt_chain_matches
from hengbot.town_arrival_checkpoint import POLICY_FILE
from replay_town_arrival import adopt_calibration, restore
from tests import test_input_executor as executor_pins


FIXTURE = Path(__file__).with_name("fixtures") / "launcher-sale-1106"
LETTERS = "abcdefghijklmnopqrstuvw"
WIELD_PROMPT = "どれを装備しますか? "
# The game's own description of the reward when the sale identified it.
IDENTIFIED = {"name": "ライト・クロスボウ (x3) (1.20turn) (+1,+2)", "to_h": 1, "to_d": 2}
# The next arrival's gold (02:52), above the fundraising start.
NEXT_STAY_GOLD = 13631


def relettered(board: dict) -> dict:
    for letter, item in zip(LETTERS, board["inventory"]):
        item["slot"] = letter
    return board


class LauncherSale1106RecordedTest(executor_pins.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        cls.boards = json.loads(lzma.decompress((FIXTURE / "boards.json.xz").read_bytes()))

    def policy(self, fundraising):
        raw = TemporaryDirectory()
        self.addCleanup(raw.cleanup)
        visit = Path(raw.name) / "town-arrival"
        visit.mkdir()
        (visit / POLICY_FILE).write_bytes(lzma.decompress((FIXTURE / "policy.pkl.xz").read_bytes()))
        scratch = Path(raw.name) / "scratch"
        scratch.mkdir()
        policy = restore(visit, scratch)
        adopt_calibration(policy, FIXTURE / "calibration.json", scratch)
        # DECLARED CONSTRUCTED: the arrival had requested the ~f skill list;
        # the Magic-Eater's two-weapon and shield skills are unused (0).
        policy.consume_skill_knowledge({"knowledge": {"skills": [{"id": 1, "exp": 0}, {"id": 3, "exp": 0}]},
                                        "player": {"level": 14}})
        # DECLARED RECONSTRUCTED: the fundraising mode of the stay (decision
        # 13949 fundraising.mode "prepare"; None for the next, richer stay).
        policy._fundraising_mode = fundraising
        return policy

    def board(self, name, turn=None, **changes):
        board = copy.deepcopy(self.boards[name])
        if turn is not None:
            board["turn"] = turn
        board["player"].update(changes)
        return board

    @staticmethod
    def decide(policy, board):
        snapshot = parse_snapshot(board, policy._monrace_knowledge)
        policy.observe_store_screen(bool(board.get("store")))
        key = policy.choose_key(snapshot)
        if key:
            policy.confirm_key_posted(key)
            chain = policy.peek_staged_prompt_chain()
            if chain is not None and staged_prompt_chain_matches(chain, key):
                policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})
        return snapshot, key, policy.last_reason

    def crossbow(self):
        """DECLARED CONSTRUCTED: the reward as identified (the sold row's text)."""
        sling = next(item for item in self.boards["smith-page"]["equipment"] if item["tval"] == TVAL_BOW)
        crossbow = copy.deepcopy(sling)
        crossbow.update(IDENTIFIED, sval=23, weight=110, slot="")
        return crossbow

    def next_stay(self, turn):
        """The identified stay with the next arrival's gold, the shovel shelved.

        DECLARED CONSTRUCTED: the crossbow kept (identified) before the shots;
        the shovel is the Home deposit an equipment plan takes first.
        """
        board = self.board("after-identify", turn, gold=NEXT_STAY_GOLD)
        pack = [item for item in board["inventory"] if item["tval"] != TVAL_DIGGING]
        shots = next(index for index, item in enumerate(pack) if item["tval"] == 16)
        pack.insert(shots, self.crossbow())
        board["inventory"] = pack
        return relettered(board)

    def test_unidentified_reward_launcher_is_not_sold(self):
        policy = self.policy("prepare")
        outside = self.board("outside-smith")
        self.decide(policy, outside)
        # DECLARED RECONSTRUCTED: the stops this stay had finished (Home 13923,
        # Magic Shop 13933); the Temple one keeps the checkpoint's later
        # surplus Heroism potion, no candidate at 13949, off the first slot.
        for store_type in (STORE_HOME, STORE_MAGIC, STORE_TEMPLE):
            policy._set_town_store_attempted(store_type, outside["turn"], "recorded-plan")
        snapshot, _key, _reason = self.decide(policy, self.board("outside-smith", outside["turn"] + 1))
        crossbow = next(item for item in snapshot.inventory if item.tval == TVAL_BOW)
        self.assertFalse(crossbow.known)
        self.assertIsNone(policy._find_town_organization_surplus(snapshot))
        _snapshot, key, reason = self.decide(policy, self.board("smith-page"))
        self.assertEqual((key, reason), ("\x1b", "shop:observe-and-leave"))


if __name__ == "__main__":
    unittest.main()
