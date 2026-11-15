"""The monsters a *Destruction* deleted leave every memory (owner 2026-11-15, review Q6).

Owner 「全部から消す・標的は残す」: the flash (destruction_use ``observe``) forgets through one registry
(monster_memory ``DESTRUCTION_FORGETS``) the hostiles known on the board of the use within the radius it
always destroys and not shown after it, but the quest's target and a QUESTOR (``_survives``).  Before,
only the three KINDS (by position) and five floor-visit memories were forgotten.

Recorded: n1-b life-355's Angband 80F locust board (tests/test_escape_count_1111_recorded, its
``locusts_destroyed`` flow through the public ``choose_key``: the policy's own *Destruction* and its
flash board without the locusts).  DECLARED CONSTRUCTED: before the use, the memories hold entries of
the locusts (a retreat's threat, a breath threat) and of a monster far off; the locust the quest would target is spared where named.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest
from unittest import mock

from hengbot import destruction_use, oneshot_breath, retreat_veto_life
from hengbot.model import parse_snapshot
import tests.test_escape_count_1111_recorded as escape

LOCUST = escape.LOCUST


class _Flow:
    def __init__(self, case, *, spare_race=None):
        self.case = case
        self.spare_race = spare_race

    def run(self):
        case = self.case
        with escape.in_line_of_fire():
            policy, _answers = case.replay(escape.LIFE, escape.LATCH_BOARD,
                                           without=(escape.DESTRUCTION_NAME,))
        raw = case.board(escape.LIFE, escape.LOCUST_BOARD)
        raw["turn"] = escape.LATCH_BOARD + 4
        raw["player"]["hp"] = raw["player"]["max_hp"] = 2000
        case.listed(policy, raw)
        locusts = [m for m in raw["visible_monsters"] if m["race_id"] == LOCUST]
        self.locust_keys = {(m["index"], m["race_id"]) for m in locusts}
        self.far_key = (999, 1)  # not on the board: no flash deletes it
        keys = self.locust_keys | {self.far_key}
        threat = retreat_veto_life.Threat("x", raw["turn"])
        life = getattr(policy, retreat_veto_life.MEMORY, None) or retreat_veto_life.Life()
        life.threats = {**life.threats, **{key: threat for key in keys}}
        setattr(policy, retreat_veto_life.MEMORY, life)
        visit = oneshot_breath.Visit(parse_snapshot(copy.deepcopy(raw), case.races).floor_key)
        visit.threats = {key: threat for key in keys}
        setattr(policy, oneshot_breath.MEMORY, visit)
        case.assertEqual(case.decide(policy, raw)[1], escape.DESTRUCTION_REASON)
        after = dict(copy.deepcopy(raw), turn=raw["turn"] + 10, messages=[])
        after["visible_monsters"] = [m for m in after["visible_monsters"] if m["race_id"] != LOCUST]
        escape.flash(after)
        survives = destruction_use._survives
        spare = self.spare_race

        def spared(policy_, snapshot, monster):
            return monster.race_id == spare or survives(policy_, snapshot, monster)

        with mock.patch.object(destruction_use, "_survives", spared):
            case.decide(policy, after)
        self.policy = policy
        return self


class DestructionForgetsTest(escape.EscapeCountRecordedTest):
    """Run through the escape-count harness (its own tests are not repeated here)."""

    def flow(self, **kwargs):
        with escape.no_depth_gate():
            return _Flow(self, **kwargs).run()

    def test_the_deleted_leave_every_memory_and_the_far_one_stays(self):
        flow = self.flow()
        life = getattr(flow.policy, retreat_veto_life.MEMORY)
        visit = getattr(flow.policy, oneshot_breath.MEMORY)
        self.assertEqual(set(life.threats) & flow.locust_keys, set())
        self.assertEqual(set(visit.threats) & flow.locust_keys, set())
        self.assertIn(flow.far_key, life.threats)
        self.assertIn(flow.far_key, visit.threats)

    def test_the_quest_target_is_kept(self):
        flow = self.flow(spare_race=LOCUST)
        life = getattr(flow.policy, retreat_veto_life.MEMORY)
        self.assertTrue(flow.locust_keys <= set(life.threats))


# The harness's own cases run in their module.
for _name in [name for name in vars(escape.EscapeCountRecordedTest) if name.startswith("test_")]:
    setattr(DestructionForgetsTest, _name, None)


if __name__ == "__main__":
    unittest.main()
