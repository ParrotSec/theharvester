#!/usr/bin/python3
"""Fetch pinned orig archives on the maintainer's machine, never during a build."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
import tempfile
import urllib.request


LOCK = Path(__file__).with_name('vendor-lock.json')


def verify(path, expected):
    with path.open('rb') as stream:
        actual = hashlib.file_digest(stream, 'sha256').hexdigest()
    if actual != expected:
        raise SystemExit(f'SHA256 mismatch for {path}: expected {expected}, got {actual}')


def download(url, path, expected):
    if path.exists():
        verify(path, expected)
        return
    print(f'Downloading {url}', flush=True)
    request = urllib.request.Request(url, headers={'User-Agent': 'Parrot-theHarvester-packaging'})
    partial = path.with_suffix(path.suffix + '.part')
    try:
        with urllib.request.urlopen(request, timeout=120) as src, partial.open('wb') as dest:
            shutil.copyfileobj(src, dest)
        verify(partial, expected)
        partial.replace(path)
    finally:
        partial.unlink(missing_ok=True)


def fetch(lock, output):
    output.mkdir(parents=True, exist_ok=True)
    upstream = lock['upstream']
    version = upstream['version']
    download(upstream['url'], output / f'theharvester_{version}.orig.tar.gz', upstream['sha256'])
    archive = output / f'theharvester_{version}.orig-vendor.tar.gz'
    # A stable tar/gzip header makes repeated preparations byte-identical.
    with tempfile.TemporaryDirectory(prefix='theharvester-vendor-') as temp:
        root = Path(temp)
        for artifact in lock['artifacts']:
            download(artifact['url'], root / artifact['filename'], artifact['sha256'])
        partial = archive.with_suffix('.gz.part')
        try:
            with partial.open('wb') as stream, gzip.GzipFile(filename='', fileobj=stream, mode='wb', mtime=0) as gz:
                with tarfile.open(fileobj=gz, mode='w', format=tarfile.GNU_FORMAT) as tar:
                    for path in sorted(root.iterdir()):
                        info = tar.gettarinfo(path, arcname=f'vendor/{path.name}')
                        info.uid = info.gid = info.mtime = 0
                        info.uname = info.gname = ''
                        info.mode = 0o644
                        with path.open('rb') as src:
                            tar.addfile(info, src)
            if archive.exists():
                verify(partial, hashlib.sha256(archive.read_bytes()).hexdigest())
                partial.unlink()
            else:
                partial.replace(archive)
        finally:
            partial.unlink(missing_ok=True)
    print(f'Ready: {archive}\nImport both orig components with gbp; see debian/README.source.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['fetch', 'verify'])
    parser.add_argument('--output-dir', type=Path, default=Path('..'))
    parser.add_argument('--vendor-dir', type=Path, default=Path('vendor'))
    args = parser.parse_args()
    lock = json.loads(LOCK.read_text())
    if args.action == 'fetch':
        fetch(lock, args.output_dir)
    else:
        for artifact in lock['artifacts']:
            path = args.vendor_dir / artifact['filename']
            if not path.is_file():
                raise SystemExit(f'Missing {path}; import the vendor orig component (see debian/README.source).')
            verify(path, artifact['sha256'])
        print('All vendor artifacts match debian/vendor-lock.json.')


if __name__ == '__main__':
    main()
