"""Single revert check: run the strengthened catalogue pin on pre-fix src."""
import io
from pathlib import Path
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory
ROOT = Path(__file__).resolve().parents[2]
with TemporaryDirectory(prefix='revert-source-', dir=ROOT / 'validation/live26') as raw:
    archive = subprocess.check_output(['git', 'archive', 'a4a33abc', 'src'], cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(archive)) as source:
        source.extractall(raw, filter='data')
    sys.path.insert(0, str(Path(raw) / 'src'))
    sys.path.insert(1, str(ROOT))
    import unittest
    from tests.test_live23_home_cycle import Live23HomeCycleTest
    suite = unittest.TestSuite([Live23HomeCycleTest(
        'test_recorded_entry_completes_catalogue_before_other_errand')])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if result.wasSuccessful():
        raise SystemExit('ERROR: revert did not break the strengthened pin')
    print('REVERT DETECTED: pre-fix source fails the OFF catalogue completion pin.')
