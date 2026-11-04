import gzip
import json
from pathlib import Path

import numpy as np
import pytest


from emmet.core.tasks import TaskDoc


@pytest.fixture(scope="module")
def si_tasks(test_dir: Path) -> list[TaskDoc]:
    with gzip.open(test_dir / "test_si_tasks.json.gz", "rt") as f:
        data = json.load(f)

    for task in data:
        task.update({"is_valid": True})

    return [TaskDoc(**d) for d in data]


HEADER = """Fake CHGCAR
    4.0
0.0 0.5 0.5
0.5 0.0 0.5
0.5 0.5 0.0
    Cs Cl
    1 1
Direct
0.125 0.125 0.125
0.875 0.875 0.875

"""

AUG = """augmentation occupancies 1 8
 1.260048e+01 1.714564e+01 1.661357e+01 2.858822e+01 2.787026e+01
 1.410466e+01 2.336182e+01 1.469713e+01
augmentation occupancies 2 8
 2.425031e+01 1.936727e+01 1.474219e+01 7.047136e+00 2.467184e+01
 1.982424e+01 1.073396e+01 1.469713e+01
"""

GRID = (2, 2, 3)


def _volumetric_text(num_blocks: int, with_aug: bool) -> str:
    """Make a fake CHGCAR-like file with num_blocks data blocks."""
    rng = np.random.default_rng(seed=num_blocks)
    text = HEADER
    for _ in range(num_blocks):
        text += "    " + " ".join(str(n) for n in GRID) + "\n"
        vals = rng.uniform(-30, 30, size=int(np.prod(GRID)))
        for i in range(0, len(vals), 5):
            text += " " + " ".join(f"{v:.6e}" for v in vals[i : i + 5]) + "\n"
        if with_aug:
            text += AUG
    return text


@pytest.fixture(scope="module")
def volumetric_files(tmp_path_factory):
    out = tmp_path_factory.mktemp("volumetric")
    paths = {}
    for name, nblocks, aug in (
        ("collinear", 2, True),
        ("collinear_no_aug", 2, False),
        ("unpolarized", 1, False),
        ("noncollinear", 4, False),
        # the spin blocks of a POT file have the layout of a CHGCAR with augmentation
        ("pot_collinear", 2, True),
        ("pot_unpolarized", 1, True),
        ("pot_noncollinear", 4, True),
    ):
        paths[name] = out / name
        paths[name].write_text(_volumetric_text(nblocks, aug))
    return paths
