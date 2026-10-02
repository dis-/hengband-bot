"""Pins: heal or teleport first by the next turn's predicted damage.

USER DECISION 2026-10-03 06:0x.  Question: below the low-HP threshold
(max(max HP x 0.5, max HP - 300)) with enemies about, which first -- the
healing potion or the teleport (death 2026-10-03 05:33: HP 182, 29 hostiles,
a teleport carried, a heal drunk, blinded on the next move).  Answer
(verbatim): 「次に受けるダメージ予測で判断する。基本的には回復を優先するが、
回復量を上回るならテレポートを優先する。回復しても状況が悪化するだけだから
である。」

Clarification (user, 2026-10-03 08:5x, option 「1ターン分の95%値
(Recommended)」): 「見える敵の1ターン分の運用値（95%）と、直近1手の実被害の
大きい方を使う。期待値より慎重で、運の悪い一撃も見込む。テレポートが先になる
場面が少し増える。」  So the next turn is the operational (p95) projection of
the visible and detected hostiles over one player turn
(threat_prediction(turns=1)), at least the observed one-move loss -- the death
fix's fair-play correction for an unseen caster.
The heal amount is the potion's expected heal capped by the missing HP
(quaff-effects.cpp:124-133: Cure Serious 4d8, Healing 300, *Healing* 1200).

Recorded pin: the death capture (fixture of test_lethal_unseen_caster_recorded)
board 06036472, HP 182 with 29 visible hostiles and the unseen caster's line:
the observed loss 295 -> 182 = 113 and the one-turn p95 projection are both
below the Healing potion's 300, so the heal goes first -- the live key.
Warm-up: 06036445 (recorded) and 06036459 with its unseen caster's line
removed (DECLARED CONSTRUCTED warm-up: with the line the board itself now
heals first, unlike live, and every later board would be counterfactual;
without it the board decides as live).
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation
import json
import unittest

import test_lethal_unseen_caster_recorded as lethal
from test_lethal_unseen_caster_recorded import B_ONLY, C_BOARD, C_WARMUP

HEALING = 37
CURE_SERIOUS = 35


class DeathBoardHealFirstRecordedTest(lethal._Replay):
    def _warm(self):
        _board, key, reason = self._decide(C_WARMUP)
        self.assertEqual((key, reason), self._live(C_WARMUP))
        _board, key, reason = self._decide(C_BOARD, self._without_unseen_cast(C_BOARD))
        self.assertEqual((key, reason), self._live(C_BOARD))

    def test_recorded_death_board_heals_first(self):
        self._warm()
        board, key, reason = self._decide(B_ONLY)
        self.assertEqual(board.player.hp, 182)
        self.assertGreater(len(board.visible_monsters), 20)
        self.assertLess(board.player.hp, self.policy._low_hp_walk_threshold(board.player.max_hp))
        self.assertTrue([item for item in board.inventory if item.is_teleport_scroll])
        # The lethal ladder is engaged (death fix) ...
        self.assertTrue(self.policy._emergency_escape_pending)
        # ... and the next turn -- the one-turn p95 projection of the
        # visible and detected hostiles, at least the observed 113 -- is
        # below the heal of 300.
        hostiles = self.policy._strategic_hostiles(board)
        self.assertEqual(self.policy._attributable_observed_loss(board), 113)
        next_turn = self.policy._low_hp_next_turn_damage(board, hostiles)
        self.assertGreaterEqual(next_turn, 113)
        self.assertLessEqual(next_turn, 300)
        self.assertEqual((key, reason), self._live(B_ONLY))
        self.assertEqual((key, reason), ("qc", "item:heal"))

    def test_teleport_first_when_the_next_turn_outdamages_the_potion(self):
        # DECLARED CONSTRUCTED: board 06036472 with the Healing stack (slot c)
        # turned into Cure Serious Wounds (4d8, 18 expected); every other
        # field is recorded.  The observed 113 exceeds 18: teleport first.
        # (Conformance pin: the pre-decision lethal ladder also read the
        # teleport first, so it does not distinguish a revert.)
        self._warm()
        data = json.loads(self.boards[B_ONLY])
        stacks = [entry for entry in data["inventory"] if entry.get("tval") == 75 and entry.get("sval") == HEALING]
        self.assertEqual(len(stacks), 1)
        stacks[0]["sval"] = CURE_SERIOUS
        board, key, reason = self._decide(B_ONLY, json.dumps(data, ensure_ascii=False))
        self.assertIsNone(self.policy._find_heal_potion(board, expected_damage=113))
        self.assertTeleportRead(board, key, reason)


if __name__ == "__main__":
    unittest.main()
