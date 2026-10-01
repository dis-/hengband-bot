import sys,pathlib,subprocess,unittest
sys.path.insert(0,str(pathlib.Path.cwd()))
import tests
module=__import__('tests.'+sys.argv[1],fromlist=['*'])
source=subprocess.check_output(['git','show','a4e51bf9:tests/'+sys.argv[1]+'.py']).decode('utf8')
exec(compile(source,module.__file__,'exec'),vars(module))
result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromName('tests.'+sys.argv[1]+'.'+sys.argv[2]))
sys.exit(not result.wasSuccessful())
