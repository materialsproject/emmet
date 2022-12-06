from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def test_dir():
    return Path(__file__).parent.parent.parent.joinpath("test_files").resolve()
