"""The ordinary use of the absorbed attack powers alone (Powerful Activation not payable).

Owner 2026-11-19 「魔道具術師の遠距離攻撃の選択肢に協力発動も入れたい」 and 「3つとも広げる」: while
me_powerful_activation.pays_safely holds, every chooser of an absorbed attack power also weighs
it cast through Powerful Activation (me_device_attacks.attack_uses).  A test written for the
ordinary use's rule (its key ``m``..., its radius 2, its figure) declares that condition with
``ORDINARY_ONLY``: DECLARED CONSTRUCTED, the HP the cost would take is not there to pay
(``powerful_ready`` False).  The powerful decision on the same boards is pinned by
tests/test_me_powerful_wider_1119.py.
"""
from unittest.mock import patch

from hengbot import me_device_attacks

ORDINARY_ONLY = patch.object(me_device_attacks, "powerful_ready", lambda *_args: False)
