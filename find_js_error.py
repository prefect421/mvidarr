#!/usr/bin/env python3
"""
Find JavaScript syntax error at character position 5881
"""
import re
from pathlib import Path

content = Path('frontend/templates/artist_detail.html').read_text()

# Find the script block
script_start = content.find('<script>')
script_end = content.find('</script>')
if script_start != -1 and script_end != -1:
    js_code = content[script_start+8:script_end]
    lines = js_code.split('\n')
    
    print(f'JavaScript block has {len(lines)} lines')
    
    # Look for issues around character 5881
    char_count = 0
    for i, line in enumerate(lines):
        line_start = char_count
        line_end = char_count + len(line) + 1  # +1 for newline
        
        if line_start <= 5881 <= line_end:
            print(f'Character 5881 is on line {i+1} at position {5881-line_start}')
            print(f'Line content: {line}')
            
            # Show surrounding lines
            for j in range(max(0, i-3), min(len(lines), i+4)):
                marker = '>>> ' if j == i else '    '
                print(f'{marker}Line {j+1}: {lines[j]}')
            break
        
        char_count = line_end

    # Also check for brace mismatches in chunks around that area
    chunk_start = max(0, 5881 - 500)
    chunk_end = min(len(js_code), 5881 + 500)
    chunk = js_code[chunk_start:chunk_end]
    
    print(f'\n--- Code chunk around character 5881 ---')
    print(chunk)