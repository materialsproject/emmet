from __future__ import annotations

import logging
import multiprocessing as mp
from datetime import datetime
from pathlib import Path
import time
from typing import Any, Callable, Dict, Optional
from uuid import uuid4

from emmet.cli.state_manager import StateManager

logger = logging.getLogger("emmet")


class TaskManager:
    """Manages background tasks and their states."""

    def __init__(
        self,
        state_manager: Optional[StateManager] = None,
        running_status_update_interval: int = 30,
    ):
        """Initialize the TaskManager with an optional StateManager instance."""
        self.state_manager = state_manager
        self.running_status_update_interval = running_status_update_interval

    def _task_wrapper(
        self, task_id: str, func: Callable[..., Any], *args: Any, **kwargs: Any
    ) -> None:
        """Wrapper function that executes the task and stores its result."""
        import time
        import threading

        running = True

        def update_running_status():
            while running:
                self._store_task_result(
                    task_id, {"still_running_at": datetime.now().isoformat()}
                )
                time.sleep(self.running_status_update_interval)

        status_thread = threading.Thread(target=update_running_status, daemon=True)
        status_thread.start()

        try:
            result = func(*args, **kwargs)
            running = False
            self._store_task_result(
                task_id,
                {
                    "status": "completed",
                    "result": result,
                    "completed_at": datetime.now().isoformat(),
                },
            )
        except Exception as e:
            running = False
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
            running = False

    def _store_task_result(self, task_id: str, result: Dict[str, Any]) -> None:
        """Store the task result in the state manager."""
        tasks = self.state_manager.get("tasks", {})
        tasks[task_id].update(result)
        self.state_manager.set("tasks", tasks)

    def start_task(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> str:
        """
        Start a new task in a separate process.

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

        # Start the process
        process = mp.Process(
            target=self._task_wrapper,
            args=(task_id, func) + args,
            kwargs=kwargs,
            daemon=True,
        )
        process.start()

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
            or if the task appears stalled (no status updates for too long)
        """
        status = self.get_task_status(task_id)
        if status["status"] != "running":
            return False

        # Check if task appears stalled
        if "started_at" in status and "still_running_at" in status:
            now = datetime.now()
            last_update = datetime.fromisoformat(status["still_running_at"])
            max_interval = self.running_status_update_interval * 3

            if (now - last_update).total_seconds() > max_interval:
                return False

        return True

    def cleanup_finished_tasks(self) -> None:
        """Remove finished tasks from the state manager."""
        tasks = self.state_manager.get("tasks", {})
        finished_tasks = [
            task_id for task_id in tasks.keys() if not self.is_task_running(task_id)
        ]
        for task_id in finished_tasks:
            del tasks[task_id]
        self.state_manager.set("tasks", tasks)
