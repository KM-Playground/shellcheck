#!/usr/bin/env python3
"""
Run ShellCheck with diff-aware filtering and reviewdog integration.

This script:
1. Runs ShellCheck on shell scripts from shell_scripts.txt
2. Filters out trivial syntax errors
3. Filters to only show issues on modified lines (from modified_lines_map.txt)
4. Pipes filtered results to reviewdog for inline PR comments
5. Outputs summary information for the workflow
"""

import os
import re
import subprocess
import sys


def filter_trivial_issues(shellcheck_output):
    """
    Filter out trivial syntax errors from ShellCheck output.
    
    Args:
        shellcheck_output (str): Raw ShellCheck output in GCC format
        
    Returns:
        list: Filtered lines without trivial issues
    """
    # Filter out only truly trivial issues that don't affect script functionality:
    # SC1071: ShellCheck only supports sh/bash/dash/ksh scripts (informational)
    #
    # NOTE: Removed SC1009, SC1073, SC1072, SC1070 as these are CRITICAL syntax errors
    # that should fail the build, not be filtered out as trivial
    trivial_codes = ['SC1071']
    
    filtered_lines = []
    for line in shellcheck_output.split('\n'):
        if line.strip():
            # Check if line contains any trivial error codes
            is_trivial = any(code in line for code in trivial_codes)
            if not is_trivial:
                filtered_lines.append(line)
    
    return filtered_lines


def is_line_modified(file_path, line_num, modified_lines_str):
    """
    Check if a specific line number is in the modified lines for a file.
    
    Args:
        file_path (str): Path to the file
        line_num (int): Line number to check
        modified_lines_str (str): Comma-separated list of modified lines or "all"
        
    Returns:
        bool: True if the line was modified, False otherwise
    """
    # If modified_lines is "all", then all lines are considered modified (new file)
    if modified_lines_str == "all":
        return True
    
    # Check if line_num is in the comma-separated list of modified lines
    try:
        modified_lines = [int(x.strip()) for x in modified_lines_str.split(',') if x.strip()]
        return line_num in modified_lines
    except ValueError:
        # If we can't parse the line numbers, assume it's modified to be safe
        return True


def load_modified_lines_map(map_file):
    """
    Load the modified lines mapping from file.
    
    Args:
        map_file (str): Path to the modified_lines_map.txt file
        
    Returns:
        dict: Mapping of file paths to modified lines strings
    """
    modified_lines_map = {}
    try:
        with open(map_file, 'r') as f:
            for line in f:
                line = line.strip()
                if ':' in line:
                    file_path, modified_lines = line.split(':', 1)
                    modified_lines_map[file_path] = modified_lines
    except FileNotFoundError:
        print(f"Warning: {map_file} not found", file=sys.stderr)
    
    return modified_lines_map


def run_shellcheck_on_files(shell_scripts_file):
    """
    Run ShellCheck on all files listed in shell_scripts.txt.
    
    Args:
        shell_scripts_file (str): Path to file containing list of shell scripts
        
    Returns:
        str: Combined ShellCheck output for all files
    """
    try:
        with open(shell_scripts_file, 'r') as f:
            shell_scripts = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print(f"Error: {shell_scripts_file} not found", file=sys.stderr)
        return ""
    
    all_output = []
    
    for script in shell_scripts:
        if script and os.path.isfile(script):
            print(f"Checking: {script}")
            try:
                # Run shellcheck with GCC format output
                result = subprocess.run(
                    ['shellcheck', '-f', 'gcc', script],
                    capture_output=True,
                    text=True
                )
                # ShellCheck returns non-zero exit code when issues are found
                # We want to capture the output regardless
                if result.stdout:
                    all_output.append(result.stdout)
                if result.stderr:
                    all_output.append(result.stderr)
            except subprocess.CalledProcessError as e:
                # This shouldn't happen with capture_output=True, but just in case
                if e.stdout:
                    all_output.append(e.stdout)
                if e.stderr:
                    all_output.append(e.stderr)
            except FileNotFoundError:
                print(f"Error: shellcheck command not found", file=sys.stderr)
                return ""
    
    return '\n'.join(all_output)


def main():
    if len(sys.argv) != 3:
        print("Usage: python3 run_shellcheck.py <shell_scripts_file> <modified_lines_map_file>", file=sys.stderr)
        sys.exit(1)
    
    shell_scripts_file = sys.argv[1]
    modified_lines_map_file = sys.argv[2]
    
    print("Running ShellCheck on modified shell scripts with diff-aware filtering...")
    
    # Run ShellCheck on all shell scripts
    raw_output = run_shellcheck_on_files(shell_scripts_file)
    
    # Write raw output to file
    with open('shellcheck_raw.txt', 'w') as f:
        f.write(raw_output)
    
    # Filter out trivial issues
    filtered_lines = filter_trivial_issues(raw_output)
    
    # Write filtered output to file
    with open('shellcheck_filtered.txt', 'w') as f:
        f.write('\n'.join(filtered_lines))
    
    # Load modified lines mapping
    modified_lines_map = load_modified_lines_map(modified_lines_map_file)
    
    # Filter to only include issues on modified lines
    diff_filtered_lines = []
    gcc_format_pattern = re.compile(r'^([^:]+):(\d+):\d+:.*$')
    
    for line in filtered_lines:
        if line.strip():
            match = gcc_format_pattern.match(line)
            if match:
                file_path = match.group(1)
                line_num = int(match.group(2))
                
                # Get modified lines for this file
                modified_lines_str = modified_lines_map.get(file_path, "")
                
                if modified_lines_str and is_line_modified(file_path, line_num, modified_lines_str):
                    diff_filtered_lines.append(line)
                    print(f"  ✓ Issue on modified line {line_num}: {line}")
                else:
                    print(f"  ⏭ Skipping issue on unmodified line {line_num}")
    
    # Write diff-filtered output to file
    with open('shellcheck_diff_filtered.txt', 'w') as f:
        f.write('\n'.join(diff_filtered_lines))
    
    # Count issues and determine exit code
    total_issues = len(diff_filtered_lines)
    exit_code = 1 if total_issues > 0 else 0
    
    if total_issues > 0:
        print(f"Found {total_issues} non-trivial ShellCheck issue(s) on modified lines")
        
        # Copy results for summary
        with open('shellcheck_results.txt', 'w') as f:
            f.write('\n'.join(diff_filtered_lines))
    else:
        print("No non-trivial ShellCheck issues found on modified lines")
        # Create empty results file
        open('shellcheck_results.txt', 'w').close()
    
    # Output for GitHub Actions
    print(f"total_issues={total_issues}")
    print(f"exit_code={exit_code}")


if __name__ == "__main__":
    main()
