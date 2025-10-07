#!/usr/bin/env python3
"""
Find the missing closing parenthesis in the JavaScript
"""
import re
from pathlib import Path

def find_missing_parenthesis():
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
    
    print(f"Finding missing parenthesis in {len(lines)} lines")
    
    # Track parentheses balance line by line
    paren_balance = 0
    issues = []
    
    for i, line in enumerate(lines):
        line_num = i + 1
        line_open = line.count('(')
        line_close = line.count(')')
        
        paren_balance += line_open - line_close
        
        # Look for lines where balance goes negative (too many closing)
        # or lines with suspicious patterns
        if paren_balance < 0:
            issues.append((line_num, paren_balance, line.strip()))
        
        # Also check for common problematic patterns
        if line_open > 0 and line_close == 0 and line.strip().endswith(','):
            # Line that opens parenthesis but doesn't close and ends with comma
            issues.append((line_num, f"Potential unclosed: balance={paren_balance}", line.strip()))
    
    print(f"Final parenthesis balance: {paren_balance}")
    
    if issues:
        print(f"\nFound {len(issues)} potential parenthesis issues:")
        for line_num, balance, line_content in issues[:10]:  # Show first 10
            print(f"  Line {line_num}: {balance} - {line_content}")
    
    # Look specifically around character position 5881 where browser error occurs
    char_count = 0
    for i, line in enumerate(lines):
        line_start = char_count
        line_end = char_count + len(line) + 1
        
        if line_start <= 5881 <= line_end:
            print(f"\n=== Area around character 5881 (JS line {i+1}) ===")
            
            # Check parenthesis balance in this area
            local_balance = 0
            for j in range(max(0, i-10), min(len(lines), i+10)):
                line_open = lines[j].count('(')
                line_close = lines[j].count(')')
                local_balance += line_open - line_close
                
                marker = '>>> ' if j == i else '    '
                print(f'{marker}Line {j+1} (bal: {local_balance}): {lines[j]}')
            
            break
        
        char_count = line_end

if __name__ == "__main__":
    find_missing_parenthesis()