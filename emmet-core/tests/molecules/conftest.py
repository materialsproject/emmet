from datetime import datetime
from monty.serialization import loadfn
import pytest

from emmet.core.qchem.task import TaskDocument


@pytest.fixture(scope="session")
def open_shell_nbo_task(test_dir):
    return TaskDocument(**loadfn(test_dir / "open_shell_nbo_task.json.gz"))


@pytest.fixture(scope="session")
def liec_tasks(test_dir):

    data = loadfn(test_dir / "liec_tasks.json.gz", cls=None)

    for d in data:
        d["last_updated"] = datetime.strptime(
            d["last_updated"]["string"], "%Y-%m-%d %H:%M:%S.%f"
        )

    tasks = [TaskDocument(**t) for t in data]
    return tasks
