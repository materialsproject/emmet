import os
from pathlib import Path
import pytest
import shutil
import tempfile

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
