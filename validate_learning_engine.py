#!/usr/bin/env python3
"""Validate learning engine files"""

import sys
import ast

def validate_python_syntax(file_path):
    """Validate Python file syntax"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            ast.parse(f.read())
        print(f"✓ {file_path} - Valid Python syntax")
        return True
    except SyntaxError as e:
        print(f"✗ {file_path} - Syntax error: {e}")
        return False
    except Exception as e:
        print(f"✗ {file_path} - Error: {e}")
        return False

def main():
    """Main validation"""
    results = []
    
    # Validate Python files
    python_files = [
        'learning_engine_service.py',
        'learning_engine_cli.py',
        'test_learning_engine.py',
        'learning_engine/__init__.py',
        'learning_engine/fisher.py',
        'learning_engine/trainer.py',
        'learning_engine/storage.py',
        'learning_engine/scheduler.py',
        'learning_engine/data_loader.py',
    ]
    
    for file_path in python_files:
        results.append(validate_python_syntax(file_path))
    
    if all(results):
        print(f"\n✓ All {len(results)} files validated successfully")
        sys.exit(0)
    else:
        failed = len([r for r in results if not r])
        print(f"\n✗ {failed} validation(s) failed")
        sys.exit(1)

if __name__ == '__main__':
    main()
