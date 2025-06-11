from __future__ import annotations

import logging
import multiprocessing as mp
from datetime import datetime
import time
import os
from typing import Any, Callable, Literal
from uuid import uuid4
import psutil
from typing import cast

from emmet.cli.state_manager import StateManager

logger = logging.getLogger("emmet")

TaskStatus = Literal["running", "completed", "failed", "terminated", "not_found"]


def _detach_process() -> bool:
    """
    Detach the process using double fork to ensure it becomes independent of the parent.
    Returns True in the parent process, False in the child process.
    """
    try:
        pid = os.fork()
        if pid > 0:
            return True  # Parent
    except OSError:
        return True  # Not on Unix or fork failed, return to parent

    # First child
    try:
        os.setsid()  # Become session leader
        try:
            pid = os.fork()
            if pid > 0:
                os._exit(0)  # Exit first child
        except OSError:
            os._exit(0)
    except OSError:
        os._exit(0)

    # Second child (fully detached)
    try:
        # Close all file descriptors
        os.closerange(3, 256)
    except OSError:
        pass

    return False  # We are in the detached process


def _is_process_running(pid: int) -> bool:
    """
    Check if a process with the given PID is running.
    Returns False if the process is not running or if we don't have permission to check.
    """
    try:
        process = psutil.Process(pid)
        return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False
    except psutil.AccessDenied:
        logger.warning(f"Access denied when checking process {pid}")
        return False


class TaskManager:
    """Manages background tasks and their states."""

    # Time limits for various grace periods (in seconds)
    DETACH_GRACE_PERIOD = 5  # Time to wait for process to detach
    INIT_GRACE_PERIOD = 2  # Time to wait for process to initialize and register PID

    def __init__(
        self,
        state_manager: StateManager,
        running_status_update_interval: int = 30,
    ) -> None:
        """Initialize the TaskManager with an optional StateManager instance."""
        self.state_manager = state_manager
        self.running_status_update_interval = running_status_update_interval

    def _get_current_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        return datetime.now().isoformat()

    def _update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        error: str | None = None,
        result: Any | None = None,
        additional_data: dict[str, Any] | None = None,
    ) -> None:
        """Update task status with common fields."""
        update_data: dict[str, Any] = {"status": status}

        if status in ["completed", "failed", "terminated"]:
            update_data["completed_at"] = self._get_current_timestamp()

        if error is not None:
            update_data["error"] = error

        if result is not None:
            update_data["result"] = result

        if additional_data:
            update_data.update(additional_data)

        self._store_task_result(task_id, update_data)

    def _try_terminate_process(self, pid: int, timeout: int = 3) -> bool:
        """Try to terminate a process with the given PID."""
        try:
            process = psutil.Process(pid)
            process.terminate()
            process.wait(timeout=timeout)
            return True
        except (psutil.NoSuchProcess, psutil.TimeoutExpired, psutil.AccessDenied):
            return False

    def _task_wrapper(
        self, task_id: str, func: Callable[..., Any], *args: Any, **kwargs: Any
    ) -> None:
        """Wrapper function that executes the task and stores its result."""
        if _detach_process():
            return  # Parent process returns immediately

        # Store the detached process PID
        self._update_task_status(
            task_id,
            cast(TaskStatus, "running"),
            additional_data={"detached_pid": os.getpid()},
        )

        try:
            result = func(*args, **kwargs)
            self._update_task_status(
                task_id, cast(TaskStatus, "completed"), result=result
            )
        except Exception as e:
            logger.exception(f"Task {task_id} failed")
            self._update_task_status(task_id, cast(TaskStatus, "failed"), error=str(e))
        finally:
            os._exit(0)

    def _store_task_result(self, task_id: str, result: dict[str, Any]) -> None:
        """Store the task result in the state manager."""
        tasks = self.state_manager.get("tasks", {})
        if task_id not in tasks:
            tasks[task_id] = {}
        tasks[task_id].update(result)
        self.state_manager.set("tasks", tasks)

    def start_task(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> str:
        """Start a new task in a separate, fully detached process."""
        task_id = str(uuid4())

        # Initialize task state
        self._update_task_status(
            task_id,
            cast(TaskStatus, "running"),
            additional_data={"started_at": self._get_current_timestamp()},
        )

        process = mp.Process(
            target=self._task_wrapper,
            args=(task_id, func) + args,
            kwargs=kwargs,
            daemon=False,
        )
        process.start()

        # Store the initial process ID
        self._update_task_status(
            task_id,
            cast(TaskStatus, "running"),
            additional_data={"initial_pid": process.pid},
        )

        return task_id

    def get_task_status(self, task_id: str) -> dict[str, Any]:
        """
        Get the current status of a task.

        Args:
            task_id: The ID of the task to check

        Returns:
            Dict containing the task status and result/error if completed
        """
        tasks = self.state_manager.get("tasks", {})
        return tasks.get(task_id, {"status": "not_found"})

    def wait_for_task_completion(
        self, task_id: str, timeout: float | None = None, check_interval: float = 1.0
    ) -> dict[str, Any]:
        """Helper function to wait for task completion"""
        start_time = time.time()
        while True:
            status = self.get_task_status(task_id)
            if status["status"] in ["completed", "failed"] or not self.is_task_running(
                task_id
            ):
                return status
            if timeout and time.time() - start_time >= timeout:
                return status
            time.sleep(check_interval)

    def _check_process_state(self, task_id: str, status: dict[str, Any]) -> bool:
        """Check the state of a process and update status accordingly."""
        now = datetime.now()

        # Check detached process
        if "detached_pid" in status:
            if not _is_process_running(status["detached_pid"]):
                self._update_task_status(
                    task_id,
                    cast(TaskStatus, "terminated"),
                    error="Process was terminated unexpectedly",
                )
                return False
            return True

        # Check initial process
        if "initial_pid" in status and "started_at" in status:
            start_time = datetime.fromisoformat(status["started_at"])
            elapsed = (now - start_time).total_seconds()

            if elapsed < self.DETACH_GRACE_PERIOD:
                return True

            if not _is_process_running(status["initial_pid"]):
                self._update_task_status(
                    task_id,
                    cast(TaskStatus, "terminated"),
                    error="Process failed to detach and was terminated",
                )
                return False
            return True

        # Check initialization period
        if "started_at" in status:
            start_time = datetime.fromisoformat(status["started_at"])
            elapsed = (now - start_time).total_seconds()

            if elapsed < self.INIT_GRACE_PERIOD:
                return True

            self._update_task_status(
                task_id,
                cast(TaskStatus, "terminated"),
                error="Process was terminated before initialization completed",
            )
            return False

        self._update_task_status(
            task_id,
            cast(TaskStatus, "terminated"),
            error="Invalid task state: no start time recorded",
        )
        return False

    def is_task_running(self, task_id: str) -> bool:
        """Check if a task is still running."""
        status = self.get_task_status(task_id)
        if status["status"] != "running":
            return False

        return self._check_process_state(task_id, status)

    def cleanup_finished_tasks(self) -> None:
        """Remove finished tasks from the state manager."""
        tasks = self.state_manager.get("tasks", {})
        finished_tasks = [
            task_id for task_id in tasks.keys() if not self.is_task_running(task_id)
        ]
        for task_id in finished_tasks:
            del tasks[task_id]
        self.state_manager.set("tasks", tasks)

    def terminate_task(self, task_id: str) -> dict[str, Any]:
        """Terminate a running task."""
        status = self.get_task_status(task_id)
        if status["status"] != "running":
            return status

        # Try to terminate the detached process first
        if "detached_pid" in status:
            self._try_terminate_process(status["detached_pid"])
        # If the process is still in initial state, try terminating that
        elif "initial_pid" in status:
            self._try_terminate_process(status["initial_pid"])

        self._update_task_status(
            task_id,
            cast(TaskStatus, "terminated"),
            error="Task was terminated by user request",
        )
        return self.get_task_status(task_id)
