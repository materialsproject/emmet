import pytest


from emmet.core.qchem.calc_types import TaskType
from emmet.core.qchem.molecule import MoleculeDoc


try:
    from openbabel.openbabel import OBAlign

    _ = OBAlign()
    has_eigen = True
except ImportError:
    has_eigen = False


@pytest.mark.skip(reason="Pymatgen OBAlign needs fix")
@pytest.mark.skipif(
    not has_eigen, reason="OBAlign missing, presumably due to lack of Eigen"
)
def test_make_mol(liec_tasks):
    molecule = MoleculeDoc.from_tasks(liec_tasks)
    assert molecule.formula_alphabetical == "C3 H4 Li1 O3"
    assert len(molecule.task_ids) == 5
    assert len(molecule.entries) == 5
    assert molecule.coord_hash == "4cbc38414f4e0e809d53d6dc34ef0be4"

    bad_task_group = [
        task
        for task in liec_tasks
        if task.task_type
        not in [
            TaskType.Geometry_Optimization,
            TaskType.Frequency_Flattening_Geometry_Optimization,
        ]
    ]

    with pytest.raises(Exception):
        MoleculeDoc.from_tasks(bad_task_group)


@pytest.mark.skip(reason="Pymatgen OBAlign needs fix")
@pytest.mark.skipif(
    not has_eigen, reason="OBAlign missing, presumably due to lack of Eigen"
)
def test_make_deprecated_mol(liec_tasks):
    bad_task_group = [
        task
        for task in liec_tasks
        if task.task_type
        not in [
            TaskType.Geometry_Optimization,
            TaskType.Frequency_Flattening_Geometry_Optimization,
        ]
    ]

    molecule = MoleculeDoc.construct_deprecated_molecule(bad_task_group)

    assert molecule.deprecated
    assert molecule.formula_alphabetical == "C3 H4 Li1 O3"
    assert len(molecule.task_ids) == 4
    assert molecule.entries is None
    assert molecule.species_hash is not None


def test_schema():
    MoleculeDoc.schema()
