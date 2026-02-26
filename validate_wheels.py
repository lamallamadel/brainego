#!/usr/bin/env python3
"""
Pre-commit validator: Check requirements vs wheelhouse.
Run this before pushing to ensure all deps are available offline.

Usage:
  python validate_wheels.py [--fix]
  
Options:
  --fix    Print pip download commands for missing wheels
"""

import re
import sys
from pathlib import Path

def validate_wheels():
    """Validate requirements exist in wheelhouse."""
    
    # Parse requirements-test.txt
    reqs = {}
    try:
        with open('requirements-test.txt', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    match = re.match(r'([a-zA-Z0-9_-]+)', line)
                    if match:
                        pkg_name = match.group(1).lower().replace('_', '-')
                        reqs[pkg_name] = line
    except FileNotFoundError:
        print('[ERROR] requirements-test.txt not found')
        return False

    # Get wheels
    wheelhouse = Path('vendor/wheels')
    if not wheelhouse.exists():
        print('[ERROR] vendor/wheels/ directory not found')
        return False

    wheels = set()
    for wheel in wheelhouse.glob('*.whl'):
        wheel_name = wheel.stem.split('-')[0].lower().replace('_', '-')
        wheels.add(wheel_name)

    print(f'[INFO] Checking {len(reqs)} requirements against {len(wheels)} wheels')
    print()

    # Find missing
    missing = [pkg for pkg in reqs if pkg not in wheels]

    if missing:
        print('[ERROR] Missing wheels for:')
        for pkg in sorted(missing):
            print(f'  - {reqs[pkg]}')
        print()
        
        if '--fix' in sys.argv:
            print('[FIX] Download commands:')
            for pkg in sorted(missing):
                base_pkg = reqs[pkg].split('>')[0].split('=')[0].split('<')[0].strip()
                print(f'  python -m pip download -d vendor/wheels {base_pkg}')
            print()
            print('Then commit: git add vendor/wheels requirements-test.txt && git commit')
        
        return False
    else:
        print('[OK] All 14 requirements found in wheelhouse!')
        print()
        print('Packages:')
        for pkg in sorted(reqs.keys()):
            print(f'  [OK] {pkg}')
        return True

if __name__ == '__main__':
    success = validate_wheels()
    sys.exit(0 if success else 1)
