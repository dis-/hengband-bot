import ast, subprocess, sys, unittest, pathlib
sys.path.insert(0, str(pathlib.Path.cwd()))
import tests
import hengbot.policy_town as town
from hengbot.policy import HengbotPolicy
mode=sys.argv[1]
if mode=='registry':
    source=subprocess.check_output(['git','show','a4e51bf9:src/hengbot/policy_town.py']).decode('utf8')
    tree=ast.parse(source)
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='TownMixin')
    node=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='_town_need_registry')
    namespace=dict(vars(town))
    exec(compile(ast.Module(body=[node],type_ignores=[]),'<base-registry>','exec'),namespace)
    town.TownMixin._town_need_registry=namespace['_town_need_registry']
    target='tests.test_live32_shop_leave.Live32ShopLeaveTest.test_cached_registry_callbacks_follow_the_restored_policy'
elif mode=='posting':
    HengbotPolicy._release_rewritten_store_posting=lambda *args,**kwargs:None
    target='tests.test_posted_effect_unobserved.PostedEffectUnobservedTest.test_p1b_rewritten_store_key_releases_the_posting_it_armed'
else:
    raise ValueError(mode)
result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromName(target))
sys.exit(not result.wasSuccessful())
