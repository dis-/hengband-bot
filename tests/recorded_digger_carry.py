"""Declared wall: replay a recorded board under the spare gear rule before 2026-11-04.

Owner 2026-11-04 「使わない装備をキープしたまま...自宅に仕舞う」 and 「採掘に行かない
時はシャベルも仕舞う」 (spare_gear): these recordings carried unworn gear and a
non-surplus digger off duty, so their later rows and Home letters assume both
stayed in the pack.  A test whose subject is something else keeps its recorded
rows under this wall; tests/test_spare_gear_recorded.py pins the rule itself.
"""
from contextlib import contextmanager
from functools import wraps
from unittest.mock import patch

from hengbot import spare_gear


def _pre_rule_digger_needed(policy, snapshot, item):
    return bool(item.is_digging_tool and not policy._is_surplus_digging_tool(snapshot, item))


def _pre_rule_released(policy, snapshot, item):
    if not policy._spare_equipment_deposit_shape(item) or item.is_digging_tool or item.is_ammo:
        return False
    good = item.is_melee_weapon and item.known and (
        item.is_ego or item.is_artifact or item.to_h > 0 or item.to_d > 0 or item.pval > 0)
    return not good and (policy._target_loadout_known() or (
        snapshot is not None and policy._calibration_rejection is not None
        and policy._town_pack_space_shortage(snapshot)))


@contextmanager
def pre_digger_home_rule():
    with patch.object(spare_gear, "digger_needed", _pre_rule_digger_needed),             patch.object(spare_gear, "released", _pre_rule_released),             patch.object(spare_gear, "stow_pending", lambda _policy, _snapshot: False):
        yield


def install_for_module():
    """A module's setUpModule: the whole module replays recorded rows; returns the undo."""
    rule = pre_digger_home_rule()
    rule.__enter__()
    return lambda: rule.__exit__(None, None, None)


def pre_digger_home_replay(test):
    """Run one test method under ``pre_digger_home_rule``."""
    @wraps(test)
    def wrapper(*args, **kwargs):
        with pre_digger_home_rule():
            return test(*args, **kwargs)
    return wrapper
