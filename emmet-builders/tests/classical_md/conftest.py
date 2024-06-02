from emmet.core.classical_md import ClassicalMDTaskDocument

import pytest


@pytest.fixture
def ec_emc_taskdoc(test_dir):
    return ClassicalMDTaskDocument.parse_file(
        test_dir / "classical_md" / "ec_emc_system" / "taskdoc.json"
    )


@pytest.fixture
def ec_emc_traj(test_dir):
    return test_dir / "classical_md" / "ec_emc_system" / "trajectory5.dcd"
