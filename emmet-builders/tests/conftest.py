from emmet.core.testing_utils import _get_test_files_dir
import pytest


@pytest.fixture(scope="session")
def test_dir():
    return _get_test_files_dir("emmet.builders")
