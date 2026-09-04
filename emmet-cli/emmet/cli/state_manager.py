from __future__ import annotations

import fcntl
import json
import logging
import os
from pathlib import Path
from typing import Any, Callable, Self, TextIO
from uuid import uuid4

logger = logging.getLogger("emmet")


class FileLock:
    """A file-based lock implementation."""

    def __init__(self, lock_file: Path) -> None:
        self.lock_file = lock_file
        self.f: TextIO | None = None

    def __enter__(self) -> Self:
        self.f = self.lock_file.open("w")
        if self.f is not None:
            fcntl.flock(self.f, fcntl.LOCK_EX)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self.f is not None:
            fcntl.flock(self.f, fcntl.LOCK_UN)
            self.f.close()


class StateManager:
    """Manages persistent state for the CLI application."""

    def __init__(self, state_dir: Path | str = Path.home() / ".emmet"):
        self.state_dir = Path(state_dir)
        self.state_file = str(self.state_dir / "state.json")
        self._ensure_state_dir()

    def _ensure_state_dir(self) -> None:
        """Ensures the state directory exists."""
        self.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.state_dir.chmod(0o700)

    def _load_state(self) -> dict[str, Any]:
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

    def _save_state(self, state: dict[str, Any]) -> None:
        """Saves current state to disk. Not thread safe."""
        state_path = Path(self.state_file)
        temporary_path = state_path.with_name(f".{state_path.name}.{uuid4().hex}.tmp")
        descriptor = os.open(
            temporary_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
        )
        try:
            try:
                state_file = os.fdopen(descriptor, "w")
            except Exception:
                os.close(descriptor)
                raise
            with state_file as f:
                json.dump(state, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporary_path, state_path)
            try:
                directory_descriptor = os.open(
                    state_path.parent, os.O_RDONLY | os.O_DIRECTORY
                )
                try:
                    os.fsync(directory_descriptor)
                finally:
                    os.close(directory_descriptor)
            except OSError:
                logger.warning(
                    "State was saved, but its directory entry could not be synced."
                )
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise

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

    def update(self, key: str, updater: Callable[[Any], Any]) -> Any:
        """Atomically update one top-level state value and return the new value."""
        with self._state_lock():
            state = self._load_state()
            value = updater(state.get(key))
            state[key] = value
            self._save_state(state)
            return value

    def _state_lock(self) -> FileLock:
        """Context manager for file locking."""
        return FileLock(Path(self.state_file + ".lock"))
