#!/usr/bin/env python3
"""
Fix import statements from src.models.* to src.database.models
"""

import os
import re
from pathlib import Path

def fix_imports_in_file(file_path):
    """Fix imports in a single file"""
    try:
        content = file_path.read_text()
        original_content = content
        
        # Fix imports
        patterns = [
            (r'from src\.models\.video import Video\nfrom src\.models\.artist import Artist', 
             'from src.database.models import Video, Artist'),
            (r'from src\.models\.video import Video', 
             'from src.database.models import Video'),
            (r'from src\.models\.artist import Artist', 
             'from src.database.models import Artist'),
            (r'from src\.database import get_async_session, get_engine', 
             'from src.database.async_connection import get_async_session, get_engine'),
            (r'from src\.database import get_async_session', 
             'from src.database.async_connection import get_async_session'),
        ]
        
        for pattern, replacement in patterns:
            content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
        
        if content != original_content:
            file_path.write_text(content)
            print(f"Fixed imports in: {file_path}")
            return True
        
        return False
        
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return False

def main():
    """Fix all import issues"""
    src_dir = Path("src")
    
    if not src_dir.exists():
        print("src directory not found")
        return
    
    files_fixed = 0
    
    # Find all Python files in src directory
    for py_file in src_dir.rglob("*.py"):
        if fix_imports_in_file(py_file):
            files_fixed += 1
    
    print(f"Fixed imports in {files_fixed} files")

if __name__ == "__main__":
    main()