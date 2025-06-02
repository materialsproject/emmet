from emmet.cli.tasks import tasks
from emmet.cli.utils import EmmetCliError


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
