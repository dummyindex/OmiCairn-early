"""Logging utilities."""

import logging
import sys
from pathlib import Path
from typing import Optional
from rich.logging import RichHandler
from config import config


def setup_logger(
    name: str = "omicairn_agent",
    log_file: Optional[Path] = None,
    level: Optional[str] = None
) -> logging.Logger:
    """Set up a logger with rich formatting."""
    logger = logging.getLogger(name)
    
    # Clear existing handlers
    logger.handlers.clear()
    
    # Set level
    log_level = level or config.log_level
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # Console handler with rich formatting
    console_handler = RichHandler(
        rich_tracebacks=True,
        markup=True,
        show_time=True,
        show_path=False
    )
    console_handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(console_handler)
    
    # File handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(logging.Formatter(config.log_format))
        logger.addHandler(file_handler)
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance."""
    return logging.getLogger(f"omicairn_agent.{name}")