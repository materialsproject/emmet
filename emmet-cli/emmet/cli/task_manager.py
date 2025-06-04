from __future__ import annotations

import logging
import multiprocessing as mp
from datetime import datetime
import time
import os
from typing import Any, Callable, Dict, Optional
from uuid import uuid4
import psutil

from emmet.cli.state_manager import StateManager

logger = logging.getLogger("emmet")


def _detach_process():
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
    ):
        """Initialize the TaskManager with an optional StateManager instance."""
        self.state_manager = state_manager
        self.running_status_update_interval = running_status_update_interval

    def _task_wrapper(
        self, task_id: str, func: Callable[..., Any], *args: Any, **kwargs: Any
    ) -> None:
        """Wrapper function that executes the task and stores its result."""
        if _detach_process():
            return  # Parent process returns immediately

        # We are now in the detached child process
        import threading

        # Store the detached process PID
        self._store_task_result(task_id, {"detached_pid": os.getpid()})

        try:
            result = func(*args, **kwargs)
            self._store_task_result(
                task_id,
                {
                    "status": "completed",
                    "result": result,
                    "completed_at": datetime.now().isoformat(),
                },
            )
        except Exception as e:
            logger.exception(f"Task {task_id} failed")
            self._store_task_result(
                task_id,
                {
                    "status": "failed",
                    "error": str(e),
                    "completed_at": datetime.now().isoformat(),
                },
            )
        finally:
            os._exit(0)  # Ensure the process exits cleanly

    def _store_task_result(self, task_id: str, result: Dict[str, Any]) -> None:
        """Store the task result in the state manager."""
        tasks = self.state_manager.get("tasks", {})
        tasks[task_id].update(result)
        self.state_manager.set("tasks", tasks)

    def start_task(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> str:
        """
        Start a new task in a separate, fully detached process.

        Args:
            func: The function to execute
            *args: Positional arguments for the function
            **kwargs: Keyword arguments for the function

        Returns:
            str: The task ID
        """
        task_id = str(uuid4())

        # Initialize task state
        tasks = self.state_manager.get("tasks", {})
        tasks[task_id] = {
            "status": "running",
            "started_at": datetime.now().isoformat(),
        }
        self.state_manager.set("tasks", tasks)

        process = mp.Process(
            target=self._task_wrapper,
            args=(task_id, func) + args,
            kwargs=kwargs,
            daemon=False,
        )
        process.start()

        # Store the initial process ID
        self._store_task_result(task_id, {"initial_pid": process.pid})

        return task_id

    def get_task_status(self, task_id: str) -> Dict[str, Any]:
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
        self, task_id: str, timeout: Optional[float] = None, check_interval: float = 1.0
    ):
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

    def is_task_running(self, task_id: str) -> bool:
        """
        Check if a task is still running.

        Args:
            task_id: The ID of the task to check

        Returns:
            bool: True if the task is still running, False if completed, not found,
            or if the task was terminated.
        """
        status = self.get_task_status(task_id)
        if status["status"] != "running":
            return False

        now = datetime.now()

        # If we have a PID, check if the process is still running
        if "detached_pid" in status:
            if not _is_process_running(status["detached_pid"]):
                self._store_task_result(
                    task_id,
                    {
                        "status": "terminated",
                        "completed_at": now.isoformat(),
                        "error": "Process was terminated unexpectedly",
                    },
                )
                return False
            return True

        # If we have an initial PID but no detached PID, check if we should wait longer
        if "initial_pid" in status and "started_at" in status:
            start_time = datetime.fromisoformat(status["started_at"])
            elapsed = (now - start_time).total_seconds()

            # Give the process up to 5 seconds to detach before checking its status
            if elapsed < self.DETACH_GRACE_PERIOD:
                return True

            if not _is_process_running(status["initial_pid"]):
                self._store_task_result(
                    task_id,
                    {
                        "status": "terminated",
                        "completed_at": now.isoformat(),
                        "error": "Process failed to detach and was terminated",
                    },
                )
                return False
            # Process is still running but hasn't detached yet
            return True

        # If we have neither PID but the task is marked as running,
        # check if we should wait longer for initialization
        if "started_at" in status:
            start_time = datetime.fromisoformat(status["started_at"])
            elapsed = (now - start_time).total_seconds()

            # Give the process up to 2 seconds to initialize and register its PID
            if elapsed < self.INIT_GRACE_PERIOD:
                return True

            self._store_task_result(
                task_id,
                {
                    "status": "terminated",
                    "completed_at": now.isoformat(),
                    "error": "Process was terminated before initialization completed",
                },
            )
            return False

        # No started_at timestamp - this shouldn't happen but handle it anyway
        self._store_task_result(
            task_id,
            {
                "status": "terminated",
                "completed_at": now.isoformat(),
                "error": "Invalid task state: no start time recorded",
            },
        )
        return False

    def cleanup_finished_tasks(self) -> None:
        """Remove finished tasks from the state manager."""
        tasks = self.state_manager.get("tasks", {})
        finished_tasks = [
            task_id for task_id in tasks.keys() if not self.is_task_running(task_id)
        ]
        for task_id in finished_tasks:
            del tasks[task_id]
        self.state_manager.set("tasks", tasks)
