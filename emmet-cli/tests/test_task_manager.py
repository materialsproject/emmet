import pytest
import time
from emmet.cli.task_manager import TaskManager
from emmet.cli.state_manager import StateManager


def task_test_function():
    """Simple function to use as a test task"""
    return "completed"


def long_task_test_function():
    """A task that takes longer to complete"""
    time.sleep(1)
    return "completed"


def failing_task_test_function():
    """Task that raises an exception"""
    raise ValueError("Task failed")


@pytest.fixture
def task_manager(temp_state_dir):
    """Creates a TaskManager instance with a temporary state directory."""
    state_manager = StateManager(state_dir=temp_state_dir)
    return TaskManager(state_manager=state_manager, running_status_update_interval=1)


def test_start_task(task_manager):
    """Test starting a new task."""
    task_id = task_manager.start_task(task_test_function)

    assert isinstance(task_id, str)
    initial_status = task_manager.get_task_status(task_id)
    assert initial_status["status"] == "running"
    assert "started_at" in initial_status

    final_status = task_manager.wait_for_task_completion(
        task_id, timeout=1, check_interval=0.1
    )
    assert final_status["status"] == "completed"
    assert final_status["result"] == "completed"
    assert "completed_at" in final_status


def test_failing_task_handling(task_manager):
    """Test handling of a failing task."""
    task_id = task_manager.start_task(failing_task_test_function)

    final_status = task_manager.wait_for_task_completion(
        task_id, timeout=1, check_interval=0.1
    )
    assert final_status["status"] == "failed"
    assert "Task failed" in final_status["error"]
    assert "completed_at" in final_status


def test_task_status_checking(task_manager):
    """Test task status checking functionality."""
    task_id = task_manager.start_task(long_task_test_function)

    # Test initial running status
    assert task_manager.is_task_running(task_id) is True

    # Wait for task to timeout and verify status
    final_status = task_manager.wait_for_task_completion(
        task_id, timeout=0.5, check_interval=0.1
    )
    assert final_status["status"] == "running"

    # Wait for task to complete and verify status
    final_status = task_manager.wait_for_task_completion(
        task_id, timeout=1, check_interval=0.1
    )
    assert final_status["status"] == "completed"

    # Give some time for the process to be cleaned up
    time.sleep(0.1)
    assert task_manager.is_task_running(task_id) is False


def test_nonexistent_task_status(task_manager):
    """Test status checking for non-existent task."""
    status = task_manager.get_task_status("nonexistent-task")
    assert status["status"] == "not_found"

    assert task_manager.is_task_running("nonexistent-task") is False


def test_sequential_tasks(task_manager):
    """Test handling multiple tasks sequentially."""
    # Start and complete first task
    task_id1 = task_manager.start_task(task_test_function)
    status1 = task_manager.wait_for_task_completion(
        task_id1, timeout=1, check_interval=0.1
    )
    assert status1["status"] == "completed"

    # Start and complete second task
    task_id2 = task_manager.start_task(task_test_function)
    status2 = task_manager.wait_for_task_completion(
        task_id2, timeout=1, check_interval=0.1
    )
    assert status2["status"] == "completed"

    # Verify both tasks completed successfully
    assert task_manager.get_task_status(task_id1)["status"] == "completed"
    assert task_manager.get_task_status(task_id2)["status"] == "completed"


def test_task_pid_storage(task_manager):
    """Test that task PIDs are properly stored."""
    # Start a task
    task_id = task_manager.start_task(long_task_test_function)

    # Check initial status
    initial_status = task_manager.get_task_status(task_id)
    assert "initial_pid" in initial_status
    assert isinstance(initial_status["initial_pid"], int)
    assert initial_status["initial_pid"] > 0

    # Wait a bit for the detached process to start and store its PID
    time.sleep(0.5)

    # Check detached status
    detached_status = task_manager.get_task_status(task_id)
    assert "detached_pid" in detached_status
    assert isinstance(detached_status["detached_pid"], int)
    assert detached_status["detached_pid"] > 0

    # Verify the PIDs are different (due to process detachment)
    assert detached_status["detached_pid"] != initial_status["initial_pid"]

    # Wait for task completion
    final_status = task_manager.wait_for_task_completion(task_id)
    assert final_status["status"] == "completed"

    # Verify PIDs are preserved after completion
    assert final_status["initial_pid"] == initial_status["initial_pid"]
    assert final_status["detached_pid"] == detached_status["detached_pid"]


def test_failing_task_pid_storage(task_manager):
    """Test that PIDs are properly stored even for failing tasks."""
    # Start a failing task
    task_id = task_manager.start_task(failing_task_test_function)

    # Check initial status
    initial_status = task_manager.get_task_status(task_id)
    assert "initial_pid" in initial_status
    assert isinstance(initial_status["initial_pid"], int)

    # Wait a bit for the detached process to start and store its PID
    time.sleep(0.5)

    # Check detached status
    detached_status = task_manager.get_task_status(task_id)
    assert "detached_pid" in detached_status
    assert isinstance(detached_status["detached_pid"], int)

    # Wait for task completion
    final_status = task_manager.wait_for_task_completion(task_id)
    assert final_status["status"] == "failed"

    # Verify PIDs are preserved after failure
    assert final_status["initial_pid"] == initial_status["initial_pid"]
    assert final_status["detached_pid"] == detached_status["detached_pid"]
