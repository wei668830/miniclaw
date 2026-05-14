
# Maximum file size to read into memory (1GB)
MAX_FILE_READ_BYTES = 1024 * 1024 * 1024

def read_file_safe(
    file_path: str,
    max_bytes: int = MAX_FILE_READ_BYTES,
) -> str:
    """Read file with Unicode error handling and memory protection.

    Args:
        file_path: Path to the file.
        max_bytes: Maximum bytes to read into memory (default 1GB).

    Returns:
        File content as string (up to max_bytes).
    """
    # Use utf-8-sig to auto-remove BOM if present, compatible with plain utf-8
    try:
        with open(file_path, "r", encoding="utf-8-sig") as f:
            return f.read(max_bytes)
    except UnicodeDecodeError:
        with open(file_path, "r", encoding="utf-8-sig", errors="ignore") as f:
            return f.read(max_bytes)