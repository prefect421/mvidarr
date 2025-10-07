#!/usr/bin/env python3
"""
Find and fix the specific JavaScript syntax error
"""
import re
from pathlib import Path

def fix_js_syntax():
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
    
    # The browser error is at line 177, character position around 5881
    # Let's examine line 177 specifically
    if len(lines) > 177:
        problem_line = lines[176]  # 0-indexed
        print(f"Line 177 content: {problem_line}")
        print(f"Line length: {len(problem_line)}")
        
        # Check character around position 5881 within this line
        # But this seems like total character count, so let's calculate differently
    
    # Calculate cumulative character positions
    char_count = 0
    for i, line in enumerate(lines):
        line_start = char_count
        line_end = char_count + len(line) + 1  # +1 for newline
        
        if line_start <= 5881 <= line_end:
            print(f"\nCharacter 5881 is on JavaScript line {i+1}")
            print(f"Character position within line: {5881 - line_start}")
            print(f"Line content: '{line}'")
            
            # Check the specific character at position 5881
            if 5881 - line_start < len(line):
                char_at_pos = line[5881 - line_start]
                print(f"Character at position 5881: '{char_at_pos}'")
                
                # Look for syntax issues around this position
                start_pos = max(0, 5881 - line_start - 20)
                end_pos = min(len(line), 5881 - line_start + 20)
                context = line[start_pos:end_pos]
                print(f"Context: '{context}'")
                
                # Look for common syntax errors
                if 'else' in context:
                    print("Found 'else' in context - checking for orphaned else")
                    
                # Show surrounding lines for more context
                for j in range(max(0, i-5), min(len(lines), i+6)):
                    marker = '>>> ' if j == i else '    '
                    print(f'{marker}JS Line {j+1}: {lines[j]}')
            break
        
        char_count = line_end
    
    # Look for specific patterns that could cause "expected expression, got keyword 'else'"
    print(f"\n=== Looking for problematic else patterns ===")
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        # Pattern: else without proper if structure
        if re.search(r'(?:^|\s)else\s*{', stripped):
            # Check if there's a proper if before this
            context_start = max(0, i-3)
            context_lines = lines[context_start:i+1]
            context_text = '\n'.join(context_lines)
            
            # Look for incomplete if structures
            if_matches = list(re.finditer(r'if\s*\([^)]*\)', context_text))
            brace_count = context_text.count('{') - context_text.count('}')
            
            if not if_matches or brace_count != 0:
                print(f"Potential issue at JS line {i+1}: {stripped}")
                for j in range(context_start, i+2):
                    if j < len(lines):
                        marker = '>>> ' if j == i else '    '
                        print(f"{marker}JS Line {j+1}: {lines[j]}")
                print("---")

if __name__ == "__main__":
    fix_js_syntax()