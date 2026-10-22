"""Tests for action executor."""

import pytest
import tempfile
from pathlib import Path
import subprocess

from agents.unified_bug_fixer.action_executor import ActionExecutor


class TestActionExecutor:
    """Test action executor functionality."""
    
    def test_read_file(self):
        """Test reading file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            test_file = workspace / "test.txt"
            test_file.write_text("Hello, World!")
            
            executor = ActionExecutor(workspace)
            result = executor.execute_action({
                'type': 'read_file',
                'path': 'test.txt'
            })
            
            assert result['success'] is True
            assert result['content'] == "Hello, World!"
            
    def test_read_nonexistent_file(self):
        """Test reading non-existent file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            
            executor = ActionExecutor(workspace)
            result = executor.execute_action({
                'type': 'read_file',
                'path': 'nonexistent.txt'
            })
            
            assert result['success'] is False
            assert 'not found' in result['error']
            
    def test_write_file(self):
        """Test writing file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            
            executor = ActionExecutor(workspace)
            result = executor.execute_action({
                'type': 'write_file',
                'path': 'output.txt',
                'content': 'Test content'
            })
            
            assert result['success'] is True
            assert (workspace / 'output.txt').read_text() == 'Test content'
            
    def test_write_file_with_subdirectory(self):
        """Test writing file in subdirectory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            
            executor = ActionExecutor(workspace)
            result = executor.execute_action({
                'type': 'write_file',
                'path': 'subdir/output.txt',
                'content': 'Test content'
            })
            
            assert result['success'] is True
            assert (workspace / 'subdir' / 'output.txt').exists()
            assert (workspace / 'subdir' / 'output.txt').read_text() == 'Test content'
            
    def test_execute_command(self):
        """Test executing command."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            
            executor = ActionExecutor(workspace)
            result = executor.execute_action({
                'type': 'execute_command',
                'command': 'echo "Hello"'
            })
            
            assert result['success'] is True
            assert result['stdout'].strip() == 'Hello'
            assert result['return_code'] == 0
            
    def test_list_directory(self):
        """Test listing directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / 'file1.txt').write_text('content1')
            (workspace / 'file2.py').write_text('content2')
            (workspace / 'subdir').mkdir()
            
            executor = ActionExecutor(workspace)
            result = executor.execute_action({
                'type': 'list_directory',
                'path': '.'
            })
            
            assert result['success'] is True
            entries = result['entries']
            assert len(entries) == 3
            
            # Check entries
            names = [e['name'] for e in entries]
            assert 'file1.txt' in names
            assert 'file2.py' in names
            assert 'subdir' in names
            
            # Check types
            for entry in entries:
                if entry['name'] == 'subdir':
                    assert entry['type'] == 'directory'
                else:
                    assert entry['type'] == 'file'
                    
    def test_create_directory(self):
        """Test creating directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            
            executor = ActionExecutor(workspace)
            result = executor.execute_action({
                'type': 'create_directory',
                'path': 'new_dir/sub_dir'
            })
            
            assert result['success'] is True
            assert (workspace / 'new_dir' / 'sub_dir').exists()
            assert (workspace / 'new_dir' / 'sub_dir').is_dir()
            
    def test_check_file_exists(self):
        """Test checking file existence."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / 'existing.txt').write_text('content')
            (workspace / 'existing_dir').mkdir()
            
            executor = ActionExecutor(workspace)
            
            # Check existing file
            result = executor.execute_action({
                'type': 'check_file_exists',
                'path': 'existing.txt'
            })
            assert result['success'] is True
            assert result['exists'] is True
            assert result['is_file'] is True
            assert result['is_directory'] is False
            
            # Check existing directory
            result = executor.execute_action({
                'type': 'check_file_exists',
                'path': 'existing_dir'
            })
            assert result['success'] is True
            assert result['exists'] is True
            assert result['is_file'] is False
            assert result['is_directory'] is True
            
            # Check non-existent
            result = executor.execute_action({
                'type': 'check_file_exists',
                'path': 'nonexistent.txt'
            })
            assert result['success'] is True
            assert result['exists'] is False
            
    def test_tail_file(self):
        """Test tailing file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            
            # Create file with multiple lines
            lines = [f"Line {i}\n" for i in range(1, 101)]
            (workspace / 'log.txt').write_text(''.join(lines))
            
            executor = ActionExecutor(workspace)
            result = executor.execute_action({
                'type': 'tail_file',
                'path': 'log.txt',
                'lines': 10
            })
            
            assert result['success'] is True
            assert result['lines_returned'] == 10
            assert result['total_lines'] == 100
            assert 'Line 91' in result['content']
            assert 'Line 100' in result['content']
            
    def test_head_file(self):
        """Test heading file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            
            # Create file with multiple lines
            lines = [f"Line {i}\n" for i in range(1, 101)]
            (workspace / 'log.txt').write_text(''.join(lines))
            
            executor = ActionExecutor(workspace)
            result = executor.execute_action({
                'type': 'head_file',
                'path': 'log.txt',
                'lines': 5
            })
            
            assert result['success'] is True
            assert result['lines_returned'] == 5
            assert 'Line 1' in result['content']
            assert 'Line 5' in result['content']
            assert 'Line 6' not in result['content']
            
    def test_grep_file(self):
        """Test grepping file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            
            content = """Line 1: Hello
Line 2: World
Line 3: Hello World
Line 4: Goodbye"""
            (workspace / 'test.txt').write_text(content)
            
            executor = ActionExecutor(workspace)
            result = executor.execute_action({
                'type': 'grep_file',
                'path': 'test.txt',
                'pattern': 'Hello'
            })
            
            assert result['success'] is True
            assert result['match_count'] == 2
            assert len(result['matches']) == 2
            
            # Check match details
            assert result['matches'][0]['line_number'] == 1
            assert result['matches'][0]['content'] == 'Line 1: Hello'
            assert result['matches'][1]['line_number'] == 3
            assert result['matches'][1]['content'] == 'Line 3: Hello World'
            
    def test_unknown_action(self):
        """Test unknown action type."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            
            executor = ActionExecutor(workspace)
            result = executor.execute_action({
                'type': 'unknown_action'
            })
            
            assert result['success'] is False
            assert 'Unknown action type' in result['error']
