import gzip
import json
from pathlib import Path
import pytest


from emmet.core.tasks import TaskDoc


@pytest.fixture(scope="module")
def si_tasks(test_dir: Path) -> list[TaskDoc]:
    with gzip.open(test_dir / "test_si_tasks.json.gz", "rt") as f:
        data = json.load(f)

    for task in data:
        task.update({"is_valid": True})

    return [TaskDoc(**d) for d in data]
