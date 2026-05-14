import os
from pathlib import Path


MINICLAW_LOG = """
  __  __ _      _  ___ _             
 |  \/  (_)_ _ (_)/ __| |__ ___ __ __
 | |\/| | | ' \| | (__| / _` \ V  V /
 |_|  |_|_|_||_|_|\___|_\__,_|\_/\_/ 
                                     
"""

class EnvVarLoader:
    """Utility to load and parse environment variables with type safety
    and defaults.
    """

    @staticmethod
    def get_bool(env_var: str, default: bool = False) -> bool:
        """Get a boolean environment variable,
        interpreting common truthy values."""
        val = os.environ.get(env_var, str(default)).lower()
        return val in ("true", "1", "yes")

    @staticmethod
    def get_float(
        env_var: str,
        default: float = 0.0,
        min_value: float | None = None,
        max_value: float | None = None,
        allow_inf: bool = False,
    ) -> float:
        """Get a float environment variable with optional bounds
        and infinity handling."""
        try:
            value = float(os.environ.get(env_var, str(default)))
            if min_value is not None and value < min_value:
                return min_value
            if max_value is not None and value > max_value:
                return max_value
            if not allow_inf and (
                value == float("inf") or value == float("-inf")
            ):
                return default
            return value
        except (TypeError, ValueError):
            return default

    @staticmethod
    def get_int(
        env_var: str,
        default: int = 0,
        min_value: int | None = None,
        max_value: int | None = None,
    ) -> int:
        """Get an integer environment variable with optional bounds."""
        try:
            value = int(os.environ.get(env_var, str(default)))
            if min_value is not None and value < min_value:
                return min_value
            if max_value is not None and value > max_value:
                return max_value
            return value
        except (TypeError, ValueError):
            return default

    @staticmethod
    def get_str(env_var: str, default: str = "") -> str:
        """Get a string environment variable with a default fallback."""
        return os.environ.get(env_var, default)

WORKING_DIR = (
    Path(EnvVarLoader.get_str("MINICLAW_WORKING_DIR", "~/.miniclaw"))
    .expanduser()
    .resolve()
)

# Env to indicate running inside a container (e.g. Docker). Set to 1/true/yes.
RUNNING_IN_CONTAINER = EnvVarLoader.get_bool(
    "MINICLAW_RUNNING_IN_CONTAINER",
    False,
)

# Playwright: use system Chromium when set (e.g. in Docker).
PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH_ENV = "PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH"