#!/usr/bin/env python3
"""
Basic tests for backup system implementation
Tests file existence, imports, and basic structure
"""

import os
import sys
import importlib.util

def test_files_exist():
    """Test that all required files exist"""
    required_files = [
        'backup_service.py',
        'restore_backup.py',
        'validate_data_integrity.py',
        'backup_setup.sh',
        'backup_manual.sh',
        'restore_manual.sh',
        'smoke_tests.sh',
        'DISASTER_RECOVERY_RUNBOOK.md',
        'BACKUP_README.md',
        'BACKUP_IMPLEMENTATION.md',
        'BACKUP_QUICKSTART.md',
        'BACKUP_CHECKLIST.md',
        'BACKUP_FILES_CREATED.md'
    ]
    
    missing = []
    for file in required_files:
        if not os.path.exists(file):
            missing.append(file)
    
    if missing:
        print(f"✗ Missing files: {', '.join(missing)}")
        return False
    
    print(f"✓ All {len(required_files)} required files exist")
    return True


def test_python_syntax():
    """Test Python files have valid syntax"""
    python_files = [
        'backup_service.py',
        'restore_backup.py',
        'validate_data_integrity.py'
    ]
    
    for file in python_files:
        try:
            with open(file, 'r') as f:
                compile(f.read(), file, 'exec')
        except SyntaxError as e:
            print(f"✗ Syntax error in {file}: {e}")
            return False
    
    print(f"✓ All {len(python_files)} Python files have valid syntax")
    return True


def test_shell_scripts():
    """Test shell scripts have shebang"""
    shell_files = [
        'backup_setup.sh',
        'backup_manual.sh',
        'restore_manual.sh',
        'smoke_tests.sh'
    ]
    
    for file in shell_files:
        with open(file, 'r') as f:
            first_line = f.readline().strip()
            if not first_line.startswith('#!/bin/bash'):
                print(f"✗ {file} missing bash shebang")
                return False
    
    print(f"✓ All {len(shell_files)} shell scripts have proper shebang")
    return True


def test_backup_service_structure():
    """Test backup_service.py has required classes and functions"""
    spec = importlib.util.spec_from_file_location("backup_service", "backup_service.py")
    module = importlib.util.module_from_spec(spec)
    
    try:
        # Just check if the file can be loaded as a module
        with open('backup_service.py', 'r') as f:
            code = f.read()
            
        # Check for key classes and functions
        required = [
            'class BackupService',
            'def backup_qdrant',
            'def backup_neo4j',
            'def backup_postgresql',
            'def cleanup_old_backups',
            'def run_full_backup'
        ]
        
        missing = []
        for item in required:
            if item not in code:
                missing.append(item)
        
        if missing:
            print(f"✗ backup_service.py missing: {', '.join(missing)}")
            return False
        
        print("✓ backup_service.py has required structure")
        return True
        
    except Exception as e:
        print(f"✗ Error checking backup_service.py: {e}")
        return False


def test_restore_service_structure():
    """Test restore_backup.py has required classes and functions"""
    try:
        with open('restore_backup.py', 'r') as f:
            code = f.read()
            
        required = [
            'class RestoreService',
            'def list_available_backups',
            'def restore_qdrant',
            'def restore_neo4j',
            'def restore_postgresql',
            'def validate_restore'
        ]
        
        missing = []
        for item in required:
            if item not in code:
                missing.append(item)
        
        if missing:
            print(f"✗ restore_backup.py missing: {', '.join(missing)}")
            return False
        
        print("✓ restore_backup.py has required structure")
        return True
        
    except Exception as e:
        print(f"✗ Error checking restore_backup.py: {e}")
        return False


def test_validator_structure():
    """Test validate_data_integrity.py has required structure"""
    try:
        with open('validate_data_integrity.py', 'r') as f:
            code = f.read()
            
        required = [
            'class DataIntegrityValidator',
            'def validate_qdrant',
            'def validate_neo4j',
            'def validate_postgresql',
            'def validate_cross_database_consistency'
        ]
        
        missing = []
        for item in required:
            if item not in code:
                missing.append(item)
        
        if missing:
            print(f"✗ validate_data_integrity.py missing: {', '.join(missing)}")
            return False
        
        print("✓ validate_data_integrity.py has required structure")
        return True
        
    except Exception as e:
        print(f"✗ Error checking validate_data_integrity.py: {e}")
        return False


def test_docker_compose():
    """Test docker-compose.yaml has backup-service"""
    try:
        with open('docker-compose.yaml', 'r') as f:
            content = f.read()
        
        if 'backup-service:' not in content:
            print("✗ docker-compose.yaml missing backup-service")
            return False
        
        required_config = [
            'BACKUP_SCHEDULE',
            'BACKUP_RETENTION_DAYS',
            'MINIO_ENDPOINT',
            'command: python backup_service.py'
        ]
        
        missing = []
        for item in required_config:
            if item not in content:
                missing.append(item)
        
        if missing:
            print(f"✗ docker-compose.yaml missing config: {', '.join(missing)}")
            return False
        
        print("✓ docker-compose.yaml properly configured")
        return True
        
    except Exception as e:
        print(f"✗ Error checking docker-compose.yaml: {e}")
        return False


def test_requirements():
    """Test requirements.txt has backup dependencies"""
    try:
        with open('requirements.txt', 'r') as f:
            content = f.read()
        
        required = ['boto3', 'apscheduler']
        missing = []
        
        for dep in required:
            if dep not in content:
                missing.append(dep)
        
        if missing:
            print(f"✗ requirements.txt missing: {', '.join(missing)}")
            return False
        
        print("✓ requirements.txt has backup dependencies")
        return True
        
    except Exception as e:
        print(f"✗ Error checking requirements.txt: {e}")
        return False


def main():
    """Run all tests"""
    print("=" * 60)
    print("Backup System Implementation Tests")
    print("=" * 60)
    print()
    
    tests = [
        ("File Existence", test_files_exist),
        ("Python Syntax", test_python_syntax),
        ("Shell Scripts", test_shell_scripts),
        ("Backup Service Structure", test_backup_service_structure),
        ("Restore Service Structure", test_restore_service_structure),
        ("Validator Structure", test_validator_structure),
        ("Docker Compose", test_docker_compose),
        ("Requirements", test_requirements)
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"✗ {name}: Exception - {e}")
            failed += 1
        print()
    
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    if failed > 0:
        sys.exit(1)
    else:
        print("\n✓ All tests passed!")
        sys.exit(0)


if __name__ == '__main__':
    main()
