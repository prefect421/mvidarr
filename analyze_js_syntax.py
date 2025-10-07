#!/usr/bin/env python3
"""
Analyze JavaScript for syntax errors in artist_detail.html
"""
import re
from pathlib import Path

def analyze_js_syntax():
    content = Path('frontend/templates/artist_detail.html').read_text()
    
    # Find the script block
    script_start = content.find('<script>')
    script_end = content.find('</script>')
    if script_start == -1 or script_end == -1:
        print("No script block found")
        return
        
    js_code = content[script_start+8:script_end]
    lines = js_code.split('\n')
    
    print(f"Analyzing {len(lines)} lines of JavaScript")
    
    # Track braces and find issues
    open_braces = 0
    brace_issues = []
    
    # Track if/else patterns
    else_issues = []
    
    for i, line in enumerate(lines):
        line_num = i + 1
        stripped = line.strip()
        
        # Count braces in this line
        line_open = line.count('{')
        line_close = line.count('}')
        open_braces += line_open - line_close
        
        # Check for orphaned else statements
        if re.search(r'\belse\s*{', stripped):
            # Look back for corresponding if
            found_if = False
            for j in range(i-1, max(0, i-10), -1):
                prev_line = lines[j].strip()
                if re.search(r'\bif\s*\(.*\)\s*{?\s*$', prev_line) or prev_line.endswith('{'):
                    found_if = True
                    break
                elif prev_line and not prev_line.startswith('//') and not re.match(r'^\s*$', prev_line):
                    break
            
            if not found_if:
                else_issues.append((line_num, stripped))
        
        # Check for empty else blocks
        if re.search(r'}\s*else\s*{\s*}', line):
            else_issues.append((line_num, f"Empty else block: {stripped}"))
    
    print(f"\nBrace balance: {open_braces} (should be 0)")
    
    if else_issues:
        print(f"\nFound {len(else_issues)} else statement issues:")
        for line_num, issue in else_issues[:10]:  # Show first 10
            print(f"  Line {line_num}: {issue}")
    
    # Look for specific problematic patterns
    print(f"\nLooking for syntax error patterns...")
    
    # Find lines with potential issues
    for i, line in enumerate(lines):
        line_num = i + 1
        stripped = line.strip()
        
        # Look for empty blocks or malformed syntax
        if re.search(r'}\s*else\s*{\s*$', stripped) and i+1 < len(lines):
            next_line = lines[i+1].strip()
            if next_line == '}' or not next_line:
                print(f"  Line {line_num}: Potentially empty else block")
                print(f"    Current: {stripped}")
                print(f"    Next: {next_line}")
        
        # Look for missing semicolons or malformed statements
        if stripped.endswith('else') and not stripped.endswith('else {'):
            print(f"  Line {line_num}: Incomplete else statement: {stripped}")

if __name__ == "__main__":
    analyze_js_syntax()