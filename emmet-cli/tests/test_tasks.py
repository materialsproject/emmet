from emmet.cli.tasks import tasks
from emmet.cli.utils import EmmetCliError
import time


def mock_task_function():
    """Simple function that returns a result."""
    return "test result"


def failing_task_function():
    """Function that raises an exception."""
    raise ValueError("Test error")


def slow_task_function():
    import time

    time.sleep(2)
    return "done"


def test_status_command_completed_task(cli_runner, task_manager):
    """Test status command for a completed task."""
    task_id = task_manager.start_task(mock_task_function)
    task_manager.wait_for_task_completion(task_id)

    result = cli_runner(tasks, ["status", task_id])
    assert result.exit_code == 0
    assert "completed" in result.output.lower()
    assert "test result" in result.output


def test_status_command_failed_task(cli_runner, task_manager):
    """Test status command for a failed task."""
    task_id = task_manager.start_task(failing_task_function)
    task_manager.wait_for_task_completion(task_id)

    result = cli_runner(tasks, ["status", task_id])
    assert result.exit_code == 0
    assert "failed" in result.output.lower()
    assert "Test error" in result.output


def test_status_command_invalid_id(cli_runner):
    """Test status command with an invalid task ID."""
    result = cli_runner(tasks, ["status", "invalid-uuid"])
    assert result.exit_code != 0
    assert isinstance(result.exception, EmmetCliError)
    assert "Invalid task ID" in str(result.exception)


def test_list_command_no_tasks(cli_runner, task_manager):
    """Test list command when no tasks exist."""
    result = cli_runner(tasks, ["list"])
    assert result.exit_code == 0
    assert "no tasks found" in result.output.lower()


def test_list_command_with_tasks(cli_runner, task_manager):
    """Test list command with multiple tasks."""
    # Create a completed task
    task_id1 = task_manager.start_task(mock_task_function)
    task_manager.wait_for_task_completion(task_id1)

    # Create a failed task
    task_id2 = task_manager.start_task(failing_task_function)
    task_manager.wait_for_task_completion(task_id2)

    result = cli_runner(tasks, ["list"])
    assert result.exit_code == 0
    assert task_id1 in result.output
    assert task_id2 in result.output
    assert "completed" in result.output.lower()
    assert "failed" in result.output.lower()


def test_wait_command_completed_task(cli_runner, task_manager):
    """Test wait command for a completed task."""
    task_id = task_manager.start_task(mock_task_function)

    result = cli_runner(tasks, ["wait", task_id])
    assert result.exit_code == 0
    assert "completed successfully" in result.output.lower()
    assert "test result" in result.output


def test_wait_command_failed_task(cli_runner, task_manager):
    """Test wait command for a failed task."""
    task_id = task_manager.start_task(failing_task_function)

    result = cli_runner(tasks, ["wait", task_id])
    assert result.exit_code == 0
    assert "failed" in result.output.lower()
    assert "Test error" in result.output


def test_wait_command_with_timeout(cli_runner, task_manager):
    """Test wait command with a timeout."""

    task_id = task_manager.start_task(slow_task_function)

    result = cli_runner(tasks, ["wait", task_id, "--timeout", "0.1"])
    assert result.exit_code == 0
    assert "did not complete" in result.output.lower()


def test_clean_command(cli_runner, task_manager):
    """Test clean command."""
    # Create and complete some tasks
    task_id1 = task_manager.start_task(mock_task_function)
    task_id2 = task_manager.start_task(failing_task_function)

    task_manager.wait_for_task_completion(task_id1)
    task_manager.wait_for_task_completion(task_id2)

    result = cli_runner(tasks, ["clean"])
    assert result.exit_code == 0
    assert "cleaned up" in result.output.lower()

    # Verify tasks were cleaned up
    tasks_after = task_manager.state_manager.get("tasks", {})
    assert len(tasks_after) == 0


def test_terminate_command_running_task(cli_runner, task_manager):
    """Test terminate command for a running task."""
    task_id = task_manager.start_task(slow_task_function)
    time.sleep(0.5)  # Wait for task to start

    # Test with force flag to skip confirmation
    result = cli_runner(tasks, ["terminate", task_id, "--force"])
    assert result.exit_code == 0
    assert "has been terminated" in result.output.lower()

    # Verify task is terminated
    status = task_manager.get_task_status(task_id)
    assert status["status"] == "terminated"


def test_terminate_command_completed_task(cli_runner, task_manager):
    """Test terminate command for an already completed task."""
    task_id = task_manager.start_task(mock_task_function)
    task_manager.wait_for_task_completion(task_id)

    result = cli_runner(tasks, ["terminate", task_id])
    assert result.exit_code == 0
    assert "is not running" in result.output.lower()
    assert "completed" in result.output.lower()


def test_terminate_command_failed_task(cli_runner, task_manager):
    """Test terminate command for a failed task."""
    task_id = task_manager.start_task(failing_task_function)
    task_manager.wait_for_task_completion(task_id)

    result = cli_runner(tasks, ["terminate", task_id])
    assert result.exit_code == 0
    assert "is not running" in result.output.lower()
    assert "failed" in result.output.lower()


def test_terminate_command_nonexistent_task(cli_runner, task_manager):
    """Test terminate command with a nonexistent task ID."""
    result = cli_runner(tasks, ["terminate", "nonexistent-uuid"])
    assert result.exit_code != 0
    assert isinstance(result.exception, EmmetCliError)
    assert "Invalid task ID" in str(result.exception)


def test_terminate_command_confirmation(cli_runner, task_manager, monkeypatch):
    """Test terminate command with user confirmation."""
    task_id = task_manager.start_task(slow_task_function)
    time.sleep(0.5)  # Wait for task to start

    # Test with 'y' confirmation
    result = cli_runner(tasks, ["terminate", task_id], input="y\n")
    assert result.exit_code == 0
    assert "has been terminated" in result.output.lower()

    # Start another task
    task_id = task_manager.start_task(slow_task_function)
    time.sleep(0.5)  # Wait for task to start

    # Test with 'n' confirmation
    result = cli_runner(tasks, ["terminate", task_id], input="n\n")
    assert result.exit_code == 0
    assert "operation cancelled" in result.output.lower()

    # Verify task is still running
    status = task_manager.get_task_status(task_id)
    assert status["status"] == "running"


def test_terminate_command_invalid_uuid(cli_runner, task_manager):
    """Test terminate command with an invalid UUID format."""
    result = cli_runner(tasks, ["terminate", "not-a-uuid"])
    assert result.exit_code != 0
    assert isinstance(result.exception, EmmetCliError)
    assert "Invalid task ID" in str(result.exception)
