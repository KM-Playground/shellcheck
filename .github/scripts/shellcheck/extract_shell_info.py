#!/usr/bin/env python3
"""
Extract shell scripts and their modified lines from changeset and diff.

This script combines two operations:
1. Identifies which files in the changeset are shell scripts
2. Extracts modified line numbers from the diff for those shell scripts

It's used by the ShellCheck workflow to determine which files need linting
and which lines should be checked.
"""

import os
import re
import sys
from collections import defaultdict


def is_shell_script(file_path):
    """
    Check if a file is a shell script based on extension or shebang.
    
    Args:
        file_path (str): Path to the file to check
        
    Returns:
        bool: True if the file is a shell script, False otherwise
    """
    # Check file extension
    if file_path.endswith(('.sh', '.bash')):
        return True
    
    # Check if file exists and has shell shebang
    if os.path.isfile(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                first_line = f.readline().strip()
                # Check for shell shebangs
                if first_line.startswith('#!') and ('bash' in first_line or 'sh' in first_line):
                    return True
        except (IOError, OSError):
            # If we can't read the file, skip it
            pass
    
    return False


def parse_diff_file(diff_file_path):
    """Parse git diff and return modified line numbers for each file."""
    modified_lines = defaultdict(set)
    
    try:
        with open(diff_file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"Error: {diff_file_path} not found", file=sys.stderr)
        return modified_lines
    
    current_file = None
    current_line_num = 0
    
    for line in content.split('\n'):
        # Match diff --git a/filename b/filename
        git_diff_match = re.match(r'^diff --git a/(.+) b/(.+)$', line)
        if git_diff_match:
            current_file = git_diff_match.group(1)
            continue
        
        # Match hunk header: @@ -old_start,old_count +new_start,new_count @@
        hunk_match = re.match(r'^@@\s+-\d+(?:,\d+)?\s+\+(\d+)(?:,\d+)?\s+@@', line)
        if hunk_match and current_file:
            current_line_num = int(hunk_match.group(1))
            continue
        
        # Process diff lines
        if current_file and current_line_num > 0:
            if line.startswith('+') and not line.startswith('+++'):
                # This is an added line
                modified_lines[current_file].add(current_line_num)
                current_line_num += 1
            elif line.startswith(' '):
                # This is a context line (unchanged)
                current_line_num += 1
            elif line.startswith('-') and not line.startswith('---'):
                # This is a deleted line, don't increment line number
                pass
    
    return modified_lines


def main():
    if len(sys.argv) != 3:
        print("Usage: python3 extract_shell_info.py <changeset_file> <diff_file>", file=sys.stderr)
        sys.exit(1)
    
    changeset_file = sys.argv[1]
    diff_file = sys.argv[2]
    
    # Read changeset file to get all changed files
    try:
        with open(changeset_file, 'r') as f:
            changed_files = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print(f"Error: {changeset_file} not found", file=sys.stderr)
        sys.exit(1)
    
    # Extract shell scripts from changed files
    shell_scripts = []
    for file_path in changed_files:
        if is_shell_script(file_path):
            shell_scripts.append(file_path)
    
    # Write shell scripts to output file
    with open('shell_scripts.txt', 'w') as f:
        for script in shell_scripts:
            f.write(f"{script}\n")
    
    # Print shell script results
    if shell_scripts:
        print(f"Found {len(shell_scripts)} shell script(s):")
        for script in shell_scripts:
            print(f"  {script}")
        print("has_shell_scripts=true")
        
        # Parse diff to get modified lines for shell scripts only
        modified_lines = parse_diff_file(diff_file)
        
        # Create mapping file for shell scripts
        with open('modified_lines_map.txt', 'w') as f:
            for script in shell_scripts:
                if script in modified_lines and modified_lines[script]:
                    # Sort line numbers and join with commas
                    lines = sorted(modified_lines[script])
                    lines_str = ','.join(map(str, lines))
                    f.write(f"{script}:{lines_str}\n")
                    print(f"Extracting modified lines for: {script}")
                    print(f"  Modified lines: {lines_str}")
                else:
                    # No modified lines found (might be new file or renamed)
                    f.write(f"{script}:all\n")
                    print(f"Extracting modified lines for: {script}")
                    print(f"  No modified lines found (file might be new or renamed)")
    else:
        print("No shell scripts found in changeset")
        print("has_shell_scripts=false")
        # Create empty files for consistency
        open('modified_lines_map.txt', 'w').close()


if __name__ == "__main__":
    main()
