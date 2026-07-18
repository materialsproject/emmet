import json
import os
import stat
from pathlib import Path
import pytest
from emmet.cli.state_manager import StateManager


def test_init_creates_state_dir(temp_state_dir):
    """Test that initialization creates the state directory."""
    manager = StateManager(state_dir=temp_state_dir)
    assert temp_state_dir.exists()
    assert temp_state_dir.is_dir()
    assert manager.state_dir == temp_state_dir


def test_state_dir_is_private_with_permissive_umask(tmp_path):
    state_dir = tmp_path / "permissive-umask"
    previous_umask = os.umask(0)
    try:
        StateManager(state_dir=state_dir)
    finally:
        os.umask(previous_umask)

    assert stat.S_IMODE(state_dir.stat().st_mode) == 0o700


def test_load_empty_state(state_manager):
    """Test loading state when no state file exists."""
    assert state_manager._load_state() == {}


def test_load_corrupted_state(temp_state_dir):
    """Test loading state when state file is corrupted."""
    state_file = temp_state_dir / "state.json"
    temp_state_dir.mkdir(parents=True, exist_ok=True)
    state_file.write_text("invalid json")

    manager = StateManager(state_dir=temp_state_dir)
    assert manager._load_state() == {}


def test_get_nonexistent_key(state_manager):
    """Test getting a nonexistent key returns default value."""
    assert state_manager.get("nonexistent") is None
    assert state_manager.get("nonexistent", "default") == "default"


def test_set_and_get(state_manager):
    """Test setting and getting a value."""
    state_manager.set("test_key", "test_value")
    assert state_manager.get("test_key") == "test_value"

    # Verify persistence
    assert (
        json.loads(Path(state_manager.state_file).read_text())["test_key"]
        == "test_value"
    )
    assert stat.S_IMODE(Path(state_manager.state_file).stat().st_mode) == 0o600


def test_update_atomically_transforms_value(state_manager, monkeypatch):
    state_manager.set("other_key", "preserved")
    load_calls = 0
    save_calls = 0
    original_load = state_manager._load_state
    original_save = state_manager._save_state

    def load_state():
        nonlocal load_calls
        load_calls += 1
        return original_load()

    def save_state(state):
        nonlocal save_calls
        save_calls += 1
        original_save(state)

    monkeypatch.setattr(state_manager, "_load_state", load_state)
    monkeypatch.setattr(state_manager, "_save_state", save_state)

    updated = state_manager.update("items", lambda value: [*(value or []), "new"])

    assert updated == ["new"]
    assert load_calls == 1
    assert save_calls == 1
    assert state_manager.get("items") == ["new"]
    assert state_manager.get("other_key") == "preserved"


def test_save_state_closes_descriptor_if_fdopen_fails(state_manager, monkeypatch):
    original_open = os.open
    original_close = os.close
    opened_descriptors = []
    closed_descriptors = []

    def tracked_open(*args, **kwargs):
        descriptor = original_open(*args, **kwargs)
        opened_descriptors.append(descriptor)
        return descriptor

    def tracked_close(descriptor):
        closed_descriptors.append(descriptor)
        original_close(descriptor)

    def fail_fdopen(*args, **kwargs):
        raise OSError("fdopen failed")

    monkeypatch.setattr(os, "open", tracked_open)
    monkeypatch.setattr(os, "close", tracked_close)
    monkeypatch.setattr(os, "fdopen", fail_fdopen)

    with pytest.raises(OSError, match="fdopen failed"):
        state_manager._save_state({"key": "value"})

    assert closed_descriptors == opened_descriptors


def test_save_state_failure_preserves_existing_state(state_manager, monkeypatch):
    state_manager._save_state({"session": "existing"})
    state_path = Path(state_manager.state_file)
    original_contents = state_path.read_text()

    def fail_dump(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(json, "dump", fail_dump)

    with pytest.raises(OSError, match="disk full"):
        state_manager._save_state({"session": "replacement"})

    assert state_path.read_text() == original_contents
    assert list(state_path.parent.glob(".state.json.*.tmp")) == []


def test_save_state_fsyncs_file_and_directory(state_manager, monkeypatch):
    original_fsync = os.fsync
    fsynced_modes = []

    def track_fsync(descriptor):
        fsynced_modes.append(os.fstat(descriptor).st_mode)
        original_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", track_fsync)

    state_manager._save_state({"session": "durable"})

    assert stat.S_ISREG(fsynced_modes[0])
    assert stat.S_ISDIR(fsynced_modes[1])


def test_directory_fsync_failure_does_not_report_save_failure(
    state_manager, monkeypatch, caplog
):
    original_fsync = os.fsync

    def fail_directory_fsync(descriptor):
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise OSError("directory sync failed")
        original_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", fail_directory_fsync)

    state_manager._save_state({"session": "persisted"})

    assert state_manager._load_state() == {"session": "persisted"}
    assert "directory entry could not be synced" in caplog.text


def test_save_and_load_state(temp_state_dir):
    """Test that state is properly saved and loaded."""
    manager1 = StateManager(state_dir=temp_state_dir)
    manager1.set("test_key", "test_value")

    # Create new instance to test loading
    manager2 = StateManager(state_dir=temp_state_dir)
    assert manager2.get("test_key") == "test_value"
