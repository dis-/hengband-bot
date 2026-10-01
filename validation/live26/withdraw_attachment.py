"""Authorized withdraw attachment: stop at first changed historical action."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from test_home_withdraw_failed_stock_present_recorded import HomeWithdrawFailedStockPresentRecordedTest as T
from hengbot.policy import HengbotPolicy

class End(Exception):
    pass

mode = sys.argv[1]
T.setUpClass()
original_init = HengbotPolicy.__init__
original_choose = HengbotPolicy.choose_key
rows = []
def init(self, *args, **kwargs):
    original_init(self, *args, **kwargs)
    self._town_claim_bar_enforced = mode == 's33'
def choose(self, snapshot):
    key = original_choose(self, snapshot)
    index = len(rows)
    historical = T.recorded[index]
    claim = self.decision_claim
    row = {'index': index, 'sequence': self._decision_sequence,
           'historical': [historical['key'], historical['reason']],
           'actual': [key, self.last_reason], 'claim': claim}
    rows.append(row)
    if row['historical'] != row['actual']:
        raise End()
    return key
HengbotPolicy.__init__ = init
HengbotPolicy.choose_key = choose
try:
    T._replay()
except End:
    pass
finally:
    HengbotPolicy.__init__ = original_init
    HengbotPolicy.choose_key = original_choose
print(json.dumps({'case': 'withdraw', 'mode': mode, 'measured_rows': len(rows),
                  'first_changed_action': rows[-1],
                  'note': 'No board after the first changed action was consumed.'}, default=str))
