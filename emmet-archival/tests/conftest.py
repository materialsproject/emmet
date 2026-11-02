import os
from pathlib import Path
import pytest
import shutil
import tempfile
from uuid import uuid4

from emmet.core.tasks import TaskDoc
from monty.serialization import loadfn


@pytest.fixture(scope="session")
def test_dir():
    module_dir = Path(__file__).resolve().parent
    test_dir = module_dir / "test_files"
    return test_dir.resolve()


@pytest.fixture
def tmp_dir():
    old_cwd = os.getcwd()
    new_path = tempfile.mkdtemp()
    os.chdir(new_path)
    yield
    os.chdir(old_cwd)
    shutil.rmtree(new_path)


@pytest.fixture
def sample_task(test_dir) -> TaskDoc:
    return TaskDoc(**loadfn(test_dir / "mp-1201400_task_doc.json.gz"))


def archive_metadata(**kwargs) -> dict:
    """The minimal metadata of an archive, which can be overridden."""
    return {
        "calculation_id": str(uuid4()),
        "source_dir_name": "host:/some/launcher",
        **kwargs,
    }
