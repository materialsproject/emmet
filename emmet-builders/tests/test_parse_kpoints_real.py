"""Test the number of k-points of the tasks of real calculations that were run with KSPACING."""

import pytest

from emmet.builders.utils import _parse_kpoints
from emmet.core.testing_utils import DataArchive
from emmet.core.vasp.parse import DirectorySource, parse_calculation


def task_of(test_dir, fixture):
    with DataArchive.extract(test_dir / "vasp" / f"{fixture}.json.gz") as directory:
        parsed = parse_calculation(
            DirectorySource.from_directory(directory)[0], "aaaaaaab"
        )
    assert parsed.errors == []
    return parsed.task


@pytest.mark.parametrize(
    "fixture, kspacing, mesh",
    [("magnetic_relax", 0.22, 8 * 8 * 6), ("magnetic_static_volumetric", 0.1, 22**3)],
)
def test_a_mesh_from_kspacing(test_dir, fixture, kspacing, mesh):
    """These have no KPOINTS file: the mesh VASP made from KSPACING is in the vasprun."""
    task = task_of(test_dir, fixture)
    assert task.input.incar["KSPACING"] == kspacing
    assert task.orig_inputs.kpoints is None
    assert _parse_kpoints(task) == mesh
