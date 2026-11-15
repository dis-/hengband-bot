"""n1-b (Magic-Eater) life-405 2026-11-16: the absorbed 分解 (Disintegrate) as an attack.

Owner 2026-11-16: 「分解攻撃は地形を壊して状況を悪化させ、アイテムを破損させるので使用を禁止する」.

The game (C:/hengband/src): the 分解 wand (wand_effect SV_WAND_DISINTEGRATE, cmd-zapwand.cpp)
fires a DISINTEGRATE ball; effect-feature.cpp turns every CAN_DISINTEGRATE, non-PERMANENT grid
in the blast into floor (granite, rubble, doors, glass), range-calc.cpp is_prevent_blast lets
only permanent walls stop it, and effect-item.cpp destroys every floor item in it but an
artifact (「蒸発してしまった！」).  No activation, rod or staff of the bot's two classes casts it.

Recorded: tests/fixtures/n1b-405-disintegrate-1116.json.xz
(tests/extract_n1b_405_disintegrate_1116_fixture.py), Castle 62F-64F, the Lv44 Magic-Eater
fired the absorbed 分解 37 times in life-405's kept decisions; four of them:

- decision 25576 (turn 3420952): ``mBz@26,46`` at a 雪女 (race 923) seven grids away;
- decision 25766 (turn 3421959): ``mBz@32,53`` at a 黒騎士 (race 442) ten grids away;
- decision 26312 (turn 3428695): ``mBz1`` at a コーウィンの銃士 (race 1094) two grids away;
- decision 26956 (turn 3434433): ``mBz6`` at a 1047 three grids east.

Every decision is the public ``choose_key`` of a fresh policy shown the lists first
(``observe_lists``, as the executor's menu reading would).

DECLARED RECONSTRUCTION / RESTORED (pin_vacuity): the frames of these decisions had rolled
away, so the absorbed lists are the earliest kept spectator frame's (decision 29803, about
50,000 game turns later: the same absorbed powers, 分解 at 1 of 4 charges and 79%); the skill knowledge is
supplied before the decision (tests/support/recorded ``skill``).
DECLARED CONSTRUCTED (each named at its test): the wand list holding 分解 alone, and the
carried 分解 wand (the pack's 魔法棒 of sval 24 renumbered 25).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
import unittest
from pathlib import Path

from hengbot import attack_expectation, me_device_attacks, me_ranged_first
from hengbot.dungeon_knowledge import load_dungeon_knowledge
from hengbot.me_device_attacks import DEVICE_REASON, observe_lists
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from tests.support.recorded import EDIT, skill

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-405-disintegrate-1116.json.xz"
DISINTEGRATE = ("wand", 25)
SEQUENCES = (25576, 25766, 26312, 26956)
TARGETS = {25576: (923, Position(26, 46)), 25766: (442, Position(32, 53)),
           26312: (1094, Position(10, 24)), 26956: (1047, Position(49, 59))}


def _disintegrate_key(key):
    # ``m`` + B (wand) + z (sval 25): the absorbed 分解 (me_device_attacks.device_key).
    return key.startswith("mBz")


class NoDisintegrateRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(lzma.decompress(FIXTURE.read_bytes()).decode("utf-8"))
        cls.races = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.dungeons = load_dungeon_knowledge(EDIT / "DungeonDefinitions.jsonc")

    def case(self, sequence):
        return copy.deepcopy(self.payload["cases"][str(sequence)])

    def decide(self, sequence, *, rows=None, change=None):
        """(key, reason, policy, snapshot): a fresh policy shown the lists first."""
        raw = self.case(sequence)["board"]
        if change is not None:
            change(raw)
        policy = HengbotPolicy(monrace_knowledge=dict(self.races),
                               dungeon_knowledge=dict(self.dungeons))
        policy.prime(parse_snapshot(copy.deepcopy(raw), self.races))
        for kind, entry in self.payload["lists"].items():
            shown_rows = entry["rows"] if rows is None else rows(kind, entry["rows"])
            shown = dict(copy.deepcopy(raw), turn=raw["turn"] - 1,
                         _magic_eater_power_list={"kind": kind, "rows": shown_rows})
            observe_lists(policy, parse_snapshot(shown, self.races))
        skill(policy, raw)
        snapshot = parse_snapshot(copy.deepcopy(raw), self.races)
        key = policy.choose_key(snapshot)
        return str(key), policy.last_reason, policy, snapshot

    def target(self, sequence, snapshot):
        race, position = TARGETS[sequence]
        return next(monster for monster in snapshot.visible_monsters
                    if monster.race_id == race and monster.position == position)

    def test_the_recorded_disintegrate_shots(self):
        for sequence in SEQUENCES:
            with self.subTest(sequence=sequence):
                decision = self.case(sequence)["decision"]
                self.assertEqual(decision["reason"], DEVICE_REASON)
                self.assertTrue(_disintegrate_key(decision["key"]), decision["key"])

    def test_the_lists_hold_disintegrate_charged(self):
        wand = {row["name"]: row for row in self.payload["lists"]["wand"]["rows"]}
        self.assertEqual((wand["分解"]["current"], wand["分解"]["max"], wand["分解"]["success"]),
                         (1, 4, 79))

    def test_another_absorbed_power_answers_instead(self):
        for sequence in SEQUENCES:
            with self.subTest(sequence=sequence):
                key, reason, policy, snapshot = self.decide(sequence)
                self.assertEqual(reason, DEVICE_REASON)
                self.assertFalse(_disintegrate_key(key), key)
                target = self.target(sequence, snapshot)
                direction = key[3] if len(key) == 4 else "5"
                ranked = me_device_attacks.scored(policy, snapshot, target, direction)
                self.assertTrue(ranked)
                self.assertNotIn(DISINTEGRATE,
                                 {(power.kind, power.sval) for _, power in ranked})

    def test_disintegrate_is_absorbed_but_never_an_attack(self):
        _, _, policy, _ = self.decide(25576)
        names = {row["name"] for _, (_, rows) in policy._me_device_lists.items() for row in rows}
        self.assertIn("分解", names)   # still listed (absorbed), so the lists keep it
        held = {(power.kind, power.sval) for power, _ in me_device_attacks.held_powers(policy)}
        self.assertNotIn(DISINTEGRATE, held)
        self.assertNotIn(DISINTEGRATE, me_device_attacks.POWERS)
        self.assertIn(DISINTEGRATE, me_device_attacks.FORBIDDEN_POWERS)
        self.assertEqual(me_device_attacks.FORBIDDEN_POWERS[DISINTEGRATE].element, "DISINTEGRATE")

    def test_counter_disintegrate_alone_is_not_fired(self):
        # DECLARED CONSTRUCTED: the wand list holds 分解 alone, every rod charging, no staff.
        def alone(kind, rows):
            if kind == "wand":
                return [row for row in rows if row["name"] == "分解"]
            if kind == "rod":
                return [dict(row, charging=row["max"]) for row in rows]
            return []
        for sequence in SEQUENCES:
            with self.subTest(sequence=sequence):
                key, _, policy, snapshot = self.decide(sequence, rows=alone)
                self.assertFalse(_disintegrate_key(key), key)
                target = self.target(sequence, snapshot)
                self.assertEqual(me_device_attacks.scored(policy, snapshot, target, "5"), [])

    def test_counter_a_carried_disintegrate_wand_is_not_aimed(self):
        # DECLARED CONSTRUCTED: the pack's known 魔法棒 (slot m, sval 24, 47 charges) made a 分解.
        def carried(raw):
            wand = next(item for item in raw["inventory"] if item["slot"] == "m")
            self.assertEqual((wand["tval"], wand["sval"]), (65, 24))
            wand["sval"] = 25
        _, _, policy, snapshot = self.decide(25576, change=carried)
        wand = next(item for item in snapshot.inventory if item.slot == "m")
        self.assertEqual((wand.sval, wand.known, wand.charges), (25, True, 47))
        target = self.target(25576, snapshot)
        self.assertNotIn(25, me_ranged_first.ATTACK_WAND_SVALS)
        self.assertIsNone(me_ranged_first._attack_wand(policy, snapshot, target, "6"))
        # The per-race plan count (Q25 and the supply fights) has no answer from it either.
        bare = dict(policy._me_device_lists)
        policy._me_device_lists = {}
        try:
            self.assertEqual(attack_expectation.devices_against(policy, snapshot, 923), 0.0)
        finally:
            policy._me_device_lists = bare


if __name__ == "__main__":
    unittest.main()
