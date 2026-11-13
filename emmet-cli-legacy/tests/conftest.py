import hashlib
import shutil
from pathlib import Path

import pytest

from emmet.core.testing_utils import TEST_FILES_DIR, DataArchive


@pytest.fixture(scope="session")
def launcher_template(tmp_path_factory) -> Path:
    """A tree of launchers, made once and copied for each test:

    block_1/launcher_single   one calculation, with no suffix (NSCF uniform)
    block_1/launcher_double_relax   a double relaxation: relax1 and relax2
    block_2/launcher_broken   a calculation with no OUTCAR
    """
    root = tmp_path_factory.mktemp("template")
    for launcher, fixture in (
        ("block_1/launcher_single", "Si_uniform"),
        ("block_1/launcher_double_relax", "Si_old_double_relax"),
        ("block_2/launcher_broken", "Si_uniform"),
    ):
        with DataArchive.extract(TEST_FILES_DIR / "vasp" / f"{fixture}.json.gz") as d:
            shutil.copytree(d, root / launcher)
    (root / "block_2/launcher_broken/OUTCAR.gz").unlink()
    return root


@pytest.fixture
def launchers(launcher_template, tmp_path) -> Path:
    """A copy of the tree of launchers, which a test can change."""
    root = tmp_path / "launchers"
    shutil.copytree(launcher_template, root)
    return root


def snapshot(directory: Path) -> dict[str, tuple[float, str]]:
    """The modification time and checksum of every file in a directory."""
    return {
        str(p.relative_to(directory)): (
            p.stat().st_mtime,
            hashlib.md5(p.read_bytes()).hexdigest(),
        )
        for p in sorted(directory.rglob("*"))
        if p.is_file()
    }
