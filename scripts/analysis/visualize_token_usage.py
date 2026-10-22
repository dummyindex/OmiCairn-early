#!/usr/bin/env python3
"""Visualize Claude token usage patterns from debugging sessions."""

import json
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path
from collections import defaultdict

def analyze_token_usage():
    """Analyze token usage from Claude debugging reports."""
    
    # Find all report files
    report_files = list(Path("test_outputs").rglob("**/claude_debugging/*_report.json"))
    
    stats = {
        'total_reports': 0,
        'by_content_type': defaultdict(lambda: {'count': 0, 'tokens': 0}),
        'input_output_by_turn': [],
        'by_error_type': defaultdict(lambda: {'count': 0, 'tokens': 0}),
        'pip_output_tokens': 0,
        'error_message_tokens': 0,
        'code_content_tokens': 0,
        'other_tokens': 0
    }
    
    for report_file in report_files:
        try:
            with open(report_file) as f:
                report = json.load(f)
                
            stats['total_reports'] += 1
            
            # Analyze each turn
            for turn in report.get('turns', []):
                request = turn.get('request', '')
                
                # Get token counts
                if 'response' in turn and '_metadata' in turn['response']:
                    usage = turn['response']['_metadata']['usage']
                    input_tokens = usage.get('input_tokens', 0)
                    output_tokens = usage.get('output_tokens', 0)
                    
                    stats['input_output_by_turn'].append({
                        'input': input_tokens,
                        'output': output_tokens,
                        'turn': turn.get('turn', 0)
                    })
                    
                    # Categorize content
                    if 'pip install' in request or 'Requirement already satisfied' in request:
                        stats['pip_output_tokens'] += input_tokens
                        stats['by_content_type']['pip_output']['count'] += 1
                        stats['by_content_type']['pip_output']['tokens'] += input_tokens
                    elif 'Traceback' in request or 'Error:' in request:
                        stats['error_message_tokens'] += input_tokens
                        stats['by_content_type']['error_trace']['count'] += 1
                        stats['by_content_type']['error_trace']['tokens'] += input_tokens
                    elif 'def ' in request or 'import ' in request:
                        stats['code_content_tokens'] += input_tokens
                        stats['by_content_type']['code']['count'] += 1
                        stats['by_content_type']['code']['tokens'] += input_tokens
                    else:
                        stats['other_tokens'] += input_tokens
                        stats['by_content_type']['other']['count'] += 1
                        stats['by_content_type']['other']['tokens'] += input_tokens
                        
        except Exception as e:
            print(f"Error processing {report_file}: {e}")
    
    return stats

def create_visualizations(stats):
    """Create token usage visualizations."""
    
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 12))
    
    # 1. Pie chart of content types
    content_types = ['Pip Output', 'Error Messages', 'Code Content', 'Other']
    token_counts = [
        stats['pip_output_tokens'],
        stats['error_message_tokens'],
        stats['code_content_tokens'],
        stats['other_tokens']
    ]
    
    ax1.pie(token_counts, labels=content_types, autopct='%1.1f%%', startangle=90)
    ax1.set_title('Input Token Distribution by Content Type')
    
    # 2. Input vs Output tokens scatter plot
    input_tokens = [t['input'] for t in stats['input_output_by_turn']]
    output_tokens = [t['output'] for t in stats['input_output_by_turn']]
    
    ax2.scatter(input_tokens, output_tokens, alpha=0.5)
    ax2.set_xlabel('Input Tokens')
    ax2.set_ylabel('Output Tokens')
    ax2.set_title('Input vs Output Tokens per Turn')
    ax2.set_xlim(0, max(input_tokens) * 1.1)
    ax2.set_ylim(0, max(output_tokens) * 1.1)
    
    # Add trend line
    z = np.polyfit(input_tokens, output_tokens, 1)
    p = np.poly1d(z)
    ax2.plot(sorted(input_tokens), p(sorted(input_tokens)), "r--", alpha=0.8)
    
    # 3. Token usage by turn number
    turn_data = defaultdict(list)
    for t in stats['input_output_by_turn']:
        turn_data[t['turn']].append(t['input'])
    
    turns = sorted(turn_data.keys())
    avg_tokens = [np.mean(turn_data[t]) for t in turns]
    
    ax3.bar(turns, avg_tokens)
    ax3.set_xlabel('Turn Number')
    ax3.set_ylabel('Average Input Tokens')
    ax3.set_title('Average Input Tokens by Turn Number')
    
    # 4. Content type frequency vs average tokens
    content_data = []
    for ctype, data in stats['by_content_type'].items():
        if data['count'] > 0:
            content_data.append({
                'type': ctype,
                'count': data['count'],
                'avg_tokens': data['tokens'] / data['count']
            })
    
    if content_data:
        types = [d['type'] for d in content_data]
        counts = [d['count'] for d in content_data]
        avg_tokens = [d['avg_tokens'] for d in content_data]
        
        x = np.arange(len(types))
        width = 0.35
        
        ax4_twin = ax4.twinx()
        bars1 = ax4.bar(x - width/2, counts, width, label='Count', color='skyblue')
        bars2 = ax4_twin.bar(x + width/2, avg_tokens, width, label='Avg Tokens', color='orange')
        
        ax4.set_xlabel('Content Type')
        ax4.set_ylabel('Count', color='skyblue')
        ax4_twin.set_ylabel('Average Tokens', color='orange')
        ax4.set_title('Content Type Frequency and Token Usage')
        ax4.set_xticks(x)
        ax4.set_xticklabels(types, rotation=45)
        ax4.tick_params(axis='y', labelcolor='skyblue')
        ax4_twin.tick_params(axis='y', labelcolor='orange')
    
    plt.tight_layout()
    plt.savefig('token_usage_analysis.png', dpi=300, bbox_inches='tight')
    print("Saved visualization to token_usage_analysis.png")
    
    # Print summary statistics
    total_input = sum(t['input'] for t in stats['input_output_by_turn'])
    total_output = sum(t['output'] for t in stats['input_output_by_turn'])
    
    print("\n=== Token Usage Summary ===")
    print(f"Total Reports Analyzed: {stats['total_reports']}")
    print(f"Total Input Tokens: {total_input:,}")
    print(f"Total Output Tokens: {total_output:,}")
    print(f"Input:Output Ratio: {total_input/total_output:.1f}:1")
    print(f"\nContent Type Breakdown:")
    print(f"  Pip Output: {stats['pip_output_tokens']:,} tokens ({stats['pip_output_tokens']/total_input*100:.1f}%)")
    print(f"  Error Messages: {stats['error_message_tokens']:,} tokens ({stats['error_message_tokens']/total_input*100:.1f}%)")
    print(f"  Code Content: {stats['code_content_tokens']:,} tokens ({stats['code_content_tokens']/total_input*100:.1f}%)")
    print(f"  Other: {stats['other_tokens']:,} tokens ({stats['other_tokens']/total_input*100:.1f}%)")

if __name__ == "__main__":
    stats = analyze_token_usage()
    create_visualizations(stats)