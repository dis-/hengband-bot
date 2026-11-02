"""Owner 2026-10-31 night: the Magic-Eater's Powerful Activation (me_powerful_activation).

「魔道具術師の強力発動について。一旦鑑定と解呪だけ取り扱う。該当の杖を取り込んだら
上位鑑定と上位解呪の巻物は以降購入せず強力発動で対応する。」

Boards are the recorded n1-c life-033 Outpost board of D25
(tests/fixtures/n1c-town-stops2-20261030.json.gz, recorded Magic-shop page)
through the public ``choose_key`` and the production executor.

DECLARED CONSTRUCTED: the staff sequence complete (every sequence staff
absorbed); the character's level (the recorded life is level 8, the power
needs 10); the displayed staff power list (``_magic_eater_power_list`` rows
with the BaseitemDefinitions names 鑑定 / 解呪, charges and fail chosen per
case); a cursed worn short sword or a known ego worn short sword; the board
outside the shop (``store`` None at the recorded entrance) for the town
work, or a Temple / Alchemist page holding the recorded scroll's row shape
with the *Remove Curse* / *Identify* scroll for the purchase cases.  Replies
to posted keys are constructed from the game's prompts
(cmd-action/cmd-racial.cpp, cmd-item/cmd-magiceat.cpp,
spell-kind/spells-perception.cpp).
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
from unittest import mock

from hengbot import me_capability
from hengbot import me_powerful_activation as powerful
from hengbot import me_staff_sequence
from hengbot.cli import _ExecutorInputPort, SendResult
from hengbot.model import (
    SV_SCROLL_STAR_IDENTIFY, SV_SCROLL_STAR_REMOVE_CURSE, STORE_ALCHEMIST, STORE_TEMPLE,
    TVAL_SCROLL, parse_snapshot,
)
from hengbot.policy_constants import REST_MACRO
from tests import test_n1c_town_stops2_recorded as d25
from tests.test_input_executor import (
    FaithfulHookGame, command_screen, source_derived_identify_viewer,
)
from tests.test_magic_eater_o3 import prompt
from tests.test_me_device_attacks import power_screen
import tests.test_input_executor as executor_harness


LIFE = "life-033"
RACIAL_PROMPT = "(特殊能力 a-c, '*'で一覧, '/'で閲覧, ESCで中断) どの能力を使いますか？"
TYPE_PROMPT = "[A] 杖, [B] 魔法棒, [C] ロッド:"
FULL_IDENTIFY_PROMPT = "どのアイテムを*鑑定*しますか? "
NAMES = {powerful.IDENTIFY: "鑑定", powerful.UNCURSE: "解呪"}
BY_SVAL_EFFECT = powerful.BY_SVAL


def staff_list(effects=(powerful.IDENTIFY, powerful.UNCURSE), current=5):
    return {"kind": "staff", "rows": [
        {"name": NAMES[effect], "current": current, "max": 14, "fail": 20, "success": 80}
        for effect in effects]}


def racial_screen(level, *, listed=True):
    """cmd-racial.cpp racial_power_display_list at x=11 (class powers first).

    racial_power_process_input asks with input_spell_choice: kind spell,
    labels a..c, ``list`` while the rows are drawn (#47 n1-c life-074).
    """
    screen = prompt(RACIAL_PROMPT, "spell", first_label="a", last_label="c", list=listed,
                    browse=False, menu=False)
    if listed:
        screen["lines"][1] = " " * 11 + " " * 35 + "Lv   MP 失率 効果"
        rows = (("a", "魔力の取り込み", 1, 0), ("b", "強力発動", 10, powerful.cost(level)),
                ("c", "経験値復活", 30, 30))
        for index, (letter, name, minimum, mp) in enumerate(rows):
            screen["lines"][2 + index] = " " * 11 + f" {letter}) {name:<26} {minimum:2} {mp:4} 100% "
    return screen


def staff_powers(current=5):
    """cmd-magiceat.cpp's staff list: I2A(sval) letters 'f' (5) and 'g' (6)."""
    return power_screen("staff", [
        (powerful.IDENTIFY.key[-1], "鑑定", current, 14, 20),
        (powerful.UNCURSE.key[-1], "解呪", current, 14, 20)])


class MagicEaterPowerfulActivationTest(executor_harness.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        d25.MagicEaterTownStops2RecordedTest.setUpClass()
        cls.cases = d25.MagicEaterTownStops2RecordedTest.cases

    def board(self, *, level=20, hp=None, effects=(powerful.IDENTIFY, powerful.UNCURSE),
              store=None, worn=None):
        policy, raw = d25.MagicEaterTownStops2RecordedTest.boundary(self, LIFE)
        record = me_staff_sequence.state(policy)
        # The record holds the displayed list's staffs (an absorbed power is
        # always listed, cmd-magiceat.cpp): the stage staffs and, among the
        # two effects, only those the case lists.
        listed = {effect.sval for effect in effects}
        record.absorbed = {sval: 1 for sval in me_staff_sequence.SEQUENCE_SVALS
                           if sval not in BY_SVAL_EFFECT or sval in listed}
        raw = copy.deepcopy(raw)
        raw["store"] = store
        raw["player"]["level"] = raw["player"]["max_level"] = level
        if hp is not None:
            raw["player"]["hp"] = hp
        raw["_magic_eater_power_list"] = staff_list(effects)
        sword = next(item for item in raw["equipment"] if item["slot"] == "main_hand")
        sword.update(worn or {})
        policy.consume_skill_knowledge({
            "player": {"level": level},
            "knowledge": {"skills": [{"id": 1, "exp": 0}, {"id": 3, "exp": 0}]},
        })
        return policy, raw

    def choose(self, policy, raw):
        raw["turn"] += 1
        return policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge))

    def post(self, policy, raw, key, screens, following):
        game = FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = command_screen(raw["turn"])
        game.screens = [*screens, command_screen(following["turn"])]
        game.states = [copy.deepcopy(following) for _ in game.screens]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        self.assertEqual(port(key, decision={"reason": policy.last_reason,
                                            "sequence": policy._decision_sequence}),
                         SendResult.SENT, port.last_result.reason)
        return game, port.last_result.board

    @staticmethod
    def advanced(raw, **sword):
        following = copy.deepcopy(raw)
        following["turn"] += 10
        next(item for item in following["equipment"] if item["slot"] == "main_hand").update(sword)
        return following

    def test_cursed_worn_item_uses_powerful_remove_curse(self):
        policy, raw = self.board(worn={"is_cursed": True})
        key = self.choose(policy, raw)
        self.assertEqual((key, policy.last_reason), ("UAg", "me-powerful:uncurse"))
        game, board = self.post(policy, raw, key, [
            racial_screen(20, listed=False), racial_screen(20), prompt(TYPE_PROMPT),
            staff_powers()], self.advanced(raw, is_cursed=False))
        self.assertEqual(game.accepted, ["U", "*", "b", "A", "g"])
        key = self.choose(policy, board)
        self.assertFalse(policy.last_reason.startswith("me-powerful:"), (key, policy.last_reason))

    def test_a_curse_that_stays_is_permanent_and_not_retried(self):
        policy, raw = self.board(worn={"is_cursed": True})
        key = self.choose(policy, raw)
        _, board = self.post(policy, raw, key, [
            racial_screen(20), prompt(TYPE_PROMPT), staff_powers()], self.advanced(raw))
        key = self.choose(policy, board)
        sword = next(item for item in parse_snapshot(board, policy._monrace_knowledge).equipment
                     if item.slot == "main_hand")
        self.assertIn(policy._item_signature(sword), policy._permanent_cursed_items)
        self.assertNotEqual(policy.last_reason, "me-powerful:uncurse", key)

    def test_known_ego_worn_item_uses_powerful_identify(self):
        policy, raw = self.board(worn={"is_ego": True, "known": True, "fully_known": False})
        key = self.choose(policy, raw)
        self.assertEqual((key, policy.last_reason), ("UAf/a", "me-powerful:identify"))
        game, board = self.post(policy, raw, key, [
            racial_screen(20), prompt(TYPE_PROMPT), staff_powers(),
            prompt(FULL_IDENTIFY_PROMPT, "item", area="inventory", areas=["inventory", "equipment"],
                   menu=False, first_label="a", last_label="m"),
            prompt(FULL_IDENTIFY_PROMPT, "item", area="equipment", areas=["inventory", "equipment"],
                   menu=False, first_label="a", last_label="h"),
            source_derived_identify_viewer(), source_derived_identify_viewer(final=True)],
            self.advanced(raw, is_ego=True, known=True, fully_known=True))
        self.assertEqual(game.accepted, ["U", "b", "A", "f", "/", "a", " ", "\x1b"])
        key = self.choose(policy, board)
        self.assertFalse(policy.last_reason.startswith("me-powerful:"), (key, policy.last_reason))

    def test_an_empty_power_is_cancelled_without_cost(self):
        policy, raw = self.board(worn={"is_cursed": True})
        key = self.choose(policy, raw)
        game, board = self.post(policy, raw, key, [
            racial_screen(20), prompt(TYPE_PROMPT), staff_powers(current=0)], self.advanced(raw))
        self.assertEqual(game.accepted, ["U", "b", "A", "\x1b"])
        # The displayed empty list serves nothing until it regenerates.
        key = self.choose(policy, board)
        self.assertNotEqual(policy.last_reason, "me-powerful:uncurse", key)

    def test_hit_points_at_or_below_the_cost_rest_first(self):
        # A Magic-Eater has no mana: the cost (15 at level 20) is paid in HP.
        # DECLARED CONSTRUCTED: max HP one above the cost (a recorded low
        # HP ratio is the survival rung's town:seek-shelter instead).
        policy, raw = self.board(hp=powerful.cost(20), worn={"is_cursed": True})
        raw["player"]["max_hp"] = powerful.cost(20) + 1
        self.choose(policy, raw)  # the drop from the primed HP is a hit: shelter first
        key = self.choose(policy, raw)
        self.assertEqual((key, policy.last_reason), (REST_MACRO, "me-powerful:recover-hp"))

    def test_below_level_10_the_power_waits(self):
        policy, raw = self.board(level=9, worn={"is_cursed": True})
        key = self.choose(policy, raw)
        self.assertFalse(policy.last_reason.startswith("me-powerful:"), (key, policy.last_reason))

    def test_worn_full_identification_is_not_requested_once_absorbed(self):
        # Below level 10 the power waits; the equipped-identification owner
        # no longer asks for an *Identify* source to buy.
        for effects, requested in (((powerful.UNCURSE,), True),
                                   ((powerful.IDENTIFY, powerful.UNCURSE), False)):
            with self.subTest(absorbed=[effect.name for effect in effects]):
                policy, raw = self.board(level=9, effects=effects,
                                         worn={"is_ego": True, "known": True, "fully_known": False})
                # DECLARED CONSTRUCTED: the staff sequence's town work silent.
                # Without the Identify staff absorbed, stage 1 is unfinished and
                # its errand would take the board before any identification.
                with mock.patch.object(me_staff_sequence, "town_key", return_value=None):
                    for _ in range(3):
                        key = self.choose(policy, raw)
                        self.assertFalse(policy.last_reason.startswith("me-powerful:"), key)
                self.assertEqual(policy._identification_need == "full", requested,
                                 (key, policy.last_reason))

    def shop(self, store_type, sval, name):
        page = copy.deepcopy(self.cases[LIFE]["board"]["store"])
        ware = dict(page["items"][0], tval=TVAL_SCROLL, sval=sval, name=name, count=3,
                    price=500, letter="a")
        return dict(page, store_type=store_type, items=[ware])

    def test_star_remove_curse_is_never_bought_once_absorbed(self):
        # The store decision (_next_purchase, asked by choose_key in a store)
        # picks the heavy-curse scroll only while the power is not absorbed.
        for effects, bought in (((powerful.IDENTIFY,), True),
                                ((powerful.IDENTIFY, powerful.UNCURSE), False)):
            with self.subTest(absorbed=[effect.name for effect in effects]):
                policy, raw = self.board(
                    store=self.shop(STORE_TEMPLE, SV_SCROLL_STAR_REMOVE_CURSE, "*解呪*の巻物"),
                    effects=effects, worn={"is_cursed": True})
                raw["player"]["gold"] = 20000
                board = parse_snapshot(raw, policy._monrace_knowledge)
                sword = next(item for item in board.equipment if item.slot == "main_hand")
                policy._heavy_cursed_items.add(policy._item_signature(sword))
                key = self.choose(policy, raw)
                self.assertNotEqual(policy.last_reason, "shop:buy-star-remove-curse", key)
                ware = policy._next_purchase(parse_snapshot(raw, policy._monrace_knowledge))
                self.assertEqual(ware is not None and ware.sval == SV_SCROLL_STAR_REMOVE_CURSE,
                                 bought, ware)
                self.assertEqual(policy._required_remove_curse_kind(board) is not None, bought)
                self.assertEqual(policy._affordable_star_remove_curse(board) is not None, bought)
                # DECLARED CONSTRUCTED: none at Home and recall scrolls in hand,
                # the reserve's other conditions.
                policy._home_star_remove_curse_count = 0
                # Owner 2026-11-02 21h: the reserve is bought over the table
                # (consumable_policy.RESERVES) until the power is absorbed.
                with mock.patch.object(policy, "_recall_departure_shortage", return_value=False):
                    self.assertEqual(policy._star_remove_curse_reserve_purchase_needed(board), bought)

    def test_the_store_never_offers_a_replaced_scroll(self):
        # The store's candidate list drops the replaced scroll even for a
        # requester outside the curse and identification gates.
        # DECLARED CONSTRUCTED: such a requester, as a heavy-curse need.
        policy, raw = self.board(
            store=self.shop(STORE_TEMPLE, SV_SCROLL_STAR_REMOVE_CURSE, "*解呪*の巻物"),
            worn={"is_cursed": True})
        raw["player"]["gold"] = 20000
        self.choose(policy, raw)
        board = parse_snapshot(raw, policy._monrace_knowledge)
        with mock.patch.object(policy, "_required_remove_curse_kind",
                               return_value="star-remove-curse"),                 mock.patch.object(policy, "_usable_remove_curse_scroll", return_value=None),                 mock.patch.object(policy, "_home_remove_curse_scroll", return_value=None):
            self.assertIsNone(policy._next_purchase(board))

    def test_star_identify_is_never_bought_once_absorbed(self):
        # The purchase ladder (_purchase_rungs) names a full identification
        # need's *Identify* only while the power is not absorbed.
        for effects, bought in (((powerful.UNCURSE,), True),
                                ((powerful.IDENTIFY, powerful.UNCURSE), False)):
            with self.subTest(absorbed=[effect.name for effect in effects]):
                policy, raw = self.board(
                    store=self.shop(STORE_ALCHEMIST, SV_SCROLL_STAR_IDENTIFY, "*鑑定*の巻物"),
                    effects=effects)
                raw["player"]["gold"] = 20000
                self.choose(policy, raw)
                policy._identification_need = "full"
                board = parse_snapshot(raw, policy._monrace_knowledge)
                rungs = [match.rung_id for match in
                         policy._matching_live_purchase_rungs(board, board.store.items[0])]
                self.assertEqual(rungs == ["identify:full"], bought, rungs)
                # DECLARED CONSTRUCTED: no fundraising run (the recorded
                # life-033 run buys only its own kit).
                policy._fundraising_mode = None
                ware = policy._next_purchase(board)
                self.assertEqual(ware is not None and ware.sval == SV_SCROLL_STAR_IDENTIFY,
                                 bought, ware)

    def test_replaced_scrolls_are_named_by_the_table(self):
        policy, raw = self.board()
        self.choose(policy, raw)
        board = parse_snapshot(raw, policy._monrace_knowledge)
        for effect in powerful.EFFECTS:
            self.assertTrue(me_capability.has(policy, board, effect.kind, effect.sval))
        replaced = {row.replaces.sval for row in me_capability.REPLACES
                    if isinstance(row.replaces, me_capability.Kind)
                    and row.replaces.tval == TVAL_SCROLL
                    and row.power in {(effect.kind, effect.sval) for effect in powerful.EFFECTS}}
        self.assertEqual(replaced, {SV_SCROLL_STAR_IDENTIFY, SV_SCROLL_STAR_REMOVE_CURSE})
        for sval in replaced:
            for use in (me_capability.PURCHASE, me_capability.CANDIDATE, me_capability.NEED):
                self.assertTrue(me_capability.replaced_by_absorbed(
                    policy, board, (TVAL_SCROLL, sval), use))


if __name__ == "__main__":
    import unittest
    unittest.main()
