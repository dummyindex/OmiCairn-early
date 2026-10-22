"""Configuration settings for OmiCairn Agent Local."""

import os
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from constants import (
    ENV_OPENAI_API_KEY, ENV_OPENAI_MODEL, DEFAULT_OPENAI_MODEL,
    ENV_CLAUDE_API_KEY, ENV_CLAUDE_MODEL, DEFAULT_CLAUDE_MODEL,
    ENV_CLAUDE_MAX_TURNS, ENV_CLAUDE_MAX_COST, ENV_CLAUDE_MAX_TOKENS
)

# Load environment variables
load_dotenv()


class Config(BaseModel):
    """Main configuration class."""
    
    # OpenAI settings
    openai_api_key: str = Field(default_factory=lambda: os.getenv(ENV_OPENAI_API_KEY, ""))
    openai_model: str = Field(default_factory=lambda: os.getenv(ENV_OPENAI_MODEL, DEFAULT_OPENAI_MODEL))
    
    # Claude settings
    claude_api_key: str = Field(default_factory=lambda: os.getenv(ENV_CLAUDE_API_KEY, ""))
    claude_model: str = Field(default_factory=lambda: os.getenv(ENV_CLAUDE_MODEL, DEFAULT_CLAUDE_MODEL))
    claude_max_turns: int = Field(default_factory=lambda: int(os.getenv(ENV_CLAUDE_MAX_TURNS, "5")))
    claude_max_cost: float = Field(default_factory=lambda: float(os.getenv(ENV_CLAUDE_MAX_COST, "0.10")))
    claude_max_tokens: int = Field(default_factory=lambda: int(os.getenv(ENV_CLAUDE_MAX_TOKENS, "50000")))
    
    # Execution settings
    max_nodes: int = Field(default=20)
    max_children_per_node: int = Field(default=3)
    max_debug_trials: int = Field(default=3)
    execution_timeout: int = Field(default=600)  # seconds
    llm_timeout: float = Field(default=300.0)  # 5 minutes default timeout for LLM calls
    bug_fixer_timeout: int = Field(default=1200)  # 20 minutes default timeout for bug fixer
    
    # Docker settings
    python_image: str = Field(default="omicairn-python:local")
    r_image: str = Field(default="omicairn-r:minimal")
    container_memory_limit: str = Field(default="8g")
    container_cpu_limit: float = Field(default=3.0)
    
    # Storage settings
    workspace_dir: Path = Field(default_factory=lambda: Path.home() / ".omicairn_agent_local")
    temp_dir: Path = Field(default_factory=lambda: Path("/tmp/omicairn_agent_local"))
    
    # Logging settings
    log_level: str = Field(default="INFO")
    log_format: str = Field(default="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    
    # Function block settings
    function_block_timeout: int = Field(default=300)  # seconds
    max_retries: int = Field(default=3)
    
    class Config:
        env_prefix = "OMICAIRN_"
        
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Create directories if they don't exist
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
    @property
    def data_dir(self) -> Path:
        """Directory for storing data files."""
        path = self.workspace_dir / "data"
        path.mkdir(exist_ok=True)
        return path
        
    @property
    def logs_dir(self) -> Path:
        """Directory for storing logs."""
        path = self.workspace_dir / "logs"
        path.mkdir(exist_ok=True)
        return path
        
    @property
    def results_dir(self) -> Path:
        """Directory for storing results."""
        path = self.workspace_dir / "results"
        path.mkdir(exist_ok=True)
        return path
        
    @property
    def function_blocks_dir(self) -> Path:
        """Directory for storing function blocks."""
        path = self.workspace_dir / "function_blocks"
        path.mkdir(exist_ok=True)
        return path


# Global config instance
config = Config()