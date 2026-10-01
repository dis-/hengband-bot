import sys, pathlib, traceback, unittest
sys.path.insert(0,str(pathlib.Path.cwd()))
import tests
from hengbot.policy_town import TownMixin
original=TownMixin._town_need_registry
def trace(policy):
    if getattr(policy,'_town_need_specs',None) is None:
        print('FIRST REGISTRY MATERIALIZATION',file=sys.stderr)
        traceback.print_stack(limit=12)
    return original(policy)
TownMixin._town_need_registry=trace
unittest.main(module=None,argv=['trace','tests.test_live32_shop_leave.Live32ShopLeaveTest.test_historical_gate_stop_shadow_agrees_without_mutation'])
