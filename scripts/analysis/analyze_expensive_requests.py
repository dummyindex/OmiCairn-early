#!/usr/bin/env python3
"""Analyze the most expensive token requests in detail."""

import json
from pathlib import Path
from collections import defaultdict
import re

def analyze_expensive_requests():
    """Find and analyze the most token-expensive requests."""
    
    # Find all report files
    report_files = list(Path("test_outputs").rglob("**/claude_debugging/*_report.json"))
    
    expensive_turns = []
    
    for report_file in report_files:
        try:
            with open(report_file) as f:
                report = json.load(f)
                
            # Analyze each turn
            for turn in report.get('turns', []):
                request = turn.get('request', '')
                
                # Get token counts
                if 'response' in turn and '_metadata' in turn['response']:
                    usage = turn['response']['_metadata']['usage']
                    input_tokens = usage.get('input_tokens', 0)
                    
                    # Analyze request content
                    content_analysis = {
                        'file': str(report_file),
                        'turn': turn.get('turn', 0),
                        'input_tokens': input_tokens,
                        'request_length': len(request),
                        'contains_pip': 'pip install' in request or 'Requirement already satisfied' in request,
                        'contains_error': 'Traceback' in request or 'Error:' in request,
                        'contains_code': 'def ' in request or 'import ' in request,
                        'pip_lines': request.count('Requirement already satisfied'),
                        'collecting_lines': request.count('Collecting'),
                        'warning_lines': request.count('WARNING:'),
                        'request_preview': request[:200] + '...' if len(request) > 200 else request
                    }
                    
                    expensive_turns.append(content_analysis)
                    
        except Exception as e:
            print(f"Error processing {report_file}: {e}")
    
    # Sort by token usage
    expensive_turns.sort(key=lambda x: x['input_tokens'], reverse=True)
    
    return expensive_turns

def analyze_pip_output_patterns(expensive_turns):
    """Analyze patterns in pip output that consume tokens."""
    
    pip_patterns = defaultdict(int)
    pip_token_waste = 0
    
    for turn in expensive_turns:
        if turn['contains_pip']:
            # Estimate wasted tokens
            # Each "Requirement already satisfied" line is ~20-30 tokens
            waste = turn['pip_lines'] * 25
            pip_token_waste += waste
            
            pip_patterns['total_pip_turns'] += 1
            pip_patterns['total_pip_tokens'] += turn['input_tokens']
            pip_patterns['avg_pip_lines'] += turn['pip_lines']
            pip_patterns['avg_collecting_lines'] += turn['collecting_lines']
    
    if pip_patterns['total_pip_turns'] > 0:
        pip_patterns['avg_pip_lines'] /= pip_patterns['total_pip_turns']
        pip_patterns['avg_collecting_lines'] /= pip_patterns['total_pip_turns']
        pip_patterns['avg_tokens_per_turn'] = pip_patterns['total_pip_tokens'] / pip_patterns['total_pip_turns']
    
    return pip_patterns, pip_token_waste

def print_analysis(expensive_turns):
    """Print detailed analysis."""
    
    print("=== Most Expensive Token Requests ===\n")

    if not expensive_turns:
        print("No claude_debugging reports with token usage found under test_outputs/.")
        return

    # Top 10 most expensive
    print("Top 10 Most Token-Expensive Turns:")
    print("-" * 80)
    
    for i, turn in enumerate(expensive_turns[:10]):
        print(f"\n{i+1}. Turn {turn['turn']} - {turn['input_tokens']:,} tokens")
        print(f"   File: {Path(turn['file']).parent.parent.name}")
        print(f"   Request length: {turn['request_length']:,} characters")
        print(f"   Content: ", end="")
        
        content_types = []
        if turn['contains_pip']:
            content_types.append(f"Pip output ({turn['pip_lines']} requirement lines)")
        if turn['contains_error']:
            content_types.append("Error/Traceback")
        if turn['contains_code']:
            content_types.append("Code")
        
        print(", ".join(content_types) if content_types else "Other")
        print(f"   Preview: {turn['request_preview']}")
    
    # Analyze pip patterns
    pip_patterns, pip_waste = analyze_pip_output_patterns(expensive_turns)
    
    print("\n\n=== Pip Output Analysis ===")
    print(f"Total pip-related turns: {pip_patterns['total_pip_turns']}")
    print(f"Total tokens in pip turns: {pip_patterns['total_pip_tokens']:,}")
    print(f"Average tokens per pip turn: {pip_patterns['avg_tokens_per_turn']:.0f}")
    print(f"Average 'Requirement already satisfied' lines: {pip_patterns['avg_pip_lines']:.1f}")
    print(f"Estimated wasted tokens on repetitive pip output: {pip_waste:,}")
    print(f"Potential savings by summarizing pip output: {pip_waste / sum(t['input_tokens'] for t in expensive_turns) * 100:.1f}%")
    
    # Token distribution
    print("\n\n=== Token Distribution Analysis ===")
    
    ranges = [(0, 1000), (1000, 2000), (2000, 3000), (3000, 5000), (5000, 10000), (10000, float('inf'))]
    distribution = defaultdict(int)
    
    for turn in expensive_turns:
        tokens = turn['input_tokens']
        for low, high in ranges:
            if low <= tokens < high:
                range_key = f"{low}-{high}" if high != float('inf') else f"{low}+"
                distribution[range_key] += 1
                break
    
    print("Token Range Distribution:")
    for range_key, count in sorted(distribution.items()):
        print(f"  {range_key:>10} tokens: {count:>3} turns")
    
    # Character to token ratio
    char_token_ratios = []
    for turn in expensive_turns:
        if turn['request_length'] > 0:
            ratio = turn['input_tokens'] / turn['request_length']
            char_token_ratios.append(ratio)
    
    if char_token_ratios:
        avg_ratio = sum(char_token_ratios) / len(char_token_ratios)
        print(f"\nAverage character-to-token ratio: {avg_ratio:.2f} tokens per character")
    
    # Recommendations
    print("\n\n=== Optimization Recommendations ===")
    print("1. Pip Output Reduction:")
    print(f"   - Current: ~{pip_patterns['avg_pip_lines']:.0f} 'Requirement' lines per pip output")
    print("   - Recommended: Summarize to 2-3 lines showing only newly installed packages")
    print(f"   - Potential savings: {pip_waste:,} tokens ({pip_waste/1000:.1f}k tokens)")
    
    print("\n2. Request Size Limits:")
    large_requests = sum(1 for t in expensive_turns if t['request_length'] > 5000)
    print(f"   - {large_requests} requests exceed 5,000 characters")
    print("   - Implement truncation for command outputs over 3,000 characters")
    
    print("\n3. Context Window Management:")
    print("   - Use rolling context window of last 2-3 turns only")
    print("   - Reference previous fixes by ID instead of repeating code")

if __name__ == "__main__":
    expensive_turns = analyze_expensive_requests()
    print_analysis(expensive_turns)