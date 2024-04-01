from atomate2.classical_md.openmm.schemas.tasks import OpenMMTaskDocument
from atomate2.classical_md.schemas import ClassicalMDTaskDocument

import pytest


@pytest.fixture
def ec_emc_taskdoc(test_dir):
    return ClassicalMDTaskDocument.parse_file(
        test_dir / "classical_md" / "ec_emc_system" / "taskdoc_json"
    )


@pytest.fixture
def ec_emc_traj(test_dir):
    return test_dir / "classical_md" / "ec_emc_system" / "trajectory5_dcd"
