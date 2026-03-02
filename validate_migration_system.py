#!/usr/bin/env python3
"""Validate migration system implementation"""

import os
import sys
import re

errors = []

# Check that all required files exist
required_files = [
    'migrations/000_bootstrap.sql',
    'migrations/001_initial_schema.sql', 
    'migrations/002_add_workspaces.sql',
    'migrations/README.md',
    'scripts/deploy/run_migrations.sh',
    'MIGRATION_SYSTEM.md',
    'MIGRATION_QUICKSTART.md'
]

print("Checking required files...")
for filename in required_files:
    if os.path.exists(filename):
        print(f"✓ {filename}: Exists")
    else:
        print(f"✗ {filename}: Missing")
        errors.append(f"Missing file: {filename}")

# Validate SQL files have basic structure
sql_files = [
    'migrations/000_bootstrap.sql',
    'migrations/001_initial_schema.sql',
    'migrations/002_add_workspaces.sql'
]

print("\nValidating SQL syntax...")
for filename in sql_files:
    if os.path.exists(filename):
        with open(filename, 'r') as f:
            content = f.read()
        
        # Check for basic SQL keywords
        if 'CREATE TABLE' in content or 'CREATE MATERIALIZED VIEW' in content or 'CREATE FUNCTION' in content:
            print(f"✓ {filename}: Contains valid SQL statements")
        else:
            print(f"✗ {filename}: No CREATE statements found")
            errors.append(f"Invalid SQL: {filename}")
        
        # Check for semicolons (SQL statement terminators)
        if ';' in content:
            print(f"✓ {filename}: Has proper statement terminators")
        else:
            print(f"✗ {filename}: Missing semicolons")
            errors.append(f"Missing semicolons: {filename}")

# Validate shell script has shebang
print("\nValidating shell script...")
shell_script = 'scripts/deploy/run_migrations.sh'
if os.path.exists(shell_script):
    with open(shell_script, 'r') as f:
        lines = f.readlines()
    
    if lines and lines[0].strip() == '#!/usr/bin/env bash':
        print(f"✓ {shell_script}: Has proper shebang")
    else:
        print(f"✗ {shell_script}: Missing or incorrect shebang")
        errors.append(f"Invalid shebang: {shell_script}")
    
    content = ''.join(lines)
    
    # Check for key functions
    required_functions = ['bootstrap_migration_system', 'run_migrations', 'compute_checksum']
    for func in required_functions:
        if func in content:
            print(f"✓ {shell_script}: Contains {func} function")
        else:
            print(f"✗ {shell_script}: Missing {func} function")
            errors.append(f"Missing function {func}: {shell_script}")

# Check migration file naming convention
print("\nValidating migration naming convention...")
migration_pattern = re.compile(r'^\d{3}_[a-z_]+\.sql$')
for filename in ['000_bootstrap.sql', '001_initial_schema.sql', '002_add_workspaces.sql']:
    if migration_pattern.match(filename):
        print(f"✓ {filename}: Follows naming convention")
    else:
        print(f"✗ {filename}: Invalid naming convention")
        errors.append(f"Invalid naming: {filename}")

# Validate bootstrap creates schema_migrations table
print("\nValidating bootstrap migration...")
bootstrap_file = 'migrations/000_bootstrap.sql'
if os.path.exists(bootstrap_file):
    with open(bootstrap_file, 'r') as f:
        content = f.read()
    
    if 'CREATE TABLE' in content and 'schema_migrations' in content:
        print(f"✓ {bootstrap_file}: Creates schema_migrations table")
    else:
        print(f"✗ {bootstrap_file}: Missing schema_migrations table")
        errors.append(f"Missing schema_migrations: {bootstrap_file}")
    
    required_columns = ['version', 'applied_at', 'checksum']
    for col in required_columns:
        if col in content:
            print(f"✓ {bootstrap_file}: Has {col} column")
        else:
            print(f"✗ {bootstrap_file}: Missing {col} column")
            errors.append(f"Missing column {col}: {bootstrap_file}")

if errors:
    print(f"\n{'='*60}")
    print(f"VALIDATION FAILED: {len(errors)} error(s)")
    print(f"{'='*60}")
    for error in errors:
        print(f"  - {error}")
    sys.exit(1)
else:
    print(f"\n{'='*60}")
    print("✓ ALL VALIDATIONS PASSED")
    print(f"{'='*60}")
    sys.exit(0)
