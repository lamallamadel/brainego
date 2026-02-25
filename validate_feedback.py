#!/usr/bin/env python3
"""Quick validation of feedback implementation."""

import sys

print("Validating feedback collection implementation...")
print("=" * 60)

# Test 1: Check if feedback_service.py compiles
print("\n1. Checking feedback_service.py syntax...")
try:
    import py_compile
    py_compile.compile('feedback_service.py', doraise=True)
    print("   ✓ feedback_service.py syntax valid")
except Exception as e:
    print(f"   ✗ Syntax error in feedback_service.py: {e}")
    sys.exit(1)

# Test 2: Check if api_server.py compiles
print("\n2. Checking api_server.py syntax...")
try:
    import py_compile
    py_compile.compile('api_server.py', doraise=True)
    print("   ✓ api_server.py syntax valid")
except Exception as e:
    print(f"   ✗ Syntax error in api_server.py: {e}")
    sys.exit(1)

# Test 3: Check if test files compile
print("\n3. Checking test files syntax...")
try:
    import py_compile
    py_compile.compile('test_feedback.py', doraise=True)
    py_compile.compile('export_weekly_finetuning.py', doraise=True)
    py_compile.compile('feedback_dashboard.py', doraise=True)
    print("   ✓ All test/utility files syntax valid")
except Exception as e:
    print(f"   ✗ Syntax error in test files: {e}")
    sys.exit(1)

# Test 4: Check SQL file exists
print("\n4. Checking database initialization...")
import os
if os.path.exists('init-scripts/postgres/init.sql'):
    print("   ✓ init-scripts/postgres/init.sql exists")
else:
    print("   ✗ init-scripts/postgres/init.sql not found")
    sys.exit(1)

# Test 5: Check documentation
print("\n5. Checking documentation...")
docs = [
    'FEEDBACK_README.md',
    'FEEDBACK_IMPLEMENTATION.md',
    'FEEDBACK_QUICKSTART.md'
]
for doc in docs:
    if os.path.exists(doc):
        print(f"   ✓ {doc} exists")
    else:
        print(f"   ✗ {doc} not found")
        sys.exit(1)

print("\n" + "=" * 60)
print("✓ All validation checks passed!")
print("=" * 60)
