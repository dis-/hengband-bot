import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hengbot.cli import (
    COMMAND_RESPONSE_GRACE,
    DECISION_WATCHDOG_SECONDS,
    DUMP_INTERVAL_SECONDS,
    EconomyLedger,
    LOOP_WINDOW,
    STATIONARY_EXEMPT_REASONS,
    MULTI_KEY_DELAY_SECONDS,
    MULTIPLIER_COMBAT_LOOP_WINDOW,
    REST_STALL_GRACE,
    STORE_ITEM_PROMPT_DELAY_SECONDS,
    STORE_QUANTITY_DIGIT_DELAY_SECONDS,
    STATIONARY_REASONS,
    STALLED_COMMAND_STATE_LIMIT,
    TUNNEL_PROMPT_DELAY_SECONDS,
    TUNNEL_MACRO_TRIGGERS,
    TRAVEL_MACRO_TRIGGERS,
    TRAVEL_PROMPT_DELAY_SECONDS,
    _advance_stalled_command_count,
    _arm_decision_watchdog,
    _cell_loop_guard_applies,
    _uses_multiplier_combat_grace,
    _delay_after_macro_key,
    _decision_record,
    _duplicate_snapshot_ready,
    _fundraising_state,
    _floor_transition_needs_prompt_clear,
    _deduplicate_consecutive,
    _is_looping,
    _newest_snapshot,
    _read_last_line,
    _request_due_dump,
    _rewind_if_truncated,
    _last_activity_after_read,
    _stall_recovery_key,
    _split_complete_lines,
    _transport_key,
    _bot_play_macros_ready,
    _valid_bot_play_macro_pref,
)
from hengbot.cli import _game_process_alive
from hengbot.monrace_knowledge import MonraceKnowledge
from hengbot.model import MissingMonraceKnowledgeError, Position, parse_snapshot


class DecisionWatchdogTest(unittest.TestCase):
    @patch("hengbot.cli.faulthandler.dump_traceback_later")
    @patch("hengbot.cli.faulthandler.cancel_dump_traceback_later")
    def test_rearms_for_each_decision_iteration(self, cancel, dump):
        _arm_decision_watchdog()
        _arm_decision_watchdog()

        self.assertEqual(cancel.call_count, 2)
        self.assertEqual(dump.call_count, 2)
        for call in dump.call_args_list:
            self.assertEqual(call.args, (DECISION_WATCHDOG_SECONDS,))
            self.assertGreater(DECISION_WATCHDOG_SECONDS, 60)
            self.assertTrue(call.kwargs["repeat"])
            self.assertIsNotNone(call.kwargs["file"])


class PeriodicDumpTimerTest(unittest.TestCase):
    def test_elapsed_timer_latches_once_and_moves_deadline(self):
        policy = unittest.mock.Mock()

        deadline = _request_due_dump(policy, 100.0, 99.0)

        policy.request_character_dump.assert_called_once_with()
        self.assertEqual(deadline, 100.0 + DUMP_INTERVAL_SECONDS)
        self.assertEqual(_request_due_dump(policy, 101.0, deadline), deadline)
        policy.request_character_dump.assert_called_once_with()


def _snap_line(turn, y, x):
    return (
        json.dumps(
            {
                "turn": turn,
                "player": {"y": y, "x": x, "hp": 10, "max_hp": 10},
                "floor": {"dungeon_id": 0, "level": 1},
            }
        )
        + "\n"
    )


class EconomyLedgerTest(unittest.TestCase):
    @staticmethod
    def _snapshot(turn, gold):
        data = json.loads(_snap_line(turn, 5, 7))
        data["player"]["gold"] = gold
        return parse_snapshot(data, {})

    def test_records_confirmed_expense_and_income_with_causes(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "bot-economy.jsonl"
            ledger = EconomyLedger(path)
            before = self._snapshot(100, 1000)
            ledger.prime(before)

            self.assertIsNone(
                ledger.observe(before, "pa\r", "shop:buy-recall")
            )
            expense = ledger.observe(
                self._snapshot(101, 750), "\x1b", "shop:leave"
            )
            ledger.observe(
                self._snapshot(101, 750), "g", "fundraise:pickup"
            )
            income = ledger.observe(
                self._snapshot(102, 825), "6", "fundraise:seek-loot"
            )

            self.assertEqual(
                expense,
                {
                    **expense,
                    "kind": "expense",
                    "amount": 250,
                    "delta": -250,
                    "gold_before": 1000,
                    "gold_after": 750,
                    "cause_reason": "shop:buy-recall",
                    "cause_key": "pa\r",
                },
            )
            self.assertEqual(income["kind"], "income")
            self.assertEqual(income["amount"], 75)
            self.assertEqual(income["cause_reason"], "fundraise:pickup")
            records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(records, [expense, income])


class NewestSnapshotTest(unittest.TestCase):
    def test_parses_equipment_optimizer_player_inputs(self):
        data = json.loads(_snap_line(100, 5, 5))
        data["player"].update(
            {
                "class_id": 0,
                "race_id": 12,
                "personality_id": 3,
                "stats": {
                    name: {
                        "cur": 10 + index,
                        "max": 11 + index,
                        "use": 12 + index,
                        "index": 13 + index,
                    }
                    for index, name in enumerate(("str", "int", "wis", "dex", "con", "chr"))
                },
                "skills": {
                    "melee": 70,
                    "saving": 40,
                    "device": 31,
                    "stealth": 2,
                    "two_weapon": 123,
                    "shield": 456,
                },
            }
        )
        data["equipment"] = [
            {
                "slot": "main_hand",
                "name": "Sword",
                "count": 1,
                "tval": 23,
                "sval": 1,
                "aware": True,
                "known": True,
                "fully_known": True,
                "is_equipment": True,
                "weight": 120,
                "weapon_proficiency": 3456,
            }
        ]
        snapshot = parse_snapshot(data, {})
        self.assertEqual(snapshot.player.race_id, 12)
        self.assertEqual(snapshot.player.personality_id, 3)
        self.assertEqual(snapshot.player.stat_cur, (10, 11, 12, 13, 14, 15))
        self.assertEqual(snapshot.player.stat_index, (13, 14, 15, 16, 17, 18))
        self.assertEqual(snapshot.player.two_weapon_skill, 123)
        self.assertEqual(snapshot.player.shield_skill, 456)
        self.assertEqual(snapshot.equipment[0].weight, 120)
        self.assertEqual(snapshot.equipment[0].weapon_proficiency, 3456)

    def test_returns_only_the_latest_of_a_batch(self):
        # A fast monster can emit several prompts before we read; we must act on
        # the newest board, not replay the stale ones (which desyncs our keys).
        batch = [_snap_line(100, 5, 5), _snap_line(110, 5, 6), _snap_line(120, 6, 6)]
        snap = _newest_snapshot(batch)
        self.assertIsNotNone(snap)
        self.assertEqual(snap.turn, 120)
        self.assertEqual((snap.player.position.y, snap.player.position.x), (6, 6))

    def test_skips_a_malformed_trailing_line(self):
        batch = [_snap_line(100, 5, 5), '{"turn": 110, "player":\n']
        snap = _newest_snapshot(batch)
        self.assertIsNotNone(snap)
        self.assertEqual(snap.turn, 100)

    def test_returns_none_for_empty_or_all_blank(self):
        self.assertIsNone(_newest_snapshot([]))
        self.assertIsNone(_newest_snapshot(["\n", "   \n"]))

    def test_derives_summoning_from_race_id_not_snapshot_capabilities(self):
        data = json.loads(_snap_line(100, 5, 5))
        data["nearby_grids"] = [
            {
                "y": 5,
                "x": 6,
                "known": True,
                "monster_index": 1,
                "terrain": {"move": True},
            },
            {
                "y": 5,
                "x": 7,
                "known": True,
                "monster_index": 2,
                "terrain": {"move": True},
            },
        ]
        data["visible_monsters"] = [
            {
                "index": 1,
                "race_id": 124,
                "can_summon": False,
                "hp": 1,
                "max_hp": 1,
                "speed": 999,
                "health": "badly_wounded",
                "confused": True,
            },
            {
                "index": 2,
                "race_id": 125,
                "can_summon": True,
            },
        ]
        knowledge = {
            124: MonraceKnowledge(100, 115, True, False),
            125: MonraceKnowledge(20, 110, False, False),
        }
        snapshot = _newest_snapshot(
            [json.dumps(data) + "\n"], knowledge
        )
        self.assertTrue(snapshot.visible_monsters[0].can_summon)
        self.assertFalse(snapshot.visible_monsters[1].can_summon)
        self.assertEqual(snapshot.visible_monsters[0].hp, 24)
        self.assertEqual(snapshot.visible_monsters[0].max_hp, 100)
        self.assertEqual(snapshot.visible_monsters[0].speed, 115)
        self.assertTrue(snapshot.visible_monsters[0].confused)
        self.assertEqual(snapshot.visible_monsters[0].position.x, 6)

    def test_rejects_a_visible_monster_missing_from_static_knowledge(self):
        data = json.loads(_snap_line(100, 5, 5))
        data["nearby_grids"] = [
            {
                "y": 5,
                "x": 6,
                "known": True,
                "monster_index": 1,
                "terrain": {"move": True},
            }
        ]
        data["visible_monsters"] = [{"index": 1, "race_id": 9999}]
        with self.assertRaisesRegex(MissingMonraceKnowledgeError, "race_id=9999"):
            parse_snapshot(data, {})

        with self.assertRaises(MissingMonraceKnowledgeError):
            _newest_snapshot([json.dumps(data) + "\n"], {})

    def test_hallucinated_monster_is_a_positional_threat_without_identity(self):
        # While hallucinating, the emitter reports the tile a monster occupies but
        # redacts its identity/health. The bot must still register a hostile at
        # that position — and must NOT raise for the absent race_id.
        data = json.loads(_snap_line(100, 5, 5))
        data["nearby_grids"] = [
            {
                "y": 5,
                "x": 6,
                "known": True,
                "monster_index": 1,
                "terrain": {"move": True},
            }
        ]
        data["visible_monsters"] = [
            {"index": 1, "hallucinated": True, "friendly": False, "pet": False}
        ]
        snapshot = parse_snapshot(data, {})  # empty knowledge must not raise
        monster = snapshot.visible_monsters[0]
        self.assertTrue(monster.hostile)
        self.assertEqual((monster.position.y, monster.position.x), (5, 6))
        self.assertEqual(monster.race_id, 0)
        self.assertFalse(monster.can_summon)

    def test_hallucinated_pet_is_not_treated_as_hostile(self):
        data = json.loads(_snap_line(100, 5, 5))
        data["nearby_grids"] = [
            {"y": 5, "x": 6, "known": True, "monster_index": 1, "terrain": {"move": True}}
        ]
        data["visible_monsters"] = [
            {"index": 1, "hallucinated": True, "friendly": True, "pet": True}
        ]
        monster = parse_snapshot(data, {}).visible_monsters[0]
        self.assertFalse(monster.hostile)

    def test_parses_redacted_unidentified_item_details(self):
        data = json.loads(_snap_line(100, 5, 5))
        data["inventory"] = [
            {
                "slot": "h",
                "name": "an unknown scroll",
                "count": 1,
                "tval": 70,
                "aware": False,
                "known": False,
                "pseudo_feeling": "average",
                "inscription": "keep HEAVY_CURSE",
            }
        ]

        item = parse_snapshot(data, {}).inventory[0]

        self.assertEqual(item.sval, -1)
        self.assertEqual(item.charges, 0)
        self.assertEqual(item.fuel, 0)
        self.assertFalse(item.aware)
        self.assertFalse(item.known)
        self.assertFalse(item.fully_known)
        self.assertEqual(item.pseudo_feeling, "average")
        self.assertEqual(item.inscription, "keep HEAVY_CURSE")

    def test_parses_the_in_town_flag(self):
        data = json.loads(_snap_line(100, 5, 5))
        data["floor"]["level"] = 0
        data["floor"]["in_town"] = False  # on the open wilderness surface
        snap = parse_snapshot(data, {})
        self.assertFalse(snap.in_town)
        self.assertTrue(snap.on_open_wilderness)
        data["floor"]["in_town"] = True
        town = parse_snapshot(data, {})
        self.assertTrue(town.in_town)
        self.assertFalse(town.on_open_wilderness)

    def test_parses_fixed_quest_progress_and_visible_quest_grids(self):
        data = json.loads(_snap_line(100, 5, 5))
        data["floor"].update({"level": 0, "in_town": True, "town_id": 0, "town_index": 1})
        data["progress"] = {
            "quests": [
                {
                    "id": 1,
                    "name": "Thieves Hideout",
                    "status": 1,
                    "type": 6,
                    "level": 5,
                    "dungeon_id": 0,
                    "r_idx": 0,
                    "cur_num": 0,
                    "max_num": 0,
                    "num_mon": 0,
                    "flags": 6,
                    "complev": 0,
                    "comptime": 0,
                    "fixed": True,
                    "has_reward": True,
                    "reward_artifact_id": None,
                    "reward_baseitem_id": 42,
                    "reward_instant_artifact": False,
                }
            ]
        }
        data["nearby_grids"] = [
            {
                "y": 5,
                "x": 6,
                "known": True,
                "terrain": {"move": True, "quest_enter": True, "quest_exit": False},
                "quest_id": 1,
            },
            {
                "y": 5,
                "x": 7,
                "known": True,
                "terrain": {"move": True, "building": True},
                "building_type": 1,
                "building_special": 1,
            },
        ]

        snap = parse_snapshot(data, {})

        self.assertEqual(snap.town_id, 0)
        self.assertIsNone(snap.visited_town_ids)
        self.assertEqual(snap.town_index, 1)
        self.assertIn(1, snap.quests)
        self.assertEqual(snap.quests[1].status, 1)
        self.assertTrue(snap.quests[1].fixed)
        self.assertEqual(snap.quests[1].reward_baseitem_id, 42)
        self.assertTrue(snap.grids[Position(5, 6)].has_quest_enter)
        self.assertEqual(snap.grids[Position(5, 6)].quest_id, 1)
        self.assertEqual(snap.grids[Position(5, 7)].building_special, 1)

        data["progress"]["visited_town_ids"] = [0, 1]
        with_towns = parse_snapshot(data, {})
        self.assertEqual(with_towns.visited_town_ids, (0, 1))

    def test_parses_entered_dungeon_ids_for_recall_selection(self):
        data = json.loads(_snap_line(100, 5, 5))
        data["progress"] = {
            "recall_dungeon_id": 2,
            "entered_dungeon_ids": [1, 2, 5],
        }

        snap = parse_snapshot(data, {})

        self.assertEqual(snap.entered_dungeon_ids, (1, 2, 5))

    def test_ignores_legacy_exact_food_and_recall_counters(self):
        data = json.loads(_snap_line(100, 5, 5))
        data["player"]["food"] = 1
        data["player"]["word_recall"] = 17

        player = parse_snapshot(data, {}).player

        self.assertEqual(player.food_state, "unknown")
        self.assertFalse(player.recalling)

    def test_parses_redacted_home_item_without_hidden_kind_or_price(self):
        data = json.loads(_snap_line(100, 5, 5))
        data["store"] = {
            "store_type": 7,
            "items": [
                {
                    "letter": "a",
                    "name": "an unknown ring",
                    "count": 1,
                    "tval": 45,
                    "aware": False,
                    "known": False,
                    "fully_known": False,
                }
            ],
        }

        stored = parse_snapshot(data, {}).store.items[0]

        self.assertEqual(stored.sval, -1)
        self.assertEqual(stored.price, 0)
        self.assertFalse(stored.aware)
        self.assertFalse(stored.known)
        self.assertFalse(stored.fully_known)

    def test_parses_store_device_charges_from_japanese_names(self):
        data = json.loads(_snap_line(100, 5, 5))
        data["store"] = {
            "store_type": 5,
            "items": [
                {"letter": "a", "name": "鑑定の杖 (12回分)", "count": 1,
                 "tval": 55, "sval": 5, "price": 500},
                {"letter": "b", "name": "岩石溶解の魔法棒（27回分）", "count": 3,
                 "tval": 65, "sval": 6, "price": 100},
            ],
        }

        staff, wand = parse_snapshot(data, {}).store.items

        self.assertEqual((staff.charges, staff.pval), (12, 12))
        self.assertEqual((wand.charges, wand.pval), (27, 27))

    def test_store_device_explicit_pval_remains_authoritative(self):
        data = json.loads(_snap_line(100, 5, 5))
        data["store"] = {
            "store_type": 7,
            "items": [{"letter": "a", "name": "鑑定の杖 (12回分)", "count": 1,
                       "tval": 55, "sval": 5, "pval": 19}],
        }

        stored = parse_snapshot(data, {}).store.items[0]

        self.assertEqual((stored.charges, stored.pval), (19, 19))

    def test_parses_visible_progress_grid_and_known_item_details(self):
        data = json.loads(_snap_line(100, 5, 5))
        data["player"].update(
            {
                "class_id": 0,
                "ac": 42,
                "melee": {
                    "main_hand_blows": 200,
                    "sub_hand_blows": 0,
                    "main_hand_to_h": 12,
                    "sub_hand_to_h": 0,
                    "main_hand_to_d": 7,
                    "sub_hand_to_d": 0,
                },
            }
        )
        data["progress"] = {
            "recall_dungeon_id": 1,
            "yeek_cave_conquered": True,
            "angband_recall_unlocked": True,
        }
        data["nearby_grids"] = [
            {
                "y": 5,
                "x": 6,
                "known": True,
                "terrain": {
                    "move": False,
                    "wall": True,
                    # Hengband veins are TUNNEL terrain but do not carry the
                    # narrower CAN_DIG flag currently emitted as `can_dig`.
                    "can_dig": False,
                    "has_gold": True,
                    "entrance": False,
                },
            },
            {
                "y": 5,
                "x": 7,
                "known": True,
                "terrain": {"move": True, "entrance": True},
                "entrance_dungeon_id": 2,
            },
        ]
        data["inventory"] = [
            {
                "slot": "a",
                "name": "known sword",
                "count": 1,
                "tval": 23,
                "sval": 1,
                "aware": True,
                "known": True,
                "fully_known": True,
                "is_equipment": True,
                "is_ego": True,
                "is_artifact": False,
                "is_cursed": False,
                "is_broken": False,
                "to_h": 3,
                "to_d": 4,
                "to_a": 0,
                "ac": 0,
                "damage_dice": {"num": 2, "sides": 5},
                "known_flags": [12, 34],
                "pval": 2,
                "timeout": 3,
            }
        ]

        snapshot = parse_snapshot(data, {})

        self.assertEqual(snapshot.player.class_id, 0)
        self.assertEqual(snapshot.player.ac, 42)
        self.assertEqual(snapshot.player.main_hand_blows, 200)
        self.assertTrue(snapshot.yeek_cave_conquered)
        self.assertTrue(snapshot.angband_recall_unlocked)
        self.assertTrue(snapshot.grids[Position(5, 6)].has_gold)
        self.assertTrue(snapshot.grids[Position(5, 6)].can_dig)
        self.assertEqual(snapshot.grids[Position(5, 7)].entrance_dungeon_id, 2)
        self.assertTrue(snapshot.inventory[0].is_ego)
        self.assertEqual(snapshot.inventory[0].known_flags, frozenset({12, 34}))
        self.assertEqual(snapshot.inventory[0].pval, 2)
        self.assertEqual(snapshot.inventory[0].timeout, 3)


class DecisionRecordTest(unittest.TestCase):
    def test_records_policy_reason_and_observable_state(self):
        data = json.loads(_snap_line(123, 5, 7))
        data["floor"]["quest_id"] = 40
        snapshot = parse_snapshot(data, {})

        requirements = [
            {"item": "Food rations", "current": 2, "target": 5, "missing": 3}
        ]
        record = _decision_record(snapshot, "6", "seek-loot", requirements)

        self.assertEqual(record["turn"], 123)
        self.assertEqual(record["objective"], "Collect visible floor items")
        self.assertEqual(record["reason"], "seek-loot")
        self.assertEqual(record["key"], "6")
        self.assertEqual(
            record["floor"], {"dungeon_id": 0, "level": 1, "quest_id": 40}
        )
        self.assertEqual(record["position"], {"y": 5, "x": 7})
        self.assertEqual(record["inventory"], {"used": 0, "free": 23})
        self.assertEqual(record["procurement_requirements"], requirements)
        self.assertEqual(record["visible_hostiles"], 0)
        self.assertEqual(record["threat_prediction"], {})
        self.assertEqual(record["loot"], {})

    def test_records_loot_telemetry(self):
        snapshot = parse_snapshot(json.loads(_snap_line(123, 5, 7)), {})
        loot = {
            "visible": [{"position": {"y": 5, "x": 8}, "count": 1}],
            "known": [{"y": 5, "x": 8}],
            "target": {"y": 5, "x": 8},
            "blocker": None,
        }

        record = _decision_record(
            snapshot, "6", "seek-loot", loot=loot
        )

        self.assertEqual(record["loot"], loot)

    def test_records_fundraising_telemetry(self):
        data = json.loads(_snap_line(123, 5, 7))
        data["floor"]["dungeon_id"] = 0
        data["floor"]["level"] = 0
        data["player"]["class_id"] = 0
        data["player"]["gold"] = 100
        snapshot = parse_snapshot(data, {})

        class Policy:
            _fundraising_mode = "prepare"
            _planned_mining_runs = 2

            def _fundraising_kit_secured(self, snapshot):
                return False

        fundraising = _fundraising_state(snapshot, Policy())
        record = _decision_record(
            snapshot, "6", "fundraise:prepare", fundraising=fundraising
        )

        self.assertEqual(
            record["fundraising"],
            {
                "mode": "prepare",
                "planned_runs": 2,
                "kit_secured": False,
                "gold_trigger": True,
            },
        )


class DuplicateSnapshotThrottleTest(unittest.TestCase):
    def test_throttles_an_exact_duplicate_until_retry_interval(self):
        line = _snap_line(100, 5, 5)

        self.assertFalse(_duplicate_snapshot_ready(line, line, 1.9))
        self.assertTrue(_duplicate_snapshot_ready(line, line, 2.0))

    def test_acts_immediately_when_snapshot_state_changes(self):
        previous = _snap_line(100, 5, 5)
        current = _snap_line(110, 5, 6)

        self.assertTrue(_duplicate_snapshot_ready(current, previous, 0.0))

    def test_emits_one_purchase_until_a_new_store_snapshot_arrives(self):
        line = _snap_line(2068969, 31, 91)
        emitted = []
        previous_line = None
        previous_reason = None

        for elapsed in (0.0, 2.0):
            if _duplicate_snapshot_ready(
                line, previous_line, elapsed, previous_reason
            ):
                emitted.append("ph30\r\r")
                previous_line = line
                previous_reason = "shop:buy-ammo"

        self.assertEqual(emitted, ["ph30\r\r"])
        changed_data = json.loads(line)
        changed_data["player"]["gold"] = 970
        changed = json.dumps(changed_data) + "\n"
        self.assertTrue(
            _duplicate_snapshot_ready(changed, previous_line, 0.0, previous_reason)
        )


class LoopDetectionTest(unittest.TestCase):
    FLOOR = (2, 1, 0)

    def test_flags_a_two_tile_oscillation(self):
        # The live failure: bouncing between exactly two tiles on one floor.
        from collections import deque

        cells = deque(maxlen=LOOP_WINDOW)
        for i in range(LOOP_WINDOW):
            cells.append((self.FLOOR, 15, 43) if i % 2 else (self.FLOOR, 16, 42))
        self.assertTrue(_is_looping(cells))

    def test_ignores_a_healthy_sweep(self):
        from collections import deque

        cells = deque(maxlen=LOOP_WINDOW)
        for i in range(LOOP_WINDOW):
            cells.append((self.FLOOR, 10, 10 + i))  # marching down a corridor
        self.assertFalse(_is_looping(cells))

    def test_does_not_flag_before_the_window_fills(self):
        from collections import deque

        cells = deque(maxlen=LOOP_WINDOW)
        for i in range(LOOP_WINDOW - 1):
            cells.append((self.FLOOR, 15, 43) if i % 2 else (self.FLOOR, 16, 42))
        self.assertFalse(_is_looping(cells))

    def test_multiplier_combat_uses_a_larger_finite_window(self):
        from collections import deque

        cells = deque(maxlen=MULTIPLIER_COMBAT_LOOP_WINDOW)
        for i in range(LOOP_WINDOW):
            cells.append((self.FLOOR, 15, 43) if i % 2 else (self.FLOOR, 16, 42))
        self.assertFalse(
            _is_looping(cells, window=MULTIPLIER_COMBAT_LOOP_WINDOW)
        )

        for i in range(LOOP_WINDOW, MULTIPLIER_COMBAT_LOOP_WINDOW):
            cells.append((self.FLOOR, 15, 43) if i % 2 else (self.FLOOR, 16, 42))
        self.assertTrue(
            _is_looping(cells, window=MULTIPLIER_COMBAT_LOOP_WINDOW)
        )

    def test_floor_change_resets_the_signal(self):
        # Confined tiles but spread across two floors is descent, not a loop.
        from collections import deque

        cells = deque(maxlen=LOOP_WINDOW)
        for i in range(LOOP_WINDOW):
            floor = (2, 1, 0) if i < LOOP_WINDOW // 2 else (2, 2, 0)
            cells.append((floor, 15, 43))
        self.assertFalse(_is_looping(cells))

    def test_flags_a_two_floor_stair_ping_pong(self):
        from collections import deque

        cells = deque(maxlen=LOOP_WINDOW)
        for i in range(LOOP_WINDOW):
            if i % 2:
                cells.append(((2, 10, 0), 7, 16))
            else:
                cells.append(((2, 9, 0), 13, 54))
        self.assertTrue(_is_looping(cells))


class DeduplicateConsecutiveTest(unittest.TestCase):
    def test_drops_only_consecutive_duplicate_snapshots(self):
        lines = ["first\n", "first\n", "second\n", "first\n"]

        self.assertEqual(
            list(_deduplicate_consecutive(lines)),
            ["first\n", "second\n", "first\n"],
        )


class CompleteLineTest(unittest.TestCase):
    def test_buffers_an_incomplete_line(self):
        complete, pending = _split_complete_lines('first\n{"turn":')
        self.assertEqual(complete, ["first\n"])
        self.assertEqual(pending, '{"turn":')

        complete, pending = _split_complete_lines(pending + "1}\n")
        self.assertEqual(complete, ['{"turn":1}\n'])
        self.assertEqual(pending, "")

    def test_once_ignores_an_incomplete_trailing_line(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "state.jsonl"
            path.write_text('{"turn":1}\n{"turn":', encoding="utf-8")

            self.assertEqual(list(_read_last_line(path)), ['{"turn":1}'])


class RolloverTest(unittest.TestCase):
    def test_rewinds_an_open_reader_after_emitter_truncation(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "state.jsonl"
            path.write_text("old snapshot\n" * 20, encoding="utf-8")

            with path.open("r", encoding="utf-8") as stream:
                stream.seek(0, 2)
                path.write_text("new snapshot\n", encoding="utf-8")

                self.assertTrue(_rewind_if_truncated(stream, path))
                self.assertEqual(stream.read(), "new snapshot\n")


class StallRecoveryTest(unittest.TestCase):
    def test_floor_transition_clears_arrival_prompt_exactly_on_change(self):
        town = (0, 0, 0)
        yeek_one = (2, 1, 0)

        self.assertFalse(_floor_transition_needs_prompt_clear(None, town))
        self.assertFalse(_floor_transition_needs_prompt_clear(town, town))
        self.assertTrue(_floor_transition_needs_prompt_clear(town, yeek_one))
        self.assertTrue(_floor_transition_needs_prompt_clear(yeek_one, town))

    def test_command_response_grace_covers_live_snapshot_serialization(self):
        self.assertGreater(COMMAND_RESPONSE_GRACE, 9.0)
        self.assertLess(COMMAND_RESPONSE_GRACE, REST_STALL_GRACE)

    def test_partial_snapshot_bytes_refresh_emitter_activity(self):
        self.assertEqual(
            _last_activity_after_read(10.0, 20.0, '{"turn":'),
            20.0,
        )
        self.assertEqual(_last_activity_after_read(10.0, 20.0, ""), 10.0)

    def test_counts_repeated_command_with_no_state_progress(self):
        signature = ((2, 1, 0), 100, 10, 20, "fundraise:mine-treasure", "T3")
        count = 0
        for _ in range(STALLED_COMMAND_STATE_LIMIT):
            count = _advance_stalled_command_count(
                count,
                signature=signature,
                previous_signature=signature,
            )
        self.assertEqual(count, STALLED_COMMAND_STATE_LIMIT)

    def test_stalled_snapshot_count_resets_on_real_progress(self):
        self.assertEqual(
            _advance_stalled_command_count(
                2,
                signature=("new",),
                previous_signature=("old",),
            ),
            0,
        )

    def test_tunnel_macro_waits_for_direction_prompt(self):
        self.assertEqual(_delay_after_macro_key("T3", 0), TUNNEL_PROMPT_DELAY_SECONDS)
        self.assertEqual(_delay_after_macro_key("T3", 1), 0.0)
        self.assertEqual(_delay_after_macro_key("rb", 0), MULTI_KEY_DELAY_SECONDS)

    def test_travel_fallback_waits_for_each_selector_redraw(self):
        key = "\x1b`n%."
        self.assertEqual(_delay_after_macro_key(key, 0), MULTI_KEY_DELAY_SECONDS)
        for index in (1, 2, 3):
            self.assertEqual(
                _delay_after_macro_key(key, index), TRAVEL_PROMPT_DELAY_SECONDS
            )
        self.assertEqual(_delay_after_macro_key(key, 4), 0.0)

    def test_loaded_tunnel_macro_replaces_each_direction_with_one_character(self):
        for direction, trigger in TUNNEL_MACRO_TRIGGERS.items():
            self.assertEqual(_transport_key(f"T{direction}", True), trigger)
            self.assertEqual(len(_transport_key(f"T{direction}", True)), 1)
        self.assertEqual(_transport_key("T5", True), "T5")
        self.assertEqual(_transport_key("T3", False), "T3")
        self.assertEqual(_transport_key("qf", True), "qf")

    def test_loaded_travel_macro_replaces_each_destination_with_one_character(self):
        for macro, trigger in TRAVEL_MACRO_TRIGGERS.items():
            self.assertEqual(_transport_key(macro, True), trigger)
            self.assertEqual(len(_transport_key(macro, True)), 1)
        self.assertEqual(_transport_key("\x1b`n%.", False), "\x1b`n%.")

    def test_tunnel_macros_require_pref_loaded_before_this_game_started(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            edit = root / "lib" / "edit"
            user = root / "lib" / "user"
            logs = root / "logs"
            edit.mkdir(parents=True)
            user.mkdir(parents=True)
            logs.mkdir()
            monrace = edit / "MonraceDefinitions.jsonc"
            monrace.write_text("{}", encoding="ascii")
            pref = user / "bot-test.prf"
            pref.write_text(
                "# HENGBOT_INPUT_MACROS_V2\n"
                "A:T1\nP:^A\nA:T2\nP:^B\nA:T3\nP:^C\nA:T4\nP:^D\n"
                "A:T6\nP:^E\nA:T7\nP:^F\nA:T8\nP:^G\nA:T9\nP:^H\n"
                "A:\\e`n!.\nP:^K\nA:\\e`n\".\nP:^L\nA:\\e`n#.\nP:^N\n"
                "A:\\e`n$.\nP:^O\nA:\\e`n%.\nP:^P\nA:\\e`n&.\nP:^Q\n"
                "A:\\e`n'.\nP:^R\nA:\\e`n(.\nP:^S\nA:\\e`n>.\nP:^T\n",
                encoding="ascii",
            )
            pid_file = logs / "hengband.pid"
            pid_file.write_text("1234", encoding="ascii")
            state_file = logs / "state.jsonl"

            self.assertTrue(_valid_bot_play_macro_pref(pref))
            self.assertTrue(_bot_play_macros_ready(state_file, monrace, 1234))
            self.assertFalse(_bot_play_macros_ready(state_file, monrace, 4321))

            newer = pid_file.stat().st_mtime_ns + 1_000_000_000
            os.utime(pref, ns=(newer, newer))
            self.assertFalse(_bot_play_macros_ready(state_file, monrace, 1234))

    def test_incomplete_tunnel_macro_pref_is_rejected(self):
        with TemporaryDirectory() as temp:
            pref = Path(temp) / "bot-test.prf"
            pref.write_text(
                "# HENGBOT_INPUT_MACROS_V2\nA:T1\nP:^A\n",
                encoding="ascii",
            )
            self.assertFalse(_valid_bot_play_macro_pref(pref))

    def test_store_transaction_macros_have_no_inter_key_delay(self):
        for macro in ("dk\r", "dj99\ry", "pf10\r\r", "{x@0\r{y@1\r"):
            for index in range(len(macro)):
                self.assertEqual(_delay_after_macro_key(macro, index), 0.0)
        self.assertEqual(
            _delay_after_macro_key("ga\r", 0),
            STORE_ITEM_PROMPT_DELAY_SECONDS,
        )

    def test_answers_the_level_ten_stat_prompt_after_escape_nudges(self):
        self.assertEqual(_stall_recovery_key(0, 9), ("\x1b", "<esc>"))
        self.assertEqual(_stall_recovery_key(1, 9), ("\x1b", "<esc>"))
        self.assertEqual(_stall_recovery_key(2, 9), ("a", "<level-stat:a>"))
        self.assertEqual(_stall_recovery_key(3, 9), ("y", "<level-stat:y>"))

    def test_keeps_retrying_the_stat_answers_if_a_key_was_lost(self):
        # A single lost 'a' or 'y' must not strand the game on the stat screen:
        # the recovery alternates the two answers until the terminal limit.
        self.assertEqual(_stall_recovery_key(4, 9), ("a", "<level-stat:a>"))
        self.assertEqual(_stall_recovery_key(5, 9), ("y", "<level-stat:y>"))

    def test_covers_a_two_level_jump_over_the_stat_threshold(self):
        # One out-of-depth kill can jump 8→10; the last snapshot still says
        # clvl 8, and the stat screen is up all the same.
        self.assertEqual(_stall_recovery_key(2, 8), ("a", "<level-stat:a>"))
        self.assertEqual(_stall_recovery_key(3, 18), ("y", "<level-stat:y>"))

    def test_does_not_send_stat_answers_at_other_levels(self):
        self.assertEqual(_stall_recovery_key(2, 7), ("\x1b", "<esc>"))
        self.assertEqual(_stall_recovery_key(3, 10), ("\x1b", "<esc>"))
        self.assertEqual(_stall_recovery_key(2, None), ("\x1b", "<esc>"))


class StationaryReasonsTest(unittest.TestCase):
    def test_town_uses_policy_cycle_guard_instead_of_cell_guard(self):
        town = parse_snapshot(
            json.loads(_snap_line(1, 10, 10).replace('"level": 1', '"level": 0')),
            {},
        )
        dungeon = parse_snapshot(json.loads(_snap_line(1, 10, 10)), {})

        self.assertFalse(_cell_loop_guard_applies(town, "shop:approach"))
        self.assertTrue(_cell_loop_guard_applies(dungeon, "explore"))

    def test_recall_waits_are_exempt_from_loop_detection(self):
        # Waiting out a Word of Recall countdown pins the player on one tile for
        # ~15-35 turns; if those decisions fed the detector they could stop the
        # bot mid-return. They must be exempt, alongside search and in-place melee.
        self.assertIn("return:wait-recall", STATIONARY_REASONS)
        self.assertIn("town:wait-recall", STATIONARY_REASONS)
        self.assertIn("town:wait-restock", STATIONARY_REASONS)
        self.assertIn("search", STATIONARY_REASONS)
        self.assertIn("melee", STATIONARY_REASONS)

    def test_mining_digs_are_exempt_from_loop_detection(self):
        # Digging breaks rock while standing on ONE tile for many turns, which the
        # position-based loop guard would read as a confined oscillation. Mining digs
        # must be exempt (the policy's MINING_STALL_LIMIT leash bounds them instead), so
        # a long tunnel-to-a-vein or dig-out is never mistaken for a stuck loop.
        dungeon = parse_snapshot(json.loads(_snap_line(1, 10, 10)), {})
        self.assertIn("fundraise:mine-treasure", STATIONARY_EXEMPT_REASONS)
        self.assertIn("fundraise:tunnel-out", STATIONARY_EXEMPT_REASONS)
        self.assertFalse(
            _cell_loop_guard_applies(dungeon, "breakout:dig-to-stairs")
        )
        # Walking reasons stay guardable — only in-place digging is exempt. The
        # two-phase design never tunnels toward far veins, so the old
        # tunnel-to-treasure reason no longer exists at all.
        self.assertNotIn("fundraise:seek-treasure", STATIONARY_EXEMPT_REASONS)

    def test_fixed_quest_hold_is_exempt_from_loop_detection(self):
        dungeon = parse_snapshot(json.loads(_snap_line(1, 10, 10)), {})

        self.assertIn("quest-strategy:hold", STATIONARY_EXEMPT_REASONS)
        self.assertFalse(_cell_loop_guard_applies(dungeon, "quest-strategy:hold"))
        # Failed positioning can repeat for a real strategy defect, so only the
        # intentional at-post hold is exempt from the outer circuit breaker.
        self.assertTrue(
            _cell_loop_guard_applies(dungeon, "quest-strategy:hold-unreachable")
        )
        self.assertTrue(
            _cell_loop_guard_applies(dungeon, "quest-strategy:avoid-never-move")
        )

    def test_deep_fundraising_combat_uses_multiplier_grace_reason(self):
        """The live deep-mining policy calls multiplier/summoner combat
        ``fundraise:clear-hostile``.  Keep that current reason tied to the
        extended combat window instead of stopping at the generic 40 turns.
        """
        self.assertTrue(_uses_multiplier_combat_grace("fundraise:clear-hostile"))
        self.assertTrue(
            _uses_multiplier_combat_grace("fundraise:eliminate-multiplier")
        )
        self.assertFalse(_uses_multiplier_combat_grace("fundraise:sweep-explore"))
        self.assertNotIn("fundraise:tunnel-to-treasure", STATIONARY_EXEMPT_REASONS)


if __name__ == "__main__":
    unittest.main()


class GameProcessAliveTest(unittest.TestCase):
    """The bot concluded <dead> (and exited) on ANY 8-nudge snapshot silence —
    twice abandoning a healthy full-HP character stuck at a store prompt chain.
    Death is only concluded when the game PROCESS is actually gone."""

    def test_running_process_reads_alive(self):
        import os

        self.assertTrue(_game_process_alive(os.getpid()))

    def test_exited_process_reads_dead(self):
        import subprocess
        import sys

        proc = subprocess.Popen([sys.executable, "-c", "pass"])
        proc.wait()
        self.assertFalse(_game_process_alive(proc.pid))

    def test_unknown_pid_reads_dead(self):
        self.assertFalse(_game_process_alive(None))


class TownBlockedStreakTest(unittest.TestCase):
    """A latched town block waits in place; when it waits on a store door, the
    interleaved store snapshots reset the cell loop guard, so the visible stop
    never fired. The streak counter stops the bot regardless."""

    def test_blocked_decisions_accumulate_through_store_leaves(self):
        from hengbot.cli import _advance_town_blocked_streak

        streak = 0
        for reason in (
            "town:blocked:repetition",
            "shop:leave",
            "town:blocked:repetition",
            "town:blocked:repetition",
        ):
            streak = _advance_town_blocked_streak(streak, reason)
        self.assertEqual(streak, 3)

    def test_any_other_reason_resets_the_streak(self):
        from hengbot.cli import _advance_town_blocked_streak

        streak = _advance_town_blocked_streak(5, "shop:travel")
        self.assertEqual(streak, 0)


class TownResidenceStreakTest(unittest.TestCase):
    def test_counts_town_residence_and_resets_on_every_floor_change(self):
        from hengbot.cli import _advance_town_residence_streak

        town = (0, 0, 0)
        other_town_key = (0, 0, 1)
        dungeon = (1, 1, 0)
        streak = _advance_town_residence_streak(0, None, town)
        streak = _advance_town_residence_streak(streak, town, town)
        self.assertEqual(streak, 2)
        streak = _advance_town_residence_streak(streak, town, other_town_key)
        self.assertEqual(streak, 1)
        streak = _advance_town_residence_streak(streak, other_town_key, dungeon)
        self.assertEqual(streak, 0)
        streak = _advance_town_residence_streak(streak, dungeon, town)
        self.assertEqual(streak, 1)
