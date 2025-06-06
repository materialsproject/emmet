import pytest
import time
import os
import signal
from unittest.mock import patch
import psutil
from datetime import datetime, timedelta
from emmet.cli.task_manager import TaskManager, _is_process_running
from emmet.cli.state_manager import StateManager


def task_test_function():
    """Simple function to use as a test task"""
    return "completed"


def long_task_test_function():
    """A task that takes longer to complete"""
    time.sleep(1)
    return "completed"


def infinite_task_function():
    """A task that runs indefinitely until terminated"""
    while True:
        time.sleep(0.1)


def failing_task_test_function():
    """Task that raises an exception"""
    raise ValueError("Task failed")


class MockProcess:
    def __init__(self, is_running=True, status=psutil.STATUS_RUNNING):
        self._is_running = is_running
        self._status = status

    def is_running(self):
        return self._is_running

    def status(self):
        return self._status


class MockDateTime:
    """Helper class to mock datetime.now() with a specific time"""

    def __init__(self, current_time):
        self._current_time = current_time

    def now(self):
        return self._current_time

    @staticmethod
    def fromisoformat(date_string):
        # Delegate to the real datetime.fromisoformat
        return datetime.fromisoformat(date_string)


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
        task_id1, timeout=2, check_interval=0.1
    )
    assert status1["status"] == "completed"

    # Start and complete second task
    task_id2 = task_manager.start_task(task_test_function)
    status2 = task_manager.wait_for_task_completion(
        task_id2, timeout=2, check_interval=0.1
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


def test_terminated_task_detection(task_manager):
    """Test detection of terminated tasks."""
    # Start a long-running task
    task_id = task_manager.start_task(infinite_task_function)

    # Wait for the detached process to start
    time.sleep(0.5)

    # Get the detached PID
    status = task_manager.get_task_status(task_id)
    assert "detached_pid" in status
    pid = status["detached_pid"]

    # Verify the process is running
    assert _is_process_running(pid)
    assert task_manager.is_task_running(task_id)

    # Terminate the process
    os.kill(pid, signal.SIGTERM)

    # Give some time for the termination to be processed
    time.sleep(0.1)

    # Verify the task is detected as terminated
    assert not task_manager.is_task_running(task_id)
    final_status = task_manager.get_task_status(task_id)
    assert final_status["status"] == "terminated"
    assert "completed_at" in final_status
    assert "error" in final_status
    assert "terminated unexpectedly" in final_status["error"].lower()


def test_terminated_task_wait_completion(task_manager):
    """Test that wait_for_task_completion properly handles terminated tasks."""
    task_id = task_manager.start_task(infinite_task_function)

    # Wait for the detached process to start
    time.sleep(0.5)

    # Mock the process as not running
    mock_dead = MockProcess(is_running=False, status=psutil.STATUS_DEAD)

    with patch("psutil.Process", return_value=mock_dead):
        # First check should mark it as terminated
        assert not task_manager.is_task_running(task_id)
        # Now wait_for_task_completion should see the terminated status
        final_status = task_manager.wait_for_task_completion(task_id, timeout=1)
        assert final_status["status"] == "terminated"
        assert "completed_at" in final_status
        assert "error" in final_status


def test_zombie_process_detection():
    """Test that zombie processes are properly detected as not running."""
    # Mock a zombie process
    mock_zombie = MockProcess(is_running=True, status=psutil.STATUS_ZOMBIE)

    with patch("psutil.Process", return_value=mock_zombie):
        assert not _is_process_running(999)  # Any PID will do as we're mocking


def test_process_permission_denied():
    """Test handling of permission denied when checking process status."""

    def mock_process(*args):
        raise psutil.AccessDenied()

    with patch("psutil.Process", side_effect=mock_process):
        # Should return False and log a warning when access is denied
        assert not _is_process_running(999)


def test_no_such_process():
    """Test handling of non-existent processes."""

    def mock_process(*args):
        raise psutil.NoSuchProcess(999)

    with patch("psutil.Process", side_effect=mock_process):
        assert not _is_process_running(999)


def test_zombie_process_task_status(task_manager):
    """Test that tasks with zombie processes are marked as terminated."""
    task_id = task_manager.start_task(infinite_task_function)

    # Wait for the detached process to start
    time.sleep(0.5)

    # Mock the process as a zombie
    mock_zombie = MockProcess(is_running=True, status=psutil.STATUS_ZOMBIE)

    with patch("psutil.Process", return_value=mock_zombie):
        # Check if task is running should detect zombie and mark as terminated
        assert not task_manager.is_task_running(task_id)
        final_status = task_manager.get_task_status(task_id)
        assert final_status["status"] == "terminated"
        assert "completed_at" in final_status
        assert "error" in final_status


def test_permission_denied_task_status(task_manager):
    """Test task status handling when process check permission is denied."""
    task_id = task_manager.start_task(infinite_task_function)

    # Wait for the detached process to start
    time.sleep(0.5)

    def mock_process(*args):
        raise psutil.AccessDenied()

    with patch("psutil.Process", side_effect=mock_process):
        # Even with access denied, the task should be considered not running
        assert not task_manager.is_task_running(task_id)
        final_status = task_manager.get_task_status(task_id)
        assert final_status["status"] == "terminated"
        assert "completed_at" in final_status
        assert "error" in final_status


@pytest.mark.parametrize(
    "process_status",
    [
        psutil.STATUS_DEAD,
        psutil.STATUS_STOPPED,
        psutil.STATUS_TRACING_STOP,
    ],
)
def test_various_process_states(process_status):
    """Test handling of various non-running process states."""
    # For these states, is_running() should return False to indicate the process is not active
    mock_process = MockProcess(is_running=False, status=process_status)

    with patch("psutil.Process", return_value=mock_process):
        # Any non-running state should be detected
        assert not _is_process_running(999)


def test_initial_pid_grace_period(task_manager):
    """Test that tasks with only initial PID get proper grace period."""
    task_id = task_manager.start_task(infinite_task_function)

    # Set up our initial time just after task start
    start_time = datetime.now()

    # Within grace period - process should appear running
    within_grace = TaskManager.DETACH_GRACE_PERIOD * 0.6
    mock_now = MockDateTime(start_time + timedelta(seconds=within_grace))

    mock_running_process = MockProcess(is_running=True)
    with patch("psutil.Process", return_value=mock_running_process):
        with patch("emmet.cli.task_manager.datetime", mock_now):
            # Should still be considered running within grace period
            assert task_manager.is_task_running(task_id)
            status = task_manager.get_task_status(task_id)
            assert status["status"] == "running"

    # After grace period - process should appear not running
    after_grace = TaskManager.DETACH_GRACE_PERIOD * 1.2
    mock_now = MockDateTime(start_time + timedelta(seconds=after_grace))

    mock_dead_process = MockProcess(is_running=False)
    with patch("psutil.Process", return_value=mock_dead_process):
        with patch("emmet.cli.task_manager.datetime", mock_now):
            # Should be marked as terminated after grace period
            assert not task_manager.is_task_running(task_id)
            status = task_manager.get_task_status(task_id)
            assert status["status"] == "terminated"
            assert "failed to detach" in status["error"].lower()


def test_no_pid_grace_period(task_manager):
    """Test that tasks with no PID get proper grace period."""
    task_id = task_manager.start_task(infinite_task_function)

    # Simulate a task that hasn't registered any PID yet
    tasks = task_manager.state_manager.get("tasks", {})
    tasks[task_id] = {"status": "running", "started_at": datetime.now().isoformat()}
    task_manager.state_manager.set("tasks", tasks)

    # Set up our initial time just after task start
    start_time = datetime.now()

    # Test within grace period (at 50% of grace period)
    within_grace = TaskManager.INIT_GRACE_PERIOD * 0.5
    mock_now = MockDateTime(start_time + timedelta(seconds=within_grace))
    with patch("emmet.cli.task_manager.datetime", mock_now):
        # Should still be considered running within grace period
        assert task_manager.is_task_running(task_id)
        status = task_manager.get_task_status(task_id)
        assert status["status"] == "running"

    # Test after grace period (50% past grace period)
    after_grace = TaskManager.INIT_GRACE_PERIOD * 1.5
    mock_now = MockDateTime(start_time + timedelta(seconds=after_grace))
    with patch("emmet.cli.task_manager.datetime", mock_now):
        # Should be marked as terminated after grace period
        assert not task_manager.is_task_running(task_id)
        status = task_manager.get_task_status(task_id)
        assert status["status"] == "terminated"
        assert "before initialization completed" in status["error"].lower()


def test_missing_start_time(task_manager):
    """Test handling of tasks with missing start time."""
    task_id = task_manager.start_task(infinite_task_function)

    # Simulate a task with no start time
    tasks = task_manager.state_manager.get("tasks", {})
    tasks[task_id] = {"status": "running", "initial_pid": 12345}  # Some dummy PID
    task_manager.state_manager.set("tasks", tasks)

    # Should be marked as terminated immediately
    assert not task_manager.is_task_running(task_id)
    status = task_manager.get_task_status(task_id)
    assert status["status"] == "terminated"
    assert "no start time recorded" in status["error"].lower()


@pytest.mark.parametrize(
    "time_factor,expected_running",
    [
        (0.5, True),  # 50% of grace period - should be running
        (1.5, False),  # 50% past grace period - should be terminated
        (2.0, False),  # Double grace period - should be terminated
    ],
)
def test_no_pid_various_times(task_manager, time_factor, expected_running):
    """Test task status at various times when no PID is registered."""
    task_id = task_manager.start_task(infinite_task_function)

    # Simulate a task that hasn't registered any PID yet
    start_time = datetime.now()
    tasks = task_manager.state_manager.get("tasks", {})
    tasks[task_id] = {"status": "running", "started_at": start_time.isoformat()}
    task_manager.state_manager.set("tasks", tasks)

    # Test at the specified time
    elapsed_time = TaskManager.INIT_GRACE_PERIOD * time_factor
    mock_now = MockDateTime(start_time + timedelta(seconds=elapsed_time))
    with patch("emmet.cli.task_manager.datetime", mock_now):
        assert task_manager.is_task_running(task_id) == expected_running
        status = task_manager.get_task_status(task_id)
        if not expected_running:
            assert status["status"] == "terminated"


def test_terminate_running_task(task_manager):
    """Test terminating a running task."""
    task_id = task_manager.start_task(infinite_task_function)

    # Wait for the detached process to start
    time.sleep(0.5)

    # Get initial status
    status = task_manager.get_task_status(task_id)
    assert status["status"] == "running"
    assert "detached_pid" in status

    # Terminate the task
    final_status = task_manager.terminate_task(task_id)
    assert final_status["status"] == "terminated"
    assert "completed_at" in final_status
    assert "error" in final_status
    assert "terminated by user request" in final_status["error"].lower()

    # Verify the task is no longer running
    assert not task_manager.is_task_running(task_id)


def test_terminate_nonexistent_task(task_manager):
    """Test attempting to terminate a nonexistent task."""
    status = task_manager.terminate_task("nonexistent-task")
    assert status["status"] == "not_found"


def test_terminate_completed_task(task_manager):
    """Test attempting to terminate an already completed task."""
    task_id = task_manager.start_task(task_test_function)

    # Wait for task to complete
    task_manager.wait_for_task_completion(task_id, timeout=1)

    # Try to terminate the completed task
    status = task_manager.terminate_task(task_id)
    assert status["status"] == "completed"
    assert "result" in status
    assert status["result"] == "completed"


def test_terminate_failed_task(task_manager):
    """Test attempting to terminate a failed task."""
    task_id = task_manager.start_task(failing_task_test_function)

    # Wait for task to fail
    task_manager.wait_for_task_completion(task_id, timeout=1)

    # Try to terminate the failed task
    status = task_manager.terminate_task(task_id)
    assert status["status"] == "failed"
    assert "error" in status
    assert "Task failed" in status["error"]


def test_terminate_already_terminated_task(task_manager):
    """Test attempting to terminate an already terminated task."""
    task_id = task_manager.start_task(infinite_task_function)

    # Wait for the detached process to start
    time.sleep(0.5)

    # Terminate the task first time
    first_status = task_manager.terminate_task(task_id)
    assert first_status["status"] == "terminated"

    # Try to terminate again
    second_status = task_manager.terminate_task(task_id)
    assert second_status["status"] == "terminated"
    assert second_status == first_status  # Should return the same status


def test_terminate_task_with_only_initial_pid(task_manager):
    """Test terminating a task that only has initial PID."""
    task_id = task_manager.start_task(infinite_task_function)

    # Immediately try to terminate before detached PID is set
    status = task_manager.terminate_task(task_id)
    assert status["status"] == "terminated"
    assert "error" in status
    assert "terminated by user request" in status["error"].lower()

    # Verify the task is no longer running
    assert not task_manager.is_task_running(task_id)


@pytest.mark.parametrize(
    "exception_class",
    [
        psutil.NoSuchProcess,
        psutil.AccessDenied,
        lambda pid: psutil.TimeoutExpired(pid),  # TimeoutExpired needs special handling
    ],
)
def test_terminate_task_with_process_errors(task_manager, exception_class):
    """Test terminating a task when process operations raise exceptions."""
    task_id = task_manager.start_task(infinite_task_function)

    # Wait for the detached process to start
    time.sleep(0.5)

    def mock_process(*args):
        pid = args[0]  # Get the actual PID being passed
        if exception_class == psutil.TimeoutExpired:
            raise exception_class(pid)
        raise exception_class(pid=pid)

    with patch("psutil.Process", side_effect=mock_process):
        status = task_manager.terminate_task(task_id)
        assert status["status"] == "terminated"
        assert "error" in status
        assert "terminated by user request" in status["error"].lower()


def test_sequential_task_termination(task_manager):
    """Test terminating tasks in sequence."""
    # Start and terminate first task
    task_id1 = task_manager.start_task(infinite_task_function)
    time.sleep(0.5)  # Wait for task to start
    status1 = task_manager.terminate_task(task_id1)
    assert status1["status"] == "terminated"
    assert "terminated by user request" in status1["error"].lower()

    # Start and terminate second task
    task_id2 = task_manager.start_task(infinite_task_function)
    time.sleep(0.5)  # Wait for task to start
    status2 = task_manager.terminate_task(task_id2)
    assert status2["status"] == "terminated"
    assert "terminated by user request" in status2["error"].lower()

    # Verify both tasks remain terminated
    assert task_manager.get_task_status(task_id1)["status"] == "terminated"
    assert task_manager.get_task_status(task_id2)["status"] == "terminated"


def test_terminate_mixed_tasks(task_manager):
    """Test terminating a mix of running, completed, and failed tasks."""
    # Start a task that will complete
    completed_task_id = task_manager.start_task(task_test_function)
    task_manager.wait_for_task_completion(completed_task_id, timeout=2)

    # Start a task that will fail
    failed_task_id = task_manager.start_task(failing_task_test_function)
    task_manager.wait_for_task_completion(failed_task_id, timeout=2)

    # Start a task that will be terminated
    running_task_id = task_manager.start_task(infinite_task_function)
    time.sleep(0.5)  # Wait for task to start

    # Try to terminate all tasks
    completed_status = task_manager.terminate_task(completed_task_id)
    failed_status = task_manager.terminate_task(failed_task_id)
    running_status = task_manager.terminate_task(running_task_id)

    # Verify completed task stays completed
    assert completed_status["status"] == "completed"
    assert completed_status["result"] == "completed"

    # Verify failed task stays failed
    assert failed_status["status"] == "failed"
    assert "Task failed" in failed_status["error"]

    # Verify running task was terminated
    assert running_status["status"] == "terminated"
    assert "terminated by user request" in running_status["error"].lower()


def test_terminate_task_cleanup(task_manager):
    """Test that terminated tasks are properly cleaned up."""
    # Start and terminate a task
    task_id = task_manager.start_task(infinite_task_function)
    time.sleep(0.5)  # Wait for task to start

    # Get the PID before termination
    status = task_manager.get_task_status(task_id)
    assert "detached_pid" in status
    pid = status["detached_pid"]

    # Terminate the task
    task_manager.terminate_task(task_id)

    # Verify the process is no longer running
    assert not _is_process_running(pid)

    # Clean up tasks
    task_manager.cleanup_finished_tasks()

    # Verify task is removed from state
    assert task_manager.get_task_status(task_id)["status"] == "not_found"
