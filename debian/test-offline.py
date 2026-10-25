#!/usr/bin/python3
"""Run deterministic upstream tests against the installed private package."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parent.parent
# Explicit allowlist: the remaining upstream tests contact public services or
# need credentials. One security test also launches real DNS/engine queries.
TESTS = [
    'lib',
    'test_myparser.py',
    'test_hackertarget_apikey.py',
    'test_mojeek.py',
    'test_security.py',
    'discovery/test_api_endpoints.py',
    'discovery/test_baidusearch.py',
    'discovery/test_builtwith.py',
    'discovery/test_censys.py',
    'discovery/test_criminalip.py',
    'discovery/test_dymosearch.py',
    'discovery/test_rocketreach.py',
]


def main():
    import theHarvester

    if not Path(theHarvester.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()):
        raise SystemExit('Tests must import the installed private package, not the source checkout.')
    with tempfile.TemporaryDirectory(prefix='theharvester-tests-') as temp:
        root = Path(temp)
        for name in TESTS:
            src, dest = ROOT / 'tests' / name, root / 'tests' / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, dest)
            else:
                shutil.copy2(src, dest)
        shutil.copy2(ROOT / 'pyproject.toml', root / 'pyproject.toml')
        # A few upstream tests inspect relative source paths. Point them at the
        # installed code instead of silently skipping those checks.
        (root / 'theHarvester').symlink_to(Path(theHarvester.__file__).resolve().parent)
        env = os.environ.copy()
        env.update(HOME=temp, PYTEST_DISABLE_PLUGIN_AUTOLOAD='1', PYTHONDONTWRITEBYTECODE='1')
        subprocess.run([
            sys.executable, '-I', '-B', '-m', 'pytest', '-p', 'pytest_asyncio.plugin',
            '--import-mode=importlib', '-q', '-k', 'not test_error_responses_do_not_leak_internal_paths', 'tests',
        ], cwd=root, env=env, check=True)


if __name__ == '__main__':
    main()
