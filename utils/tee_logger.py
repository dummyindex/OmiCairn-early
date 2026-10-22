"""TeeLogger utility for capturing logs to both stdout and file."""

import logging
import sys
from pathlib import Path
from typing import Optional, List, TextIO
from datetime import datetime
import threading


class TeeLogger:
    """Context manager that captures logging output to both stdout and a file.
    
    This class intercepts all logging output and writes it to both the console
    and a specified file. It's thread-safe and preserves the original logging
    configuration when exiting.
    
    Usage:
        with TeeLogger('/path/to/logfile.log'):
            # All logging within this block is captured
            logger.info("This goes to both console and file")
    """
    
    def __init__(
        self, 
        log_file_path: Path,
        level: int = logging.DEBUG,
        format_string: Optional[str] = None,
        append: bool = False
    ):
        """Initialize TeeLogger.
        
        Args:
            log_file_path: Path to the log file
            level: Minimum logging level to capture
            format_string: Custom format string for log messages
            append: Whether to append to existing file or overwrite
        """
        self.log_file_path = Path(log_file_path)
        self.level = level
        self.append = append
        
        # Use default format if not provided
        self.format_string = format_string or (
            '%(asctime)s - %(levelname)-8s - %(name)-40s - %(message)s'
        )
        
        # Thread-safe storage for handlers
        self._lock = threading.Lock()
        self.file_handler = None
        self.original_handlers = []
        self.original_level = None
        
        # Ensure parent directory exists
        self.log_file_path.parent.mkdir(parents=True, exist_ok=True)
        
    def __enter__(self):
        """Enter context manager - set up logging capture."""
        with self._lock:
            # Get root logger
            root_logger = logging.getLogger()
            
            # Save original configuration
            self.original_level = root_logger.level
            self.original_handlers = root_logger.handlers.copy()
            
            # Set minimum level to capture all messages
            root_logger.setLevel(min(self.level, root_logger.level))
            
            # Create file handler
            mode = 'a' if self.append else 'w'
            self.file_handler = logging.FileHandler(
                self.log_file_path, 
                mode=mode,
                encoding='utf-8'
            )
            self.file_handler.setLevel(self.level)
            
            # Create formatter
            formatter = logging.Formatter(self.format_string)
            self.file_handler.setFormatter(formatter)
            
            # Add file handler
            root_logger.addHandler(self.file_handler)
            
            # Log session start
            root_logger.info(f"="*80)
            root_logger.info(f"Logging session started at {datetime.now().isoformat()}")
            root_logger.info(f"Log file: {self.log_file_path}")
            root_logger.info(f"="*80)
            
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager - restore original logging configuration."""
        with self._lock:
            root_logger = logging.getLogger()
            
            # Log session end
            root_logger.info(f"="*80)
            root_logger.info(f"Logging session ended at {datetime.now().isoformat()}")
            if exc_type:
                root_logger.error(f"Session ended with exception: {exc_type.__name__}: {exc_val}")
            root_logger.info(f"="*80)
            
            # Close and remove file handler
            if self.file_handler:
                self.file_handler.close()
                root_logger.removeHandler(self.file_handler)
                self.file_handler = None
            
            # Restore original handlers
            # First remove all current handlers
            for handler in root_logger.handlers[:]:
                root_logger.removeHandler(handler)
            
            # Then add back the original handlers
            for handler in self.original_handlers:
                root_logger.addHandler(handler)
            
            # Restore original level
            if self.original_level is not None:
                root_logger.setLevel(self.original_level)
    
    def flush(self):
        """Flush the file handler to ensure all logs are written."""
        if self.file_handler:
            self.file_handler.flush()


class MultiStreamHandler(logging.Handler):
    """Handler that writes to multiple streams simultaneously."""
    
    def __init__(self, streams: List[TextIO], level=logging.NOTSET):
        """Initialize with multiple output streams."""
        super().__init__(level)
        self.streams = streams
        self._lock = threading.Lock()
    
    def emit(self, record):
        """Emit a record to all streams."""
        try:
            msg = self.format(record)
            with self._lock:
                for stream in self.streams:
                    stream.write(msg + '\n')
                    if hasattr(stream, 'flush'):
                        stream.flush()
        except Exception:
            self.handleError(record)


def setup_logging_capture(
    log_file_path: Path,
    console_level: int = logging.INFO,
    file_level: int = logging.DEBUG,
    format_string: Optional[str] = None
) -> logging.FileHandler:
    """Set up logging to capture to both console and file.
    
    This is an alternative to TeeLogger that doesn't use context manager.
    
    Args:
        log_file_path: Path to log file
        console_level: Logging level for console output
        file_level: Logging level for file output
        format_string: Format string for log messages
        
    Returns:
        The file handler (can be used to close it later)
    """
    # Ensure parent directory exists
    log_file_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Create formatters
    format_str = format_string or '%(asctime)s - %(levelname)-8s - %(name)-40s - %(message)s'
    formatter = logging.Formatter(format_str)
    
    # Create file handler
    file_handler = logging.FileHandler(log_file_path, mode='w', encoding='utf-8')
    file_handler.setLevel(file_level)
    file_handler.setFormatter(formatter)
    
    # Add to root logger
    root_logger = logging.getLogger()
    root_logger.addHandler(file_handler)
    
    # Ensure root logger level allows all messages
    if root_logger.level > file_level:
        root_logger.setLevel(file_level)
    
    # Log start
    root_logger.info(f"="*80)
    root_logger.info(f"Logging capture started at {datetime.now().isoformat()}")
    root_logger.info(f"Log file: {log_file_path}")
    root_logger.info(f"="*80)
    
    return file_handler