#!/usr/bin/env python3
"""Validate syntax of backup system Python files"""

import ast
import sys

files = [
    'backup_service.py',
    'restore_backup.py', 
    'validate_data_integrity.py'
]

errors = []

for filename in files:
    try:
        with open(filename, 'r') as f:
            code = f.read()
        ast.parse(code)
        print(f"✓ {filename}: Syntax OK")
    except SyntaxError as e:
        print(f"✗ {filename}: Syntax Error - {e}")
        errors.append(filename)
    except Exception as e:
        print(f"✗ {filename}: Error - {e}")
        errors.append(filename)

if errors:
    print(f"\nFailed files: {', '.join(errors)}")
    sys.exit(1)
else:
    print("\n✓ All files passed syntax validation")
    sys.exit(0)
