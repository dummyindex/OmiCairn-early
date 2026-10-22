#!/usr/bin/env python3

import json
import os
import glob
from pathlib import Path
import pandas as pd
import numpy as np

def analyze_request_content():
    """Analyze what specific content in requests consumes the most tokens."""
    
    files = glob.glob(os.path.join(os.environ.get('TEST_OUTPUTS_DIR', 'test_outputs'), '**/claude_debugging/**/*.json'), recursive=True)
    
    content_analysis = {
        'error_messages': [],
        'code_snippets': [],
        'command_outputs': [],
        'large_requests': []
    }
    
    for file_path in files:
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            
            turns = data.get('turns', [])
            for turn_idx, turn in enumerate(turns):
                request = turn.get('request', '')
                input_tokens = turn.get('tokens', {}).get('input_tokens', 0)
                
                # Categorize content
                content_info = {
                    'file_path': file_path,
                    'turn': turn_idx + 1,
                    'input_tokens': input_tokens,
                    'request_length': len(request)
                }
                
                # Check for large error messages
                if 'Error Message:' in request:
                    error_start = request.find('Error Message:')
                    error_end = request.find('Previous Attempts:', error_start)
                    if error_end == -1:
                        error_end = request.find('Please analyze', error_start)
                    
                    error_msg = request[error_start:error_end] if error_end != -1 else request[error_start:]
                    content_info['error_message_length'] = len(error_msg)
                    content_analysis['error_messages'].append(content_info.copy())
                
                # Check for code in action results
                if 'Action result:' in request:
                    action_start = request.find('Action result:')
                    action_content = request[action_start:]
                    content_info['action_result_length'] = len(action_content)
                    content_analysis['command_outputs'].append(content_info.copy())
                
                # Check for very large requests
                if len(request) > 3000:
                    content_analysis['large_requests'].append(content_info.copy())
                    
        except Exception as e:
            print(f'Error processing {file_path}: {e}')
    
    # Analysis
    print("=== DETAILED TOKEN CONSUMPTION ANALYSIS ===\n")
    
    # Error message analysis
    if content_analysis['error_messages']:
        error_df = pd.DataFrame(content_analysis['error_messages'])
        print(f"ERROR MESSAGES:")
        print(f"  Total turns with error messages: {len(error_df)}")
        print(f"  Average error message length: {error_df['error_message_length'].mean():.0f} chars")
        print(f"  Average input tokens for error turns: {error_df['input_tokens'].mean():.0f}")
        print(f"  Longest error message: {error_df['error_message_length'].max()} chars")
        print()
    
    # Command output analysis
    if content_analysis['command_outputs']:
        output_df = pd.DataFrame(content_analysis['command_outputs'])
        print(f"COMMAND OUTPUTS:")
        print(f"  Total turns with command outputs: {len(output_df)}")
        print(f"  Average action result length: {output_df['action_result_length'].mean():.0f} chars")
        print(f"  Average input tokens for output turns: {output_df['input_tokens'].mean():.0f}")
        print(f"  Longest action result: {output_df['action_result_length'].max()} chars")
        print()
    
    # Large request analysis
    if content_analysis['large_requests']:
        large_df = pd.DataFrame(content_analysis['large_requests'])
        print(f"LARGE REQUESTS (>3000 chars):")
        print(f"  Total large requests: {len(large_df)}")
        print(f"  Average length of large requests: {large_df['request_length'].mean():.0f} chars")
        print(f"  Average input tokens for large requests: {large_df['input_tokens'].mean():.0f}")
        print(f"  Largest request: {large_df['request_length'].max()} chars")
        print()
        
        # Top 5 largest requests
        print("TOP 5 LARGEST REQUESTS:")
        top_large = large_df.nlargest(5, 'request_length')
        for idx, row in top_large.iterrows():
            path_parts = Path(row['file_path']).parts
            short_path = '/'.join(path_parts[-3:])
            print(f"  {short_path}, Turn {row['turn']}: {row['request_length']:,} chars, {row['input_tokens']:,} tokens")
        print()

def analyze_specific_content_types():
    """Analyze specific types of content that appear in requests."""
    
    files = glob.glob(os.path.join(os.environ.get('TEST_OUTPUTS_DIR', 'test_outputs'), '**/claude_debugging/**/*.json'), recursive=True)[:10]  # Sample first 10
    
    content_types = {
        'pip_install_output': 0,
        'python_tracebacks': 0,
        'function_code': 0,
        'container_logs': 0,
        'dependency_conflicts': 0
    }
    
    total_chars = 0
    
    for file_path in files:
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            
            turns = data.get('turns', [])
            for turn in turns:
                request = turn.get('request', '')
                total_chars += len(request)
                
                # Count different content types
                if 'Requirement already satisfied:' in request:
                    content_types['pip_install_output'] += request.count('Requirement already satisfied:')
                
                if 'Traceback (most recent call last):' in request:
                    content_types['python_tracebacks'] += 1
                
                if 'def run(path_dict, params):' in request:
                    content_types['function_code'] += 1
                
                if 'Container exited with code' in request:
                    content_types['container_logs'] += 1
                
                if 'dependency resolver does not currently' in request:
                    content_types['dependency_conflicts'] += 1
                    
        except Exception as e:
            continue
    
    print("CONTENT TYPE ANALYSIS (Sample of 10 files):")
    print(f"Total characters analyzed: {total_chars:,}")
    for content_type, count in content_types.items():
        print(f"  {content_type}: {count} occurrences")
    print()

def token_efficiency_analysis():
    """Analyze token efficiency patterns."""
    
    files = glob.glob(os.path.join(os.environ.get('TEST_OUTPUTS_DIR', 'test_outputs'), '**/claude_debugging/**/*.json'), recursive=True)
    
    efficiency_data = []
    
    for file_path in files:
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            
            total_tokens = data.get('total_tokens', {}).get('total', 0)
            success = data.get('success', False)
            iterations = data.get('iterations', 0)
            
            if total_tokens > 0:
                efficiency_data.append({
                    'file_path': file_path,
                    'total_tokens': total_tokens,
                    'success': success,
                    'iterations': iterations,
                    'tokens_per_iteration': total_tokens / max(iterations, 1),
                    'efficiency_score': 1 / total_tokens if success else 0
                })
                
        except Exception as e:
            continue
    
    if efficiency_data:
        eff_df = pd.DataFrame(efficiency_data)
        
        print("TOKEN EFFICIENCY ANALYSIS:")
        print(f"Successful attempts use on average: {eff_df[eff_df['success']]['total_tokens'].mean():.0f} tokens")
        print(f"Failed attempts use on average: {eff_df[~eff_df['success']]['total_tokens'].mean():.0f} tokens")
        print(f"Average tokens per iteration: {eff_df['tokens_per_iteration'].mean():.0f}")
        print()
        
        # Most efficient successful attempts
        successful = eff_df[eff_df['success']].nsmallest(5, 'total_tokens')
        print("MOST EFFICIENT SUCCESSFUL ATTEMPTS:")
        for idx, row in successful.iterrows():
            path_parts = Path(row['file_path']).parts
            short_path = '/'.join(path_parts[-3:])
            print(f"  {short_path}: {row['total_tokens']:,} tokens in {row['iterations']} iterations")

if __name__ == '__main__':
    analyze_request_content()
    analyze_specific_content_types()
    token_efficiency_analysis()