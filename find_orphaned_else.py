#!/usr/bin/env python3
"""
Find truly orphaned else statements that cause syntax errors
"""
import re
from pathlib import Path

def find_orphaned_else():
    file_path = Path('frontend/templates/artist_detail.html')
    content = file_path.read_text()
    
    # Find the script block
    script_start = content.find('<script>')
    script_end = content.find('</script>')
    if script_start == -1 or script_end == -1:
        print("No script block found")
        return
        
    js_code = content[script_start+8:script_end]
    lines = js_code.split('\n')
    
    print(f"Analyzing {len(lines)} lines for orphaned else statements")
    
    # Look for the specific pattern that causes "expected expression, got keyword 'else'"
    # This happens when there's an else without a proper if/try block before it
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        # Look for lines that are ONLY "else" or "} else" without proper context
        if stripped == 'else' or stripped == 'else {':
            print(f"Found bare else at line {i+1}: '{stripped}'")
            
            # Show context
            for j in range(max(0, i-5), min(len(lines), i+6)):
                marker = '>>> ' if j == i else '    '
                print(f'{marker}JS Line {j+1}: {lines[j]}')
            print("---")
        
        # Look for malformed if-else structures
        if 'else' in stripped and not stripped.startswith('//'):
            # Check if this line has issues
            # Pattern: "} else" followed by something that's not "{"
            if re.match(r'^\s*}\s*else(?!\s*{)', stripped):
                print(f"Malformed else at line {i+1}: '{stripped}'")
                
                # Show context
                for j in range(max(0, i-3), min(len(lines), i+4)):
                    marker = '>>> ' if j == i else '    '
                    print(f'{marker}JS Line {j+1}: {lines[j]}')
                print("---")
    
    # Also check for unbalanced braces that might cause else to be orphaned
    print("\nChecking for brace balance issues...")
    brace_stack = []
    for i, line in enumerate(lines):
        for char in line:
            if char == '{':
                brace_stack.append((i+1, char))
            elif char == '}':
                if brace_stack:
                    brace_stack.pop()
                else:
                    print(f"Unmatched closing brace at line {i+1}")
    
    if brace_stack:
        print("Unmatched opening braces:")
        for line_num, char in brace_stack[-5:]:  # Show last 5
            print(f"  Line {line_num}")

if __name__ == "__main__":
    find_orphaned_else()