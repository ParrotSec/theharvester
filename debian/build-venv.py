#!/usr/bin/python3
"""Assemble an offline, relocatable private venv using the distro interpreter."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parent.parent
PREFIX = Path('/usr/lib/theharvester/venv')


def run(*args, **kwargs):
    subprocess.run([str(arg) for arg in args], check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destdir', type=Path, default=ROOT / 'debian/theharvester')
    args = parser.parse_args()
    lock = json.loads((ROOT / 'debian/vendor-lock.json').read_text())
    python_version = f'{sys.version_info.major}.{sys.version_info.minor}'
    if python_version != lock['python']:
        raise SystemExit(f'This vendor set requires distro Python {lock["python"]}; regenerate it for a Python transition.')
    # Refuse to silently ship the old checkout under a new Debian version.
    version_line = f"__version__ = '{lock['upstream']['version']}'"
    if version_line not in (ROOT / 'theHarvester/__init__.py').read_text():
        raise SystemExit('Import the locked upstream release with gbp first; see debian/README.source.')
    arch = subprocess.check_output(['dpkg-architecture', '-qDEB_HOST_ARCH'], text=True).strip()
    build_arch = subprocess.check_output(['dpkg-architecture', '-qDEB_BUILD_ARCH'], text=True).strip()
    if arch not in ('amd64', 'arm64') or arch != build_arch:
        raise SystemExit('Build natively on amd64 or arm64; cross-building this venv is not supported.')
    run(sys.executable, ROOT / 'debian/vendor.py', 'verify', '--vendor-dir', ROOT / 'vendor')

    destdir = args.destdir.resolve()
    venv = destdir / PREFIX.relative_to('/')
    if venv.exists():
        shutil.rmtree(venv)
    # Use a minor-version-specific symlink, never a copied Python executable.
    interpreter = Path(f'/usr/bin/python{python_version}')
    run(interpreter, '-m', 'venv', '--without-pip', '--system-site-packages', venv)
    python = venv / 'bin/python'
    env = {key: value for key, value in os.environ.items() if not key.startswith(('PIP_', 'PYTHON'))}
    env.update(PIP_CONFIG_FILE='/dev/null', PIP_NO_INDEX='1', PIP_DISABLE_PIP_VERSION_CHECK='1',
               PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1', FLIT_ROOT_INSTALL='1')
    pip = [interpreter, '-m', 'pip', '--python', python, 'install', '--no-index', '--no-deps',
           '--no-build-isolation', '--no-cache-dir', '--no-compile', '--ignore-installed']
    wheels = [a for a in lock['artifacts'] if a['architecture'] in ('all', arch)]
    with tempfile.TemporaryDirectory(prefix='theharvester-build-') as temp:
        requirements = Path(temp) / 'requirements.txt'
        requirements.write_text(''.join(
            f'{(ROOT / "vendor" / a["filename"]).as_uri()} --hash=sha256:{a["sha256"]}\n' for a in wheels
        ))
        run(*pip, '--require-hashes', '--only-binary=:all:', '-r', requirements, env=env)
        run(*pip, ROOT, env=env)

    site = venv / f'lib/python{python_version}/site-packages'
    # The Playwright driver is JavaScript. Use distro Node, not the wheel's ELF.
    node = site / 'playwright/driver/node'
    node.unlink()
    node.symlink_to('/usr/bin/node')
    # No pip, activation scripts or third-party entry points need to be public.
    # Our two entry points are invoked explicitly with the venv interpreter.
    for path in (venv / 'bin').iterdir():
        if path.name in ('theHarvester', 'restfulHarvest'):
            lines = path.read_text().splitlines(keepends=True)
            lines[0] = f'#!{PREFIX}/bin/python\n'
            path.write_text(''.join(lines))
        elif path.name not in ('python', 'python3', f'python{python_version}'):
            path.unlink()
    (venv / 'pyvenv.cfg').write_text(
        f'home = /usr/bin\ninclude-system-site-packages = true\n'
        f'version = {python_version}\nexecutable = {interpreter}\n'
    )
    # These describe temporary build paths and are not useful in a .deb.
    for path in site.glob('*.dist-info/direct_url.json'):
        path.unlink()
    for path in venv.rglob('__pycache__'):
        shutil.rmtree(path)

    doc = destdir / 'usr/share/doc/theharvester'
    doc.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / 'debian/vendor-lock.json', doc)
    # Preserve all upstream notices, including Playwright's bundled JS notices.
    for path in site.rglob('*'):
        if path.is_file() and any(word in path.name.upper() for word in ('LICENSE', 'COPYING', 'NOTICE')):
            target = doc / 'vendor-licenses' / path.relative_to(site)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    with tempfile.TemporaryDirectory(prefix='theharvester-check-') as temp:
        env['HOME'] = temp
        run(python, '-I', '-B', ROOT / 'debian/check-runtime.py', '--report', doc / 'runtime-versions.json', env=env, cwd=temp)
        run(python, '-I', '-B', venv / 'bin/theHarvester', '--help', env=env, cwd=temp)
        run(python, '-I', '-B', venv / 'bin/restfulHarvest', '--help', env=env, cwd=temp)
        # Starts the JS driver but does not launch or download a browser.
        run(python, '-I', '-B', '-m', 'playwright', '--version', env=env, cwd=temp)
        profiles = os.environ.get('DEB_BUILD_PROFILES', '').split()
        options = os.environ.get('DEB_BUILD_OPTIONS', '').split()
        if 'nocheck' not in profiles + options:
            run(python, '-I', '-B', ROOT / 'debian/test-offline.py', env=env, cwd=temp)
    # Also cover subprocesses that did not inherit -B. Never ship bytecode with
    # temporary build-directory paths embedded in it.
    for path in venv.rglob('__pycache__'):
        shutil.rmtree(path)


if __name__ == '__main__':
    main()
