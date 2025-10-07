#!/usr/bin/env python3
"""
Fix parenthesis balance by finding and fixing the exact unmatched parenthesis
"""
import re
from pathlib import Path

def fix_parenthesis_balance():
    file_path = Path('frontend/templates/artist_detail.html')
    content = file_path.read_text()
    
    # Find the script block
    script_start = content.find('<script>')
    script_end = content.find('</script>')
    if script_start == -1 or script_end == -1:
        print("No script block found")
        return False
        
    js_code = content[script_start+8:script_end]
    lines = js_code.split('\n')
    
    # Track parentheses balance and find unmatched
    balance = 0
    max_balance = 0
    problematic_lines = []
    
    for i, line in enumerate(lines):
        line_num = i + 1
        
        # Count parentheses in this line
        line_open = line.count('(')
        line_close = line.count(')')
        old_balance = balance
        balance += line_open - line_close
        
        if balance > max_balance:
            max_balance = balance
        
        # Track lines that cause imbalance issues
        if balance < 0:
            problematic_lines.append((line_num, balance, 'Negative balance', line.strip()))
        elif line_open > line_close + 1:  # Line opens way more than it closes
            problematic_lines.append((line_num, balance, f'Opens {line_open}, closes {line_close}', line.strip()))
    
    print(f"Final balance: {balance}")
    print(f"Max balance during parsing: {max_balance}")
    
    if problematic_lines:
        print(f"\nProblematic lines:")
        for line_num, bal, reason, content in problematic_lines[:5]:
            print(f"  Line {line_num}: {reason} (balance: {bal})")
            print(f"    Content: {content[:100]}...")
    
    # If balance is +1, we need to find where to add a closing parenthesis
    if balance == 1:
        print(f"\nSearching for best place to add closing parenthesis...")
        
        # Look for common patterns where a closing paren might be missing
        for i, line in enumerate(lines):
            line_num = i + 1
            stripped = line.strip()
            
            # Common patterns that might be missing closing parens
            patterns = [
                (r'if\s*\([^)]*$', 'Incomplete if condition'),
                (r'function\s*\([^)]*$', 'Incomplete function definition'),
                (r'\([^)]*,\s*$', 'Incomplete function call with trailing comma'),
                (r'\.then\s*\([^)]*$', 'Incomplete .then() call'),
                (r'fetch\s*\([^)]*$', 'Incomplete fetch() call'),
                (r'console\.\w+\s*\([^)]*$', 'Incomplete console call'),
                (r'JSON\.\w+\s*\([^)]*$', 'Incomplete JSON call'),
            ]
            
            for pattern, description in patterns:
                if re.search(pattern, stripped):
                    print(f"  Line {line_num}: {description}")
                    print(f"    Content: {stripped}")
                    
                    # Show next few lines for context
                    for j in range(i+1, min(len(lines), i+4)):
                        print(f"    Line {j+1}: {lines[j].strip()}")
                    print("  ---")
    
    return balance == 0

if __name__ == "__main__":
    fix_parenthesis_balance()