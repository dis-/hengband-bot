# Calibration travel audit (base a4e51bf9)

| Branch | Base source | Declaration before fix |
| --- | --- | --- |
| deposit, away from Home | policy_calibration.py:1292-1298 | Generic route declaration only; missing calibration phase continuation. |
| deposit, Home entrance/open Home | policy_calibration.py:1282-1290 | Home composer declares its operation; preserve exact operation binding. |
| restore travel | policy_calibration.py:1472-1495 | calibration, home-reached, calibration.restore-supplies; preserves Home operation declarations. |
| restore excess deposit at Home | policy_calibration.py:1373-1399 | Home operation declaration or calibration restore-excess declaration. |
| restore excess, away from Home | policy_calibration.py:1400-1495 | Falls through restore knowledge/visit/travel, declared as above. |
| strip/equip session Home approach | policy_equipment.py:2240-2245,2133-2146 | calibration when session owned, home-reached, equipment.next-action. |

Recorded decisions: 4676 at 1722292 sends ESC `n(. with calibration:deposit-travel; 4677 at 1722384 returns no key, ownership:holder-silent:calibration. The generic declaration says arrive:45,123 / route.resume; it does not declare calibration.deposit. No checkpoint was captured; the pin must state its attachment wall and compare the first key before consuming its response.

No screen classification or modal code changes are needed. No new persistent attributes are planned. EXPECTED_FIRST remains untouched.
