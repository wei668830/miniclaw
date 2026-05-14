import os
from pathlib import Path


def get_current_workspace_dir() -> Path:
    """Get the current working directory for Miniclaw."""
    return Path(os.getcwd())