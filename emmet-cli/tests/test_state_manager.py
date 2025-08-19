import json
from pathlib import Path
from emmet.cli.state_manager import StateManager


def test_init_creates_state_dir(temp_state_dir):
    """Test that initialization creates the state directory."""
    StateManager(state_dir=temp_state_dir)
    assert temp_state_dir.exists()
    assert temp_state_dir.is_dir()


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


def test_save_and_load_state(temp_state_dir):
    """Test that state is properly saved and loaded."""
    manager1 = StateManager(state_dir=temp_state_dir)
    manager1.set("test_key", "test_value")

    # Create new instance to test loading
    manager2 = StateManager(state_dir=temp_state_dir)
    assert manager2.get("test_key") == "test_value"
