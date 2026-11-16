"""*Destruction* on a sleeping T1, and the approach to one out of reach (owner 2026-11-17).

Owner 2026-11-17 (verbatim): 「50F以降でT1を破壊で排除するルールに眠っているかどうかを記載した記憶は
ないのだが、現状を確認して」, then 「両方の条件を外して直して」.  The rules -- 11-04 「脅威が範囲内に
見える時に使用」, 11-09 B 「即死ではない場合は破壊による排除を優先」, 11-10 「感知だけで見えた遠くの T1
は積極的に *破壊* で消しにいく」, 11-14 「破壊または近寄って破壊を試みる」 -- never asked the monster
awake nor the player inside its sensing radius; the code did (threat_tiers ``_sensed_strong``:
``not monster.asleep`` and ``inside_sensing``; destruction_use ``_awake_in_view``).  Both are gone
for the use and its approach.  The 2026-11-08 leave (「感知で起きている倒しきれない敵が見えている時に
休むか」→「その敵の感知範囲内なら早急に離脱する」) keeps its own words: no stairs, scroll, Recall or
walk away for a sleeper or from outside the radius.

Recorded: the n1-c life-216 62F boards of tests/fixtures/route-veto-sealed-20261117.json.gz (see
tests/test_route_veto_sealed_1117_recorded.py), decided in order by one policy's ``choose_key``.
DECLARED RECONSTRUCTED: the absorbed *Destruction* list row (22 charges at 95%; the record cast
``mA3`` at 04:18:44).  DECLARED CONSTRUCTED: one recorded sleeper's race made a パワー・ワイアーム
(race 847, which the tiers read T1 on these boards), asleep where the board shows it: on the landing
board (3,29) the visible スリング・ハーフリング (index 101) at (12,28), 9 cells off; or the detected-only
monster (race 1398) at (3,46), 17 cells off.
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import destruction_use, me_capability, threat_tiers
from hengbot.model import SV_STAFF_DESTRUCTION, game_distance, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy

FIXTURE = Path(__file__).with_name("fixtures") / "route-veto-sealed-20261117.json.gz"
LANDING_TURN = 3897141
POWER_WYRM = 847
IN_VIEW_INDEX = 101      # the visible スリング・ハーフリング at (12,28) on the landing board
FAR_RACE = 1398          # the detected-only monster at (3,46) on the landing board


class SleepingT1DestructionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.landing = next(raw for raw in json.load(stream)["boards"]
                               if raw["turn"] == LANDING_TURN)
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def decide(self, swap):
        """The landing board with ``swap`` (field, monster) made a sleeping パワー・ワイアーム,
        decided by a fresh policy: (key, reason, policy, board, the wyrm)."""
        raw = copy.deepcopy(self.landing)
        for field in ("visible_monsters", "detected_monsters"):
            for monster in raw[field]:
                if swap(field, monster):
                    monster["race_id"] = POWER_WYRM
                    monster["asleep"] = True
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        board = parse_snapshot(raw, self.monrace)
        policy.prime(board)
        policy._skill_exp_cache = (0, 0, board.player.level, policy._town_visit_epoch)
        policy._me_device_lists = {"staff": (board.turn, ({
            "name": me_capability.names("staff", SV_STAFF_DESTRUCTION)[0], "current": 22,
            "max": 22, "fail": 5, "success": 95},))}
        board = policy.with_known_skill_exp(board)
        key = policy.choose_key(board)
        wyrm = next(m for m in (*board.visible_monsters, *board.detected_monsters)
                    if m.race_id == POWER_WYRM)
        return key, policy.last_reason, policy, board, wyrm

    def test_a_sleeping_t1_in_view_in_reach_is_destroyed(self):
        key, reason, policy, board, wyrm = self.decide(
            lambda field, m: field == "visible_monsters" and m["index"] == IN_VIEW_INDEX)
        self.assertTrue(wyrm.asleep)
        self.assertLessEqual(game_distance(board.player.position, wyrm.position),
                             destruction_use.GUARANTEED_RADIUS)
        self.assertEqual(threat_tiers.tiered(policy, board, [wyrm], contact=True).tier, threat_tiers.T1)
        self.assertEqual(key, "mA3")
        self.assertTrue(reason.startswith(destruction_use.REASON), reason)

    def test_a_sleeping_t1_far_off_is_gone_to(self):
        """Owner 2026-11-10 「感知だけで見えた遠くの T1 は積極的に *破壊* で消しにいく」, now for a
        sleeper and from outside its sensing radius: the approach owns the board (approach_owns:
        known only by detection, the means held, none in reach of a refused use).  The landing
        board knows no way toward it yet, so ``approach_key`` gives the rungs below the board (its
        documented None: they map and explore) and no leave is read."""
        key, reason, policy, board, wyrm = self.decide(
            lambda field, m: m["race_id"] == FAR_RACE)
        self.assertTrue(wyrm.asleep)
        self.assertEqual(wyrm.perception, "detected")
        self.assertGreater(game_distance(board.player.position, wyrm.position),
                           destruction_use.GUARANTEED_RADIUS)
        strong = threat_tiers._sensed_strong(policy, board)[1]
        self.assertIn(wyrm, strong)
        self.assertTrue(threat_tiers.approach_owns(policy, board, strong))
        self.assertEqual(threat_tiers._approach_targets(policy, board, strong), strong)
        self.assertFalse(reason.startswith(threat_tiers.SENSED_LEAVE_PREFIX), reason)
        self.assertEqual(reason, "explore")

    def test_no_leave_is_read_for_a_sleeper(self):
        """The 2026-11-08 leave keeps its words: the sleeping T1 is not left by a read."""
        _key, _reason, policy, board, _wyrm = self.decide(
            lambda field, m: field == "visible_monsters" and m["index"] == IN_VIEW_INDEX)
        self.assertEqual(threat_tiers._sensed_strong(policy, board, leave=True)[1], [])
        self.assertTrue(threat_tiers._sensed_strong(policy, board)[1])


if __name__ == "__main__":
    unittest.main()
