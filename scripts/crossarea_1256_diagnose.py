"""Print the pre-decision fundraising facts at town replay index 1256."""

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tests  # noqa: F401
from hengbot.policy import HengbotPolicy
from hengbot.policy_fundraising import fundraising_run_verdict
from test_town_approach_retired_recorded import TownApproachRetiredRecordedTest


class ReachedTarget(Exception):
    pass


def inspect(mode):
    fixture = TownApproachRetiredRecordedTest
    fixture.setUpClass()
    fixture.replay = None
    original_init = HengbotPolicy.__init__
    original_choose = HengbotPolicy.choose_key
    calls = 0
    result = None

    def init(policy, *args, **kwargs):
        original_init(policy, *args, **kwargs)
        policy._crossarea_fundraising_enforced = mode == "on"

    def choose(policy, snapshot):
        nonlocal calls, result
        index = calls
        calls += 1
        if index != 1256:
            return original_choose(policy, snapshot)
        facts = policy._fundraising_facts(snapshot)
        purpose = policy._fundraising_run_purpose
        record = policy._fundraising_purpose_record
        verdict = fundraising_run_verdict(facts, purpose)
        result = {
            "mode": mode, "index": index,
            "decision_sequence_before": policy._decision_sequence,
            "food_state": snapshot.player.food_state,
            "food_type": snapshot.player.food_type,
            "carried_edible": repr(policy._find_edible(snapshot)),
            "home_edible": repr(policy._home_mana_food_candidate()),
            "home_knowledge_current": policy._home_knowledge_current,
            "shop_food_seen": policy._fundraising_affordable_food_seen,
            "store_attempted": dict(policy._town_store_attempted),
            "gold": snapshot.player.gold,
            "inventory_count": len(snapshot.inventory),
            "purpose": repr(purpose), "record": repr(record),
            "runs_started": policy._fundraising_runs_started,
            "fundraising_mode": policy._fundraising_mode,
            "known_treasure_count": len(policy._known_treasure),
            "facts": vars(facts), "verdict": vars(verdict),
            "legacy_no_food_left": policy._find_edible(snapshot) is None
            and snapshot.player.food_state not in {"full", "gorged"},
            "returning_to_town": policy._returning_to_town,
            "expedition_light_ready": policy._expedition_light_ready(snapshot),
            "floor_key": snapshot.floor_key,
        }
        result["key"] = original_choose(policy, snapshot)
        result["reason"] = policy.last_reason
        result["return_trigger_after"] = policy._last_return_trigger
        raise ReachedTarget

    HengbotPolicy.__init__ = init
    HengbotPolicy.choose_key = choose
    try:
        fixture._replay()
    except ReachedTarget:
        pass
    finally:
        HengbotPolicy.__init__ = original_init
        HengbotPolicy.choose_key = original_choose
    if result is None:
        raise AssertionError(f"{mode}: replay did not reach 1256")
    return result


if __name__ == "__main__":
    for mode in ("off", "on"):
        print(json.dumps(inspect(mode), ensure_ascii=False, default=str))
