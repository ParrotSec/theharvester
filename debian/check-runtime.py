#!/usr/bin/python3
"""Check only the application's dependency closure, not unrelated system packages."""

import argparse
import importlib.metadata as metadata
import json
from pathlib import Path
import sys

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    if sys.prefix == sys.base_prefix or not sys.flags.isolated:
        raise SystemExit('Run this check using the private venv Python with -I.')
    lock = json.loads(Path(__file__).with_name('vendor-lock.json').read_text())
    private = {'theharvester': lock['upstream']['version']}
    private.update({a['project']: a['version'] for a in lock['artifacts']})
    pending = [(Requirement(f'{name}=={version}'), True) for name, version in private.items()]
    seen = set()
    report = {}
    while pending:
        req, check_version = pending.pop()
        name = canonicalize_name(req.name)
        dist = metadata.distribution(name)
        # APT owns system-to-system version constraints. Debian metadata may
        # retain upstream upper bounds already relaxed by distro maintainers
        # (e.g. limits 4.4.1 asks for packaging<25, while Echo ships packaging 25).
        # Enforce every boundary from our private code to a dependency instead.
        if check_version and req.specifier and not req.specifier.contains(dist.version, prereleases=True):
            raise SystemExit(f'Unsatisfied requirement: {req}; installed {dist.version}')
        bundled = Path(dist.locate_file('')).resolve().is_relative_to(Path(sys.prefix).resolve())
        if bundled != (name in private):
            raise SystemExit(f'{name} is not from the expected {"private" if name in private else "system"} location')
        report[name] = {'version': dist.version, 'origin': 'private' if bundled else 'system'}
        key = (name, frozenset(req.extras))
        if key in seen:
            continue
        seen.add(key)
        for dependency in dist.requires or []:
            child = Requirement(dependency)
            if child.marker is None or any(child.marker.evaluate({'extra': extra}) for extra in ('', *req.extras)):
                pending.append((child, bundled))
    if args.report:
        args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(f'Checked {len(report)} runtime distributions; only {", ".join(sorted(private))} are private.')


if __name__ == '__main__':
    main()
