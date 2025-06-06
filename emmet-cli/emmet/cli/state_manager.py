from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict
import fcntl

logger = logging.getLogger("emmet")


class FileLock:
    """A file-based lock implementation."""

    def __init__(self, lock_file: Path):
        self.lock_file = lock_file
        self.f = None

    def __enter__(self):
        self.f = self.lock_file.open("w")
        fcntl.flock(self.f, fcntl.LOCK_EX)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.f:
            fcntl.flock(self.f, fcntl.LOCK_UN)
            self.f.close()


class StateManager:
    """Manages persistent state for the CLI application."""

    def __init__(self, state_dir: Path | str = Path.home() / ".emmet"):
        # Store only the state file path
        self.state_file = str(Path(state_dir) / "state.json")
        self._ensure_state_dir()

    def _ensure_state_dir(self) -> None:
        """Ensures the state directory exists."""
        Path(self.state_file).parent.mkdir(parents=True, exist_ok=True)

    def _load_state(self) -> Dict[str, Any]:
        """Loads state from disk. Not thread safe."""
        state_path = Path(self.state_file)
        if not state_path.exists():
            return {}
        try:
            with state_path.open("r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            logger.warning("Corrupted state file found, creating new state")
            return {}

    def _save_state(self, state: Dict[str, Any]) -> None:
        """Saves current state to disk. Not thread safe."""
        with Path(self.state_file).open("w") as f:
            json.dump(state, f, indent=2)

    def get(self, key: str, default: Any = None) -> Any:
        """Gets a value from state."""
        with self._state_lock():
            state = self._load_state()
            return state.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Sets a value in state and persists it."""
        with self._state_lock():
            state = self._load_state()
            state[key] = value
            self._save_state(state)

    def _state_lock(self):
        """Context manager for file locking."""
        return FileLock(Path(self.state_file + ".lock"))
