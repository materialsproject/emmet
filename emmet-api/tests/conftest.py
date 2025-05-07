import pytest

from emmet.core.testing_utils import TEST_FILES_DIR


@pytest.fixture(scope="session")
def test_dir():
    return TEST_FILES_DIR
