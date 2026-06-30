"""
Atomic JSON file I/O helper.
Writes to a temporary file then atomically renames (os.replace) to prevent
corruption from crashes or concurrent access within a single process.
"""
import json
import os
import threading
from pathlib import Path
from typing import Any

# Global file lock for cross-store serialization (single process only)
_file_lock = threading.Lock()


def atomic_read(path: Path) -> Any:
    """Read a JSON file. Returns [] if file doesn't exist or is corrupted."""
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def atomic_write(path: Path, data: Any) -> None:
    """Write JSON atomically: write to .tmp first, then os.replace (atomic on same filesystem)."""
    tmp_path = path.with_suffix(".json.tmp")
    with _file_lock:
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(str(tmp_path), str(path))
